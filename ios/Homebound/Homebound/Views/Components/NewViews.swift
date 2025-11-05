import SwiftUI
import Combine

// MARK: - Main Home Dashboard
struct HomeView: View {
    @EnvironmentObject var session: Session
    @State private var showingCreatePlan = false
    @State private var showingAuth = false
    @State private var activePlan: PlanOut?
    @State private var recentPlans: [PlanOut] = []
    @State private var timeline: [TimelineEvent] = []

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Active Plan Card
                    if let plan = activePlan {
                        ActivePlanCard(plan: plan, timeline: $timeline)
                            .transition(.move(edge: .top).combined(with: .opacity))
                    }

                    // Quick Actions
                    HStack(spacing: 16) {
                        Button(action: { showingCreatePlan = true }) {
                            QuickActionButton(
                                icon: "plus.circle.fill",
                                title: "Start New Trip",
                                color: .blue
                            )
                        }
                        .disabled(session.accessToken == nil)

                        if activePlan != nil {
                            Button(action: { Task { await checkoutActive() } }) {
                                QuickActionButton(
                                    icon: "house.fill",
                                    title: "I'm Home Safe",
                                    color: .green
                                )
                            }
                        }
                    }
                    .padding(.horizontal)

                    // Recent Activity
                    if !recentPlans.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Recent Trips")
                                .font(.headline)
                                .padding(.horizontal)

                            ForEach(recentPlans.prefix(5)) { plan in
                                RecentTripRow(plan: plan)
                                    .padding(.horizontal)
                            }
                        }
                    }

                    // Stats Summary (placeholder for future)
                    HStack(spacing: 16) {
                        StatCard(value: "12", label: "Trips", icon: "map.fill")
                        StatCard(value: "3", label: "This Week", icon: "calendar")
                        StatCard(value: "🥾", label: "Favorite", icon: nil)
                    }
                    .padding(.horizontal)
                }
                .padding(.vertical)
            }
            .navigationTitle("Homebound")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: { showingAuth = true }) {
                        Image(systemName: session.accessToken != nil ? "person.crop.circle.fill" : "person.crop.circle")
                            .foregroundStyle(session.accessToken != nil ? .green : .gray)
                    }
                }
            }
            .sheet(isPresented: $showingCreatePlan) {
                OldCreatePlanView()
            }
            .sheet(isPresented: $showingAuth) {
                AuthView()
            }
            .task {
                await loadActivePlan()
            }
        }
    }

    func loadActivePlan() async {
        // TODO: Fetch active plan from API
    }

    func checkoutActive() async {
        guard activePlan != nil else { return }
        // TODO: Call checkout endpoint
    }
}

// MARK: - Active Plan Card
struct ActivePlanCard: View {
    let plan: PlanOut
    @Binding var timeline: [TimelineEvent]
    @State private var timeRemaining = ""
    @State private var isOverdue = false

    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var activity: ActivityType {
        ActivityType(rawValue: plan.activity_type) ?? .other
    }

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                Text(activity.icon)
                    .font(.largeTitle)
                VStack(alignment: .leading) {
                    Text(plan.title)
                        .font(.headline)
                    Text(activity.displayName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: isOverdue ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                    .foregroundStyle(isOverdue ? .red : .green)
            }

            // Countdown Timer
            Text(timeRemaining)
                .font(.system(size: 48, weight: .bold, design: .rounded))
                .foregroundStyle(isOverdue ? .red : activity.primaryColor)

            Text(isOverdue ? "OVERDUE" : "Time Remaining")
                .font(.caption)
                .textCase(.uppercase)
                .foregroundStyle(.secondary)

            // Location Info
            if let location = plan.location_text {
                HStack {
                    Image(systemName: "location.fill")
                        .font(.caption)
                    Text(location)
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            // Action Buttons
            HStack(spacing: 12) {
                Button("Check In") {
                    Task { await performCheckin() }
                }
                .buttonStyle(ActivityButtonStyle(color: activity.primaryColor))

                Button("Extend +30min") {
                    Task { await extendTrip() }
                }
                .buttonStyle(.bordered)
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(activity.primaryColor.opacity(0.1))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(activity.primaryColor.opacity(0.3), lineWidth: 1)
        )
        .padding(.horizontal)
        .onReceive(timer) { _ in
            updateTimer()
        }
    }

    func updateTimer() {
        let now = Date()
        let eta = plan.eta_at
        let interval = eta.timeIntervalSince(now)

        if interval < 0 {
            isOverdue = true
            let overdueInterval = abs(interval)
            let hours = Int(overdueInterval) / 3600
            let minutes = Int(overdueInterval) % 3600 / 60
            timeRemaining = String(format: "%02d:%02d", hours, minutes)
        } else {
            isOverdue = false
            let hours = Int(interval) / 3600
            let minutes = Int(interval) % 3600 / 60
            let seconds = Int(interval) % 60
            timeRemaining = String(format: "%02d:%02d:%02d", hours, minutes, seconds)
        }
    }

    func performCheckin() async {
        // TODO: Implement checkin
    }

    func extendTrip() async {
        // TODO: Implement extend
    }
}

// MARK: - Create Plan View (Old Version - Deprecated)
struct OldCreatePlanView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var session: Session

    @State private var title = ""
    @State private var selectedActivity = ActivityType.other
    @State private var location = ""
    @State private var departureTime = Date()
    @State private var returnTime = Date().addingTimeInterval(3600)
    @State private var graceMinutes = 30
    @State private var showingDetailedMode = false
    @State private var notes = ""
    @State private var contacts: [ContactIn] = []

    var body: some View {
        NavigationStack {
            Form {
                // Quick Mode Sections
                Section {
                    TextField("Trip Title", text: $title)
                        .font(.title3)

                    Picker("Activity", selection: $selectedActivity) {
                        ForEach(ActivityType.allCases, id: \.self) { activity in
                            Label(activity.displayName, systemImage: "")
                                .tag(activity)
                        }
                    }
                    .onChange(of: selectedActivity) { _, newValue in
                        graceMinutes = newValue.defaultGraceMinutes
                        if title.isEmpty {
                            title = "\(newValue.displayName) Trip"
                        }
                    }
                } header: {
                    Text("What are you doing?")
                }

                Section {
                    TextField("Location / Trail / Route", text: $location)

                    DatePicker("Leaving at", selection: $departureTime, displayedComponents: [.date, .hourAndMinute])

                    DatePicker("Back by", selection: $returnTime, displayedComponents: [.date, .hourAndMinute])

                    Stepper("Grace Period: \(graceMinutes) min", value: $graceMinutes, in: 15...120, step: 15)
                } header: {
                    Text("Trip Details")
                }

                // Activity-specific tips
                Section {
                    ForEach(selectedActivity.safetyTips, id: \.self) { tip in
                        Label(tip, systemImage: "checkmark.circle")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Safety Reminders")
                } footer: {
                    Text(selectedActivity.startMessage)
                        .font(.caption)
                        .italic()
                }

                // Advanced Options
                if showingDetailedMode {
                    Section {
                        TextEditor(text: $notes)
                            .frame(minHeight: 80)
                    } header: {
                        Text("Trip Notes")
                    }

                    Section {
                        Button("Add Contact") {
                            // TODO: Add contact
                        }
                        ForEach(contacts, id: \.name) { contact in
                            Text(contact.name)
                        }
                    } header: {
                        Text("Emergency Contacts")
                    }
                }

                Section {
                    Toggle("Show More Options", isOn: $showingDetailedMode)
                        .tint(selectedActivity.primaryColor)
                }

                // Create Button
                Section {
                    Button(action: createPlan) {
                        HStack {
                            Spacer()
                            Label("Start Adventure", systemImage: "play.fill")
                                .font(.headline)
                            Spacer()
                        }
                    }
                    .buttonStyle(ActivityButtonStyle(color: selectedActivity.primaryColor))
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
                }
            }
            .navigationTitle("New Trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    func createPlan() {
        Task {
            _ = PlanCreate(
                title: title,
                activity_type: selectedActivity.rawValue,
                start_at: departureTime,
                eta_at: returnTime,
                grace_minutes: graceMinutes,
                location_text: location.isEmpty ? nil : location,
                notes: notes.isEmpty ? nil : notes,
                contacts: contacts
            )

            // TODO: Call API to create plan
            dismiss()
        }
    }
}

// MARK: - Auth View
struct AuthView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var session: Session
    @State private var email = ""
    @State private var code = ""
    @State private var showingVerification = false

    var body: some View {
        NavigationStack {
            Form {
                if !showingVerification {
                    Section {
                        TextField("Email Address", text: $email)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()

                        Button("Send Magic Link") {
                            Task {
                                await session.requestMagicLink(email: email)
                                showingVerification = true
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!email.contains("@"))
                    } header: {
                        Text("Sign In")
                    } footer: {
                        Text("We'll send you a 6-digit code to verify your email.")
                    }
                } else {
                    Section {
                        TextField("6-Digit Code", text: $code)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)

                        Button("Verify Code") {
                            Task {
                                await session.verifyMagic(code: code, email: email)
                                if session.accessToken != nil {
                                    dismiss()
                                }
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(code.count != 6)
                    } header: {
                        Text("Enter Verification Code")
                    } footer: {
                        Text("Check your email for the code we sent to \(email)")
                    }
                }
            }
            .navigationTitle(session.accessToken != nil ? "Profile" : "Sign In")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Helper Components
struct QuickActionButton: View {
    let icon: String
    let title: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.largeTitle)
                .foregroundStyle(color)
            Text(title)
                .font(.caption)
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(color.opacity(0.1))
        )
    }
}

struct RecentTripRow: View {
    let plan: PlanOut

    var activity: ActivityType {
        ActivityType(rawValue: plan.activity_type) ?? .other
    }

    var body: some View {
        HStack {
            Text(activity.icon)
                .font(.title2)
            VStack(alignment: .leading) {
                Text(plan.title)
                    .font(.footnote)
                Text(plan.eta_at, style: .relative)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text(plan.status.capitalized)
                .font(.caption)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(Capsule().fill(statusColor.opacity(0.2)))
                .foregroundStyle(statusColor)
        }
        .padding(.vertical, 4)
    }

    var statusColor: Color {
        switch plan.status {
        case "active": return .orange
        case "completed": return .green
        default: return .gray
        }
    }
}

struct StatCard: View {
    let value: String
    let label: String
    let icon: String?

    var body: some View {
        VStack(spacing: 4) {
            if let icon = icon {
                Image(systemName: icon)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .font(.title2.bold())
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(.systemGray6))
        )
    }
}

struct ActivityButtonStyle: ButtonStyle {
    let color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white)
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(color)
                    .opacity(configuration.isPressed ? 0.8 : 1)
            )
    }
}