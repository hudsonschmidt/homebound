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
    @State private var refreshID = UUID()

    var firstName: String? {
        session.userName?.components(separatedBy: " ").first
    }

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
                                Text("\(greeting)\(firstName != nil ? ", \(firstName!)" : "")")
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

                        // Upcoming Trips Section (always visible)
                        UpcomingTripsSection()
                            .padding(.horizontal)
                            .id(refreshID)
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
                // Sync all data on app open
                await syncData()
            }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
                Task {
                    // Sync when app comes to foreground
                    await syncData()
                }
            }
        }
    }

    func updateGreeting() {
        let hour = Calendar.current.component(.hour, from: Date())
        greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
    }

    func syncData() async {
        // Load all necessary data in parallel
        async let loadActive: Void = session.loadActivePlan()
        async let loadProfile: Void = session.loadUserProfile()

        // Wait for all to complete
        _ = await (loadActive, loadProfile)

        // Trigger a refresh of child views by changing the ID
        await MainActor.run {
            refreshID = UUID()
        }
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
                    if let token = plan.checkin_token {
                        Task {
                            isPerformingAction = true
                            await session.performTokenAction(token, action: "checkin")
                            isPerformingAction = false
                        }
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
                .disabled(plan.checkin_token == nil || isPerformingAction)

                // I'm safe button
                Button(action: {
                    if let token = plan.checkout_token {
                        Task {
                            isPerformingAction = true
                            await session.performTokenAction(token, action: "checkout")
                            // Reload active plan to update UI
                            await session.loadActivePlan()
                            isPerformingAction = false
                        }
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
                .disabled(plan.checkout_token == nil || isPerformingAction)
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

// MARK: - Upcoming Trips Section
struct UpcomingTripsSection: View {
    @EnvironmentObject var session: Session
    @State private var upcomingPlans: [PlanOut] = []
    @State private var currentTime = Date()
    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Upcoming Trips")
                .font(.headline)

            if upcomingPlans.isEmpty {
                HStack {
                    Image(systemName: "calendar.badge.clock")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("No upcoming trips scheduled")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.vertical, 20)
                .padding(.horizontal)
                .background(Color(.tertiarySystemBackground))
                .cornerRadius(12)
            } else {
                ForEach(upcomingPlans) { plan in
                    UpcomingTripCard(plan: plan, currentTime: currentTime)
                }
            }
        }
        .onReceive(timer) { time in
            currentTime = time
        }
        .task {
            await loadUpcomingPlans()
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
            Task {
                await loadUpcomingPlans()
            }
        }
    }

    func loadUpcomingPlans() async {
        // Load plans with caching support (uses LocalStorage for offline access)
        let allPlans = await session.loadAllTrips()

        await MainActor.run {
            upcomingPlans = allPlans
                .filter { $0.status == "planned" }
                .sorted { $0.start_at < $1.start_at }
                .prefix(3) // Show max 3 upcoming trips
                .map { $0 }
        }
    }
}

// MARK: - Upcoming Trip Card
struct UpcomingTripCard: View {
    let plan: PlanOut
    let currentTime: Date

    var activity: ActivityType {
        // Try exact match first
        if let matched = ActivityType(rawValue: plan.activity_type.lowercased()) {
            return matched
        }

        // Try converting spaces to underscores and lowercasing
        let normalized = plan.activity_type.lowercased().replacingOccurrences(of: " ", with: "_")
        return ActivityType(rawValue: normalized) ?? .other
    }

    var countdown: String {
        let interval = plan.start_at.timeIntervalSince(currentTime)

        if interval <= 0 {
            return "Starting now"
        }

        return formatCountdown(interval)
    }

    var body: some View {
        HStack {
            // Activity icon
            Circle()
                .fill(activity.primaryColor.opacity(0.2))
                .frame(width: 40, height: 40)
                .overlay(
                    Text(activity.icon)
                        .font(.title3)
                )

            VStack(alignment: .leading, spacing: 4) {
                Text(plan.title)
                    .font(.subheadline)
                    .fontWeight(.medium)

                if let location = plan.location_text {
                    HStack(spacing: 4) {
                        Image(systemName: "location.fill")
                            .font(.caption2)
                        Text(location)
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                }

                // Show actual start date/time
                HStack(spacing: 4) {
                    Image(systemName: "calendar")
                        .font(.caption2)
                    Text(plan.start_at.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text(countdown)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)

                Text("until start")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(Color(.tertiarySystemBackground))
        .cornerRadius(12)
    }

    private func formatCountdown(_ interval: TimeInterval) -> String {
        let days = Int(interval) / 86400
        let hours = (Int(interval) % 86400) / 3600
        let minutes = (Int(interval) % 3600) / 60
        let seconds = Int(interval) % 60

        if days > 0 {
            return "\(days)d \(hours)h"
        } else if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds)s"
        }
    }
}

// MARK: - History Tab View
struct HistoryTabView: View {
    @EnvironmentObject var session: Session
    @State private var plans: [PlanOut] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var loadTask: Task<Void, Never>?

    var body: some View {
        NavigationStack {
            Group {
                if isLoading && plans.isEmpty {
                    ProgressView("Loading history...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if plans.isEmpty && !isLoading {
                    EmptyHistoryView()
                } else {
                    List {
                        // Stats Section
                        Section {
                            TripStatsView(plans: plans)
                        }
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                        .listRowBackground(Color.clear)

                        // Trips List
                        Section {
                            ForEach(plans) { plan in
                                HistoryRowView(plan: plan)
                                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                                    .listRowBackground(Color.clear)
                            }
                            .onDelete(perform: deletePlans)
                        }
                    }
                    .listStyle(.plain)
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
            .onDisappear {
                loadTask?.cancel()
            }
        }
    }

    func loadHistory() async {
        // Cancel any existing load task
        loadTask?.cancel()

        // Create new task
        loadTask = Task {
            guard !Task.isCancelled else { return }

            await MainActor.run {
                isLoading = true
                errorMessage = nil
            }

            do {
                let loadedPlans: [PlanOut] = try await session.api.get(
                    session.url("/api/v1/trips/"),
                    bearer: session.accessToken
                )

                // Check if task was cancelled before updating UI
                guard !Task.isCancelled else { return }

                await MainActor.run {
                    // Sort by most recent first
                    self.plans = loadedPlans.sorted { $0.start_at > $1.start_at }
                    self.isLoading = false
                }
            } catch {
                // Only show error if not cancelled
                if !Task.isCancelled {
                    let errorText = error.localizedDescription
                    if !errorText.contains("cancelled") {
                        await MainActor.run {
                            errorMessage = "Failed to load history: \(errorText)"
                            isLoading = false
                        }
                    } else {
                        await MainActor.run {
                            isLoading = false
                        }
                    }
                }
            }
        }
    }

    func deletePlans(at offsets: IndexSet) {
        Task {
            for index in offsets {
                let plan = plans[index]

                // Call delete endpoint
                do {
                    struct DeleteResponse: Decodable {
                        let ok: Bool
                        let message: String
                    }

                    let _: DeleteResponse = try await session.api.delete(
                        session.url("/api/v1/trips/\(plan.id)"),
                        bearer: session.accessToken
                    )

                    // Remove from local list on successful delete
                    await MainActor.run {
                        plans.remove(atOffsets: offsets)
                    }
                } catch {
                    await MainActor.run {
                        errorMessage = "Failed to delete plan: \(error.localizedDescription)"
                    }
                }
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

    var activity: ActivityType {
        // Try exact match first
        if let matched = ActivityType(rawValue: plan.activity_type.lowercased()) {
            return matched
        }

        // Try converting spaces to underscores and lowercasing
        let normalized = plan.activity_type.lowercased().replacingOccurrences(of: " ", with: "_")
        return ActivityType(rawValue: normalized) ?? .other
    }

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

    var statusText: String {
        switch plan.status {
        case "completed": return "Completed"
        case "cancelled": return "Cancelled"
        case "overdue": return "Overdue"
        case "planned": return "Planned"
        case "active": return "Active"
        default: return plan.status.capitalized
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                // Activity icon with colored background
                Circle()
                    .fill(activity.primaryColor.opacity(0.2))
                    .frame(width: 50, height: 50)
                    .overlay(
                        Text(activity.icon)
                            .font(.title2)
                    )

                // Title and activity
                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .lineLimit(2)

                    Text(activity.displayName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Status indicator
                VStack(spacing: 2) {
                    Image(systemName: statusIcon)
                        .font(.title3)
                        .foregroundStyle(statusColor)

                    Text(statusText)
                        .font(.caption2)
                        .fontWeight(.medium)
                        .foregroundStyle(statusColor)
                }
            }

            // Time details section
            VStack(alignment: .leading, spacing: 8) {
                // Start time
                HStack(spacing: 6) {
                    Image(systemName: "arrow.right.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.green)
                    Text("Start:")
                        .font(.caption)
                        .fontWeight(.medium)
                    Text(plan.start_at.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // End time
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Text("Finish:")
                        .font(.caption)
                        .fontWeight(.medium)
                    Text(plan.eta_at.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Duration
                if let duration = calculateDuration(from: plan.start_at, to: plan.eta_at) {
                    HStack(spacing: 6) {
                        Image(systemName: "clock.fill")
                            .font(.caption)
                            .foregroundStyle(.blue)
                        Text("Duration:")
                            .font(.caption)
                            .fontWeight(.medium)
                        Text(duration)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Location
                if let location = plan.location_text {
                    HStack(spacing: 6) {
                        Image(systemName: "location.fill")
                            .font(.caption)
                            .foregroundStyle(.red)
                        Text("Location:")
                            .font(.caption)
                            .fontWeight(.medium)
                        Text(location)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }
            .padding(.leading, 62) // Align with title
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    func calculateDuration(from start: Date, to end: Date) -> String? {
        let interval = end.timeIntervalSince(start)
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m"
        }
        return nil
    }
}

// MARK: - Trip Stats View
struct TripStatsView: View {
    let plans: [PlanOut]

    var totalTrips: Int {
        plans.count
    }

    var completedTrips: Int {
        plans.filter { $0.status == "completed" }.count
    }

    var totalAdventureTime: String {
        let totalSeconds = plans.reduce(0.0) { total, plan in
            total + plan.eta_at.timeIntervalSince(plan.start_at)
        }
        let hours = Int(totalSeconds) / 3600
        let days = hours / 24

        if days > 0 {
            return "\(days)d \(hours % 24)h"
        } else if hours > 0 {
            return "\(hours)h"
        } else {
            return "\(Int(totalSeconds) / 60)m"
        }
    }

    var favoriteActivity: (icon: String, name: String, count: Int)? {
        let activityCounts = Dictionary(grouping: plans) { plan in
            plan.activity_type
        }.mapValues { $0.count }

        guard let mostCommon = activityCounts.max(by: { $0.value < $1.value }) else {
            return nil
        }

        let activity = ActivityType(rawValue: mostCommon.key) ?? .other
        return (activity.icon, activity.displayName, mostCommon.value)
    }

    var completionRate: Int {
        guard totalTrips > 0 else { return 0 }
        return Int((Double(completedTrips) / Double(totalTrips)) * 100)
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Your Adventure Stats")
                    .font(.headline)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                Spacer()
            }

            // Stats Grid
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                // Total Trips
                StatCardImproved(
                    value: "\(totalTrips)",
                    label: "Total Trips",
                    icon: "map.fill",
                    color: Color(hex: "#6C63FF") ?? .purple
                )

                // Completed Trips
                StatCardImproved(
                    value: "\(completedTrips)",
                    label: "Completed",
                    icon: "checkmark.circle.fill",
                    color: .green
                )

                // Total Adventure Time
                StatCardImproved(
                    value: totalAdventureTime,
                    label: "Adventure Time",
                    icon: "clock.fill",
                    color: .orange
                )

                // Completion Rate
                StatCardImproved(
                    value: "\(completionRate)%",
                    label: "Success Rate",
                    icon: "chart.line.uptrend.xyaxis",
                    color: Color(hex: "#4ECDC4") ?? .teal
                )
            }

            // Favorite Activity (if available)
            if let favorite = favoriteActivity {
                HStack(spacing: 12) {
                    Circle()
                        .fill(Color(hex: "#6C63FF")?.opacity(0.2) ?? .purple.opacity(0.2))
                        .frame(width: 44, height: 44)
                        .overlay(
                            Text(favorite.icon)
                                .font(.title3)
                        )

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Favorite Activity")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(favorite.name)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }

                    Spacer()

                    Text("\(favorite.count) trips")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color(hex: "#6C63FF")?.opacity(0.1) ?? .purple.opacity(0.1))
                        .cornerRadius(8)
                }
                .padding()
                .background(Color(.tertiarySystemBackground))
                .cornerRadius(12)
            }
        }
    }
}

// MARK: - Improved Stat Card
struct StatCardImproved: View {
    let value: String
    let label: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)

            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(.primary)

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

#Preview {
    MainTabView()
        .environmentObject(Session())
}