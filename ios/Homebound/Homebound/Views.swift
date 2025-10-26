import SwiftUI

struct RootView: View {
    @EnvironmentObject var session: Session
    @State private var email = ""
    @State private var code = ""
    @State private var plan: PlanOut?
    @State private var timeline: [TimelineEvent] = []

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)

                    Button("Request Link") {
                        Task {
                            await session.requestMagicLink(email: emailTrimmed)
                            if let latest = await session.devPeekCode(email: emailTrimmed) {
                                await MainActor.run { code = latest }
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!isValidEmail(emailTrimmed))

                    TextField("6-digit code", text: $code)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .autocorrectionDisabled(true)

                    Button("Verify Code") {
                        Task { await session.verifyMagic(code: codeTrimmed, email: emailTrimmed) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(!isValidEmail(emailTrimmed) || !isValidCode(codeTrimmed))
                } header: {
                    Text("Auth (dev)")
                }

                Section {
                    Button("Create quick plan") { Task { await createQuickPlan() } }
                        .disabled(session.accessToken == nil)
                    if let p = plan {
                        NavigationLink("Open \(p.title)", destination: PlanDetail(plan: p, timeline: $timeline))
                    }
                } header: {
                    Text("Create Plan")
                }

                Section {
                    Text("Base URL: \(session.baseURL.absoluteString)")
                        .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    Button("Ping /health") { Task { await session.ping() } }
                    if !session.notice.isEmpty {
                        Text(session.notice).font(.caption).foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Debug")
                }
            }
            .navigationTitle("Homebound")
            .onReceive(NotificationCenter.default.publisher(for: .hbGotAPNsToken)) { note in
                if let t = note.object as? String { session.handleAPNsToken(t) }
            }
        }
    }

    // MARK: helpers
    var emailTrimmed: String { email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
    var codeTrimmed: String { code.trimmingCharacters(in: .whitespacesAndNewlines) }
    func isValidEmail(_ s: String) -> Bool { s.contains("@") && s.contains(".") && s.count > 5 }
    func isValidCode(_ s: String) -> Bool { s.count == 6 && s.allSatisfy({ $0.isNumber }) }

    func createQuickPlan() async {
        guard let bearer = session.accessToken else { return }
        let now = Date()
        let eta = now.addingTimeInterval(3 * 3600)
        let payload = PlanCreate(title: "iOS Demo Plan", start_at: now, eta_at: eta,
                                 grace_minutes: 30, location_text: "Trailhead", notes: "Blue trail")
        do {
            let p: PlanOut = try await session.api.post(
                session.url("/api/v1/plans"),
                body: payload, bearer: bearer
            )
            plan = p
            try await reloadTimeline(planId: p.id)
        } catch {
            session.notice = "Create plan failed: \(error.localizedDescription)"
        }
    }

    func reloadTimeline(planId: Int) async throws {
        let r: TimelineResponse = try await session.api.get(
            session.url("/api/v1/plans/\(planId)/timeline"),
            bearer: session.accessToken
        )
        await MainActor.run {
            timeline = r.events
            session.notice = "Timeline reloaded (\(r.events.count) events)"
        }
    }
}

struct PlanDetail: View {
    @EnvironmentObject var session: Session
    let plan: PlanOut
    @Binding var timeline: [TimelineEvent]

    var body: some View {
        List {
            Section {
                Text(plan.title)
                Text("Start \(plan.start_at.formatted(date: .abbreviated, time: .shortened))")
                Text("ETA \(plan.eta_at.formatted(date: .abbreviated, time: .shortened))")
                Text("Status \(plan.status)")
            } header: {
                Text("Plan")
            }
            Section {
                Button("Check-In") { Task { await hitToken(plan.checkin_token, action: "checkin") } }
                Button("Check-Out") { Task { await hitToken(plan.checkout_token, action: "checkout") } }
            } header: {
                Text("Actions")
            }
            Section {
                Button("Reload timeline") { Task { await refresh() } }
                ForEach(timeline) { e in
                    VStack(alignment: .leading) {
                        Text(e.kind.capitalized)
                        Text(e.at.formatted(date: .numeric, time: .standard))
                            .foregroundStyle(.secondary).font(.caption)
                    }
                }
            } header: {
                Text("Timeline")
            }
        }
        .navigationTitle("Plan")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Refresh") { Task { await refresh() } }
            }
        }
    }

    @MainActor
    private func refresh() async {
        do {
            let r: TimelineResponse = try await session.api.get(
                session.url("/api/v1/plans/\(plan.id)/timeline"),
                bearer: session.accessToken
            )
            timeline = r.events
            session.notice = "Timeline refreshed (\(r.events.count) events)"
        } catch {
            session.notice = "Timeline refresh failed: \(error.localizedDescription)"
            print("timeline refresh failed:", error)
        }
    }

    private func hitToken(_ token: String, action: String) async {
        do {
            struct Resp: Decodable { let ok: Bool }
            let _: Resp = try await session.api.get(
                session.url("/t/\(token)/\(action)"),
                bearer: Optional<String>.none
            )
            await refresh()
        } catch {
            session.notice = "Token action failed: \(error.localizedDescription)"
            print("token action failed:", error)
        }
    }
}
