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

            // Map Tab
            TripMapView()
                .tabItem {
                    Label("Map", systemImage: "map.fill")
                }
                .tag(2)
        }
        .accentColor(Color.hbBrand)
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
                // Plain background - adapts to system light/dark mode
                Color(.systemBackground)
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
                                            colors: [Color.hbBrand, Color.hbTeal],
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
                                            colors: [Color.hbBrand, Color.hbTeal],
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
                        if let activeTrip = session.activeTrip {
                            // Show active plan card instead of new trip card
                            ActivePlanCardCompact(plan: activeTrip, timeline: $timeline)
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
                                colors: [Color.hbBrand, Color.hbTeal],
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
                    .background(Color.hbAccent)
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
                .foregroundStyle(Color.hbBrand)
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
    let plan: Trip
    @Binding var timeline: [TimelineEvent]
    @EnvironmentObject var session: Session
    @State private var timeRemaining = ""
    @State private var isOverdue = false
    @State private var isPerformingAction = false
    @State private var showingExtendOptions = false
    @State private var selectedExtendMinutes = 30
    @State private var appeared = false

    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    let extendOptions = [
        (15, "15 min"),
        (30, "30 min"),
        (60, "1 hr"),
        (120, "2 hrs"),
        (180, "3 hrs")
    ]

    var body: some View {
        VStack(spacing: 20) {
            // Status badge with pulse animation
            HStack {
                Circle()
                    .fill(isOverdue ? Color.red : Color.green)
                    .frame(width: 12, height: 12)
                    .overlay(
                        Circle()
                            .stroke(isOverdue ? Color.red : Color.green, lineWidth: 2)
                            .scaleEffect(isOverdue ? 1.4 : 1.0)
                            .opacity(isOverdue ? 0.0 : 1.0)
                            .animation(.easeOut(duration: 1.5).repeatForever(autoreverses: false), value: isOverdue)
                    )

                Text(isOverdue ? "OVERDUE" : "ACTIVE TRIP")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundStyle(.white.opacity(0.9))

                Spacer()
            }

            // Plan info with activity icon
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 12) {
                    // Activity icon
                    Text(plan.activity.icon)
                        .font(.system(size: 32))

                    VStack(alignment: .leading, spacing: 4) {
                        Text(plan.title)
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundStyle(.white)

                        Text(plan.activity.name)
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundStyle(.white.opacity(0.7))
                    }

                    Spacer()
                }

                if let location = plan.location_text {
                    HStack {
                        Image(systemName: "location.fill")
                            .font(.caption)
                        Text(location)
                            .font(.subheadline)
                    }
                    .foregroundStyle(.white.opacity(0.8))
                }

                // Time remaining
                VStack(alignment: .leading, spacing: 4) {
                    Text("Expected return")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.7))
                    Text(timeRemaining)
                        .font(.title3)
                        .fontWeight(.semibold)
                        .foregroundStyle(isOverdue ? Color.red.opacity(0.9) : .white)
                }
            }

            // Action buttons with haptic feedback
            HStack(spacing: 12) {
                // Check-in button
                Button(action: {
                    let impact = UIImpactFeedbackGenerator(style: .medium)
                    impact.impactOccurred()

                    if let token = plan.checkin_token {
                        Task {
                            isPerformingAction = true
                            await session.performTokenAction(token, action: "checkin")

                            // Success haptic
                            let success = UINotificationFeedbackGenerator()
                            success.notificationOccurred(.success)

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
                        .background(Color.green.opacity(0.9))
                        .cornerRadius(12)
                        .shadow(color: Color.green.opacity(0.3), radius: 8, y: 4)
                }
                .disabled(plan.checkin_token == nil || isPerformingAction)

                // I'm safe button
                Button(action: {
                    let impact = UIImpactFeedbackGenerator(style: .medium)
                    impact.impactOccurred()

                    if let token = plan.checkout_token {
                        Task {
                            isPerformingAction = true
                            await session.performTokenAction(token, action: "checkout")

                            // Success haptic with confetti effect
                            let success = UINotificationFeedbackGenerator()
                            success.notificationOccurred(.success)

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
                        .background(Color.hbAccent)
                        .cornerRadius(12)
                        .shadow(color: Color.hbAccent.opacity(0.3), radius: 8, y: 4)
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
                            .foregroundStyle(.white.opacity(0.7))

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(extendOptions, id: \.0) { minutes, label in
                                    Button(action: {
                                        let impact = UIImpactFeedbackGenerator(style: .light)
                                        impact.impactOccurred()

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
                                            .padding(.horizontal, 12)
                                            .padding(.vertical, 8)
                                            .glassmorphicButton(cornerRadius: 8)
                                    }
                                }
                            }
                            .padding(.horizontal, 2)
                        }
                    }
                    .transition(.scale.combined(with: .opacity))
                } else {
                    Button(action: {
                        let impact = UIImpactFeedbackGenerator(style: .light)
                        impact.impactOccurred()

                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            showingExtendOptions = true
                        }
                    }) {
                        Label("Extend Time", systemImage: "clock.arrow.circlepath")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundStyle(.white.opacity(0.9))
                    }
                }
            }

            // Safety Tips Carousel
            SafetyTipsCarousel(safetyTips: plan.activity.safety_tips)
        }
        .padding(24)
        .glassmorphic(cornerRadius: 32, borderOpacity: 0.0)
        // Prominent glow effect using activity's primary color
        .shadow(
            color: Color(hex: plan.activity.colors.primary)?.opacity(0.4) ?? .clear,
            radius: 20,
            y: 10
        )
        .shadow(
            color: Color(hex: plan.activity.colors.primary)?.opacity(0.6) ?? .clear,
            radius: 12,
            y: 6
        )
        .opacity(appeared ? 1.0 : 0.0)
        .offset(y: appeared ? 0 : 20)
        .onReceive(timer) { _ in
            updateTimeRemaining()
        }
        .onAppear {
            updateTimeRemaining()
            withAnimation(.easeOut(duration: 0.5)) {
                appeared = true
            }
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
    @State private var upcomingPlans: [Trip] = []
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
    let plan: Trip
    let currentTime: Date

    var activity: ActivityTypeAdapter {
        ActivityTypeAdapter(activity: plan.activity)
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
                    .foregroundStyle(Color.hbBrand)

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
    @State private var plans: [Trip] = []
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
                let loadedPlans: [Trip] = try await session.api.get(
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
                print("[MainTabView] ❌ Failed to load trips: \(error)")
                if let decodingError = error as? DecodingError {
                    switch decodingError {
                    case .typeMismatch(let type, let context):
                        print("[MainTabView] Type mismatch: \(type) at \(context.codingPath)")
                        print("[MainTabView] Debug: \(context.debugDescription)")
                    case .valueNotFound(let type, let context):
                        print("[MainTabView] Value not found: \(type) at \(context.codingPath)")
                        print("[MainTabView] Debug: \(context.debugDescription)")
                    case .keyNotFound(let key, let context):
                        print("[MainTabView] Key not found: \(key) at \(context.codingPath)")
                        print("[MainTabView] Debug: \(context.debugDescription)")
                    case .dataCorrupted(let context):
                        print("[MainTabView] Data corrupted at \(context.codingPath)")
                        print("[MainTabView] Debug: \(context.debugDescription)")
                    @unknown default:
                        print("[MainTabView] Unknown decoding error: \(decodingError)")
                    }
                }

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
    let plan: Trip

    var activity: ActivityTypeAdapter {
        ActivityTypeAdapter(activity: plan.activity)
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

                // End time - show actual completion time for completed trips
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Text("Finish:")
                        .font(.caption)
                        .fontWeight(.medium)

                    // For completed trips, show actual completion time; otherwise show ETA
                    if plan.status == "completed", let completedAtStr = plan.completed_at,
                       let completedDate = DateUtils.parseDate(completedAtStr) {
                        Text(completedDate.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text(plan.eta_at.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Duration
                if let duration = DateUtils.formatDuration(from: plan.start_at, to: plan.eta_at) {
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

}

// MARK: - Trip Stats View
struct TripStatsView: View {
    let plans: [Trip]
    @State private var preferences = StatsPreferences.load()
    @State private var showingEditStats = false
    @State private var animatedValues: [StatType: Double] = [:]

    var calculator: TripStatsCalculator {
        TripStatsCalculator(trips: plans)
    }

    var favoriteActivity: (icon: String, name: String, count: Int)? {
        let activityCounts = Dictionary(grouping: plans) { plan in
            plan.activity.id
        }

        guard let mostCommon = activityCounts.max(by: { $0.value.count < $1.value.count }) else {
            return nil
        }

        let activity = mostCommon.value.first!.activity
        return (activity.icon, activity.name, mostCommon.value.count)
    }

    var useScrolling: Bool {
        preferences.selectedStats.count > 4
    }

    var body: some View {
        VStack(spacing: 12) {
            // Header with Edit button
            HStack {
                Text("Your Adventure Stats")
                    .font(.headline)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.hbBrand, Color.hbTeal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                Spacer()
                Button(action: { showingEditStats = true }) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.title3)
                        .foregroundStyle(Color.hbBrand)
                }
            }

            // Stats Grid or Scrolling
            if useScrolling {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(Array(preferences.selectedStats.enumerated()), id: \.element) { index, statType in
                            AnimatedStatCard(
                                statType: statType,
                                value: calculator.value(for: statType),
                                badge: calculator.achievementBadge(for: statType),
                                delay: Double(index) * 0.1
                            )
                            .frame(width: 140)
                        }
                    }
                }
            } else {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ForEach(Array(preferences.selectedStats.enumerated()), id: \.element) { index, statType in
                        AnimatedStatCard(
                            statType: statType,
                            value: calculator.value(for: statType),
                            badge: calculator.achievementBadge(for: statType),
                            delay: Double(index) * 0.1
                        )
                    }
                }
            }

            // Favorite Activity (if available)
            if let favorite = favoriteActivity {
                HStack(spacing: 12) {
                    Circle()
                        .fill(Color.hbBrand.opacity(0.2))
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
                        .foregroundStyle(Color.hbBrand)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.hbBrand.opacity(0.1))
                        .cornerRadius(8)
                }
                .padding()
                .background(Color(.tertiarySystemBackground))
                .cornerRadius(12)
                .transition(.scale.combined(with: .opacity))
            }
        }
        .sheet(isPresented: $showingEditStats) {
            EditStatsView(preferences: $preferences)
        }
    }
}

// MARK: - Animated Stat Card
struct AnimatedStatCard: View {
    let statType: StatType
    let value: String
    let badge: String?
    let delay: Double

    @State private var appeared = false
    @State private var scale: CGFloat = 0.8

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                // Icon
                Image(systemName: statType.icon)
                    .font(.title2)
                    .foregroundStyle(statType.color)

                // Achievement badge
                if let badge = badge {
                    Text(badge)
                        .font(.caption)
                        .offset(x: 20, y: -20)
                        .scaleEffect(appeared ? 1.2 : 0)
                        .animation(.spring(response: 0.5, dampingFraction: 0.6).delay(delay + 0.3), value: appeared)
                }
            }

            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(.primary)
                .opacity(appeared ? 1 : 0)

            Text(statType.displayName)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(
            LinearGradient(
                colors: [
                    statType.color.opacity(0.1),
                    statType.color.opacity(0.05)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .cornerRadius(12)
        .scaleEffect(scale)
        .onAppear {
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7).delay(delay)) {
                appeared = true
                scale = 1.0
            }
        }
    }
}

// MARK: - Edit Stats View
struct EditStatsView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var preferences: StatsPreferences
    @State private var selectedStats: [StatType]

    init(preferences: Binding<StatsPreferences>) {
        self._preferences = preferences
        self._selectedStats = State(initialValue: preferences.wrappedValue.selectedStats)
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Select up to 8 stats to display on your Adventure Stats dashboard")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Customize Your Stats")
                }

                Section {
                    ForEach(StatType.allCases, id: \.self) { statType in
                        HStack {
                            Image(systemName: statType.icon)
                                .foregroundStyle(statType.color)
                                .frame(width: 24)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(statType.displayName)
                                    .font(.subheadline)

                                Text(getStatDescription(statType))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            if selectedStats.contains(statType) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(statType.color)
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            toggleStat(statType)
                        }
                    }
                } header: {
                    Text("Available Stats (\(selectedStats.count)/8)")
                }

                Section {
                    Button("Reset to Default") {
                        selectedStats = StatsPreferences.defaultStats
                    }
                    .foregroundStyle(.red)
                }
            }
            .navigationTitle("Edit Stats")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        savePreferences()
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .disabled(selectedStats.isEmpty)
                }
            }
        }
    }

    func toggleStat(_ statType: StatType) {
        if selectedStats.contains(statType) {
            selectedStats.removeAll { $0 == statType }
        } else if selectedStats.count < 8 {
            selectedStats.append(statType)
        }
    }

    func savePreferences() {
        preferences.selectedStats = selectedStats
        preferences.save()
    }

    func getStatDescription(_ statType: StatType) -> String {
        switch statType {
        case .totalTrips: return "Total number of adventures"
        case .adventureTime: return "Total time on all trips"
        case .longestAdventure: return "Your longest single trip"
        case .activitiesTried: return "Different activity types"
        case .thisMonth: return "Trips this month"
        case .uniqueLocations: return "Different places visited"
        case .mostAdventurousMonth: return "Month with most trips"
        case .averageTripDuration: return "Average trip length"
        }
    }
}

#Preview {
    MainTabView()
        .environmentObject(Session())
}