import SwiftUI
import Combine

// MARK: - Main Tab View with Dock Navigation
struct MainTabView: View {
    @EnvironmentObject var session: Session
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            // Home Tab
            NewHomeView()
                .tabItem {
                    Label("Home", systemImage: "house.fill")
                }
                .tag(0)

            // History Tab
            HistoryTabView()
                .tabItem {
                    Label("History", systemImage: "clock.fill")
                }
                .tag(1)
        }
        .accentColor(Color(hex: "#6C63FF") ?? .purple)
    }
}

// MARK: - New Home View with Big Trip Card
struct NewHomeView: View {
    @EnvironmentObject var session: Session
    @State private var showingCreatePlan = false
    @State private var showingSettings = false
    @State private var greeting = "Good morning"
    @State private var timeline: [TimelineEvent] = []

    var body: some View {
        NavigationStack {
            ZStack {
                // Background gradient
                LinearGradient(
                    colors: [
                        Color(.systemBackground),
                        Color(.systemBackground).opacity(0.95)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Header with greeting and settings
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(greeting)\(session.userName != nil ? ", \(session.userName!)" : "")")
                                    .font(.largeTitle)
                                    .fontWeight(.bold)
                                    .foregroundStyle(
                                        LinearGradient(
                                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                            startPoint: .leading,
                                            endPoint: .trailing
                                        )
                                    )
                                Text("Ready for your next adventure?")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            // Settings button
                            Button(action: { showingSettings = true }) {
                                Circle()
                                    .fill(
                                        LinearGradient(
                                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                                    .frame(width: 44, height: 44)
                                    .overlay(
                                        Image(systemName: "gearshape.fill")
                                            .foregroundStyle(.white)
                                            .font(.system(size: 20))
                                    )
                            }
                        }
                        .padding(.horizontal)
                        .padding(.top, 8)

                        // Check for active plan first
                        if let activePlan = session.activePlan {
                            // Show active plan card instead of new trip card
                            ActivePlanCardCompact(plan: activePlan, timeline: $timeline)
                                .padding(.horizontal)
                        } else {
                            // Big New Trip Card
                            BigNewTripCard(showingCreatePlan: $showingCreatePlan)
                                .padding(.horizontal)
                        }

                        // Quick Stats Section (optional)
                        if session.activePlan == nil {
                            QuickStatsSection()
                                .padding(.horizontal)
                        }
                    }
                    .padding(.bottom, 100)
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showingCreatePlan) {
                CreatePlanView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
                    .environmentObject(session)
            }
            .task {
                updateGreeting()
                await session.loadActivePlan()
                await session.loadUserProfile()
            }
        }
    }

    func updateGreeting() {
        let hour = Calendar.current.component(.hour, from: Date())
        greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
    }
}

// MARK: - Big New Trip Card
struct BigNewTripCard: View {
    @Binding var showingCreatePlan: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Card content
            VStack(spacing: 20) {
                // Icon
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 80, height: 80)

                    Image(systemName: "location.north.fill")
                        .font(.system(size: 40))
                        .foregroundStyle(.white)
                }

                // Title
                VStack(spacing: 8) {
                    Text("Start a New Trip")
                        .font(.title2)
                        .fontWeight(.bold)

                    Text("Let someone know where you're going")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }

                // Features list
                VStack(alignment: .leading, spacing: 12) {
                    FeatureRow(icon: "clock", text: "Set your expected return time")
                    FeatureRow(icon: "person.2", text: "Add emergency contacts")
                    FeatureRow(icon: "bell", text: "Automatic safety alerts")
                }
                .padding(.horizontal)

                // Create button
                Button(action: { showingCreatePlan = true }) {
                    HStack {
                        Image(systemName: "plus.circle.fill")
                        Text("Create New Trip")
                            .fontWeight(.semibold)
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .cornerRadius(12)
                }
            }
            .padding(24)
        }
        .background(Color(.secondarySystemBackground))
        .cornerRadius(20)
        .shadow(color: Color.black.opacity(0.1), radius: 10, x: 0, y: 5)
    }
}

// MARK: - Feature Row
struct FeatureRow: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                .frame(width: 24)

            Text(text)
                .font(.subheadline)
                .foregroundStyle(.primary)

            Spacer()
        }
    }
}

// MARK: - Active Plan Card Compact
struct ActivePlanCardCompact: View {
    let plan: PlanOut
    @Binding var timeline: [TimelineEvent]
    @EnvironmentObject var session: Session
    @State private var timeRemaining = ""
    @State private var isOverdue = false
    @State private var isPerformingAction = false
    @State private var showingExtendOptions = false
    @State private var selectedExtendMinutes = 30

    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    let extendOptions = [
        (15, "15 minutes"),
        (30, "30 minutes"),
        (60, "1 hour"),
        (120, "2 hours"),
        (180, "3 hours")
    ]

    var body: some View {
        VStack(spacing: 20) {
            // Status badge
            HStack {
                Circle()
                    .fill(isOverdue ? Color.red : Color.green)
                    .frame(width: 12, height: 12)

                Text(isOverdue ? "OVERDUE" : "ACTIVE TRIP")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundStyle(isOverdue ? Color.red : Color.green)

                Spacer()
            }

            // Plan info
            VStack(alignment: .leading, spacing: 12) {
                Text(plan.title)
                    .font(.title2)
                    .fontWeight(.bold)

                if let location = plan.location_text {
                    HStack {
                        Image(systemName: "location.fill")
                            .font(.caption)
                        Text(location)
                            .font(.subheadline)
                    }
                    .foregroundStyle(.secondary)
                }

                // Time remaining
                VStack(alignment: .leading, spacing: 4) {
                    Text("Expected return")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(timeRemaining)
                        .font(.title3)
                        .fontWeight(.semibold)
                        .foregroundStyle(isOverdue ? Color.red : Color.primary)
                }
            }

            // Action buttons
            HStack(spacing: 16) {
                // Check-in button
                Button(action: {
                    Task {
                        isPerformingAction = true
                        await session.performTokenAction(plan.checkin_token, action: "checkin")
                        isPerformingAction = false
                    }
                }) {
                    Label("Check In", systemImage: "checkmark.circle.fill")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color.green)
                        .cornerRadius(10)
                }

                // I'm safe button
                Button(action: {
                    Task {
                        isPerformingAction = true
                        await session.performTokenAction(plan.checkout_token, action: "checkout")
                        // Reload active plan to update UI
                        await session.loadActivePlan()
                        isPerformingAction = false
                    }
                }) {
                    Label("I'm Safe", systemImage: "house.fill")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(
                            LinearGradient(
                                colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .cornerRadius(10)
                }
            }
            .disabled(isPerformingAction)

            // Extend time section
            VStack(spacing: 12) {
                if showingExtendOptions {
                    VStack(spacing: 8) {
                        Text("Extend trip by:")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        HStack(spacing: 8) {
                            ForEach(extendOptions, id: \.0) { minutes, label in
                                Button(action: {
                                    Task {
                                        isPerformingAction = true
                                        _ = await session.extendPlan(minutes: minutes)
                                        showingExtendOptions = false
                                        isPerformingAction = false
                                    }
                                }) {
                                    Text(label)
                                        .font(.caption)
                                        .fontWeight(.medium)
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 6)
                                        .background(Color(hex: "#6C63FF") ?? .purple)
                                        .cornerRadius(6)
                                }
                            }
                        }
                    }
                    .transition(.scale.combined(with: .opacity))
                } else {
                    Button(action: {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            showingExtendOptions = true
                        }
                    }) {
                        Label("Extend Time", systemImage: "clock.arrow.circlepath")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                    }
                }
            }
        }
        .padding(24)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(20)
        .shadow(color: Color.black.opacity(0.1), radius: 10, x: 0, y: 5)
        .onReceive(timer) { _ in
            updateTimeRemaining()
        }
        .onAppear {
            updateTimeRemaining()
        }
    }

    func updateTimeRemaining() {
        let now = Date()
        let eta = plan.eta_at.addingTimeInterval(Double(plan.grace_minutes) * 60)

        if now > eta {
            isOverdue = true
            let interval = now.timeIntervalSince(eta)
            timeRemaining = formatInterval(interval) + " overdue"
        } else {
            isOverdue = false
            let interval = eta.timeIntervalSince(now)
            timeRemaining = formatInterval(interval)
        }
    }

    func formatInterval(_ interval: TimeInterval) -> String {
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes) minutes"
        }
    }
}

// MARK: - Quick Stats Section
struct QuickStatsSection: View {
    @EnvironmentObject var session: Session

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your Safety Stats")
                .font(.headline)

            HStack(spacing: 16) {
                QuickStatCard(
                    icon: "checkmark.shield.fill",
                    value: "12",
                    label: "Safe Returns",
                    color: .green
                )

                QuickStatCard(
                    icon: "clock.fill",
                    value: "3h",
                    label: "Avg Trip",
                    color: Color(hex: "#6C63FF") ?? .purple
                )

                QuickStatCard(
                    icon: "person.2.fill",
                    value: "3",
                    label: "Contacts",
                    color: Color(hex: "#4ECDC4") ?? .teal
                )
            }
        }
    }
}

// MARK: - Quick Stat Card
struct QuickStatCard: View {
    let icon: String
    let value: String
    let label: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)

            Text(value)
                .font(.title3)
                .fontWeight(.bold)

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color(.tertiarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - History Tab View
struct HistoryTabView: View {
    @EnvironmentObject var session: Session
    @State private var plans: [PlanOut] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView("Loading history...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if plans.isEmpty {
                    EmptyHistoryView()
                } else {
                    List(plans) { plan in
                        HistoryRowView(plan: plan)
                            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    }
                    .listStyle(PlainListStyle())
                }
            }
            .navigationTitle("Trip History")
            .navigationBarTitleDisplayMode(.large)
            .task {
                await loadHistory()
            }
            .refreshable {
                await loadHistory()
            }
            .alert("Error", isPresented: .constant(errorMessage != nil)) {
                Button("OK") { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
        }
    }

    func loadHistory() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let loadedPlans: [PlanOut] = try await session.api.get(
                session.url("/api/v1/plans"),
                bearer: session.accessToken
            )
            await MainActor.run {
                // Sort by most recent first
                self.plans = loadedPlans.sorted { $0.start_at > $1.start_at }
            }
        } catch {
            await MainActor.run {
                errorMessage = "Failed to load history: \(error.localizedDescription)"
            }
        }
    }
}

// MARK: - Empty History View
struct EmptyHistoryView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "clock.badge.xmark")
                .font(.system(size: 60))
                .foregroundStyle(.secondary)

            Text("No Trip History")
                .font(.title2)
                .fontWeight(.bold)

            Text("Your completed trips will appear here")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - History Row View
struct HistoryRowView: View {
    let plan: PlanOut

    var statusColor: Color {
        switch plan.status {
        case "completed": return .green
        case "cancelled": return .orange
        case "overdue": return .red
        default: return .blue
        }
    }

    var statusIcon: String {
        switch plan.status {
        case "completed": return "checkmark.circle.fill"
        case "cancelled": return "xmark.circle.fill"
        case "overdue": return "exclamationmark.triangle.fill"
        default: return "clock.fill"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title)
                        .font(.headline)

                    if let location = plan.location_text {
                        HStack(spacing: 4) {
                            Image(systemName: "location.fill")
                                .font(.caption)
                            Text(location)
                                .font(.caption)
                        }
                        .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // Status badge
                HStack(spacing: 4) {
                    Image(systemName: statusIcon)
                        .font(.caption)
                    Text(plan.status.capitalized)
                        .font(.caption)
                        .fontWeight(.semibold)
                }
                .foregroundStyle(statusColor)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(statusColor.opacity(0.1))
                .cornerRadius(8)
            }

            // Date and duration
            HStack {
                Image(systemName: "calendar")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(plan.start_at.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Spacer()

                if let duration = calculateDuration(from: plan.start_at, to: plan.eta_at) {
                    Text(duration)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 8)
    }

    func calculateDuration(from start: Date, to end: Date) -> String? {
        let interval = end.timeIntervalSince(start)
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes) minutes"
        }
        return nil
    }
}

#Preview {
    MainTabView()
        .environmentObject(Session())
}