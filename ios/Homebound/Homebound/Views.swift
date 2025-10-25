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
                Section("Auth (dev)") {
                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()

                    Button("Request Link") {
                        Task {
                            do {
                                try await session.requestMagicLink(email: emailTrimmed)
                                if let latest = await session.devPeekCode(email: emailTrimmed) {
                                    await MainActor.run { code = latest }
                                }
                            } catch {
                                await MainActor.run { session.notice = "Request failed: \(error.localizedDescription)" }
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!isValidEmail(emailTrimmed))

                    TextField("6-digit code", text: $code)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .autocorrectionDisabled()

                    Button("Verify Code") {
                        Task {
                            do {
                                try await session.verifyMagic(code: codeTrimmed, email: emailTrimmed)
                            } catch {
                                await MainActor.run { session.notice = "Verify failed: \(error.localizedDescription)" }
                            }
                        }
                    }
                    .buttonStyle(.bordered)
                    .disabled(!isValidEmail(emailTrimmed) || !isValidCode(codeTrimmed))
                }

                Section("Create Plan") {
                    Button("Create quick plan") { Task { await createQuickPlan() } }
                        .disabled(session.accessToken == nil)
                    if let p = plan {
                        NavigationLink("Open \(p.title)", destination: PlanDetail(plan: p, timeline: $timeline))
                    }
                }

                Section("Debug") {
                    Text("Base URL: \(session.baseURL.absoluteString)")
                        .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    Button("Ping /health") { Task { await session.ping() } }
                    if let msg = session.notice {
                        Text(msg).font(.caption).foregroundStyle(.secondary)
                    }
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
            Section("Plan") {
                Text(plan.title)
                Text("Start \(plan.start_at.formatted(date: .abbreviated, time: .shortened))")
                Text("ETA \(plan.eta_at.formatted(date: .abbreviated, time: .shortened))")
                Text("Status \(plan.status)")
            }
            Section("Actions") {
                Button("Check-In") { Task { await hitToken(plan.checkin_token, action: "checkin") } }
                Button("Check-Out") { Task { await hitToken(plan.checkout_token, action: "checkout") } }
            }
            Section("Timeline") {
                Button("Reload timeline") { Task { await refresh() } }
                ForEach(timeline) { e in
                    VStack(alignment: .leading) {
                        Text(e.kind.capitalized)
                        Text(e.at.formatted(date: .numeric, time: .standard))
                            .foregroundStyle(.secondary).font(.caption)
                    }
                }
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
