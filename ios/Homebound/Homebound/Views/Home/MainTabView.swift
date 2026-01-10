import SwiftUI
import Combine
import MapKit

// MARK: - Main Tab View with Dock Navigation
struct MainTabView: View {
    @EnvironmentObject var session: Session
    @State private var selectedTab = 0
    @State private var showPaywall = false

    var body: some View {
        TabView(selection: $selectedTab) {
            // Home Tab
            NewHomeView()
                .tabItem {
                    Label("Home", systemImage: "house.fill")
                }
                .tag(0)

            // History Tab
            HistoryView(showAsTab: true, showStats: true)
                .tabItem {
                    Label("History", systemImage: "clock.fill")
                }
                .tag(1)

            // Friends Tab
            FriendsTabView()
                .tabItem {
                    Label("Friends", systemImage: "person.2.fill")
                }
                .tag(2)
                .badge(session.tripInvitations.count)

            // Map Tab (Premium Feature)
            Group {
                if session.canUse(feature: .tripMap) {
                    TripMapView()
                } else {
                    LockedTripMapView(showPaywall: $showPaywall)
                }
            }
            .tabItem {
                Label("Map", systemImage: "map.fill")
            }
            .tag(3)
        }
        .accentColor(Color.hbBrand)
        .onChange(of: selectedTab) { oldValue, newValue in
            if newValue == 2 { // Friends tab
                NotificationCenter.default.post(name: .friendsTabSelected, object: nil)
            }
        }
        .sheet(isPresented: $showPaywall) {
            PaywallView()
                .environmentObject(session)
        }
    }
}

// MARK: - Locked Trip Map View (Premium Feature)
struct LockedTripMapView: View {
    @Binding var showPaywall: Bool

    var body: some View {
        ZStack {
            // Blurred map background
            Map()
                .blur(radius: 10)
                .allowsHitTesting(false)

            // Overlay with lock content
            VStack(spacing: 20) {
                // Lock icon
                ZStack {
                    Circle()
                        .fill(Color.hbBrand.opacity(0.15))
                        .frame(width: 80, height: 80)

                    Image(systemName: "lock.fill")
                        .font(.system(size: 32))
                        .foregroundStyle(Color.hbBrand)
                }

                VStack(spacing: 8) {
                    Text("Trip Map")
                        .font(.title2)
                        .fontWeight(.bold)

                    Text("See all your adventures on an interactive map")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                }

                // Premium badge
                HStack(spacing: 4) {
                    Image("Logo")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 20, height: 20)
                    Text("PLUS")
                        .font(.caption)
                        .fontWeight(.bold)
                }
                .foregroundStyle(Color.hbBrand)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.hbBrand.opacity(0.15))
                .cornerRadius(8)

                // Upgrade button
                Button(action: { showPaywall = true }) {
                    Text("Unlock Trip Map")
                        .font(.headline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(
                            LinearGradient(
                                colors: [Color.hbBrand, Color.hbTeal],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .cornerRadius(12)
                }
                .padding(.horizontal, 32)
            }
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 24)
                    .fill(.ultraThinMaterial)
            )
            .padding(24)
        }
    }
}

// MARK: - Offline Status Banner
struct OfflineStatusBanner: View {
    @EnvironmentObject var session: Session
    @ObservedObject private var networkMonitor = NetworkMonitor.shared

    var isVisible: Bool {
        !networkMonitor.isConnected || session.pendingActionsCount > 0
    }

    var body: some View {
        if isVisible {
            HStack(spacing: 10) {
                if !networkMonitor.isConnected {
                    Image(systemName: "wifi.slash")
                        .font(.subheadline)
                    Text("Offline Mode")
                        .font(.subheadline)
                        .fontWeight(.medium)
                } else if session.pendingActionsCount > 0 {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Syncing \(session.pendingActionsCount) action\(session.pendingActionsCount == 1 ? "" : "s")...")
                        .font(.subheadline)
                        .fontWeight(.medium)
                }

                Spacer()

                if session.pendingActionsCount > 0 && !networkMonitor.isConnected {
                    Text("\(session.pendingActionsCount)")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Circle().fill(Color.orange))
                }
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(!networkMonitor.isConnected ? Color.orange : Color.blue)
            )
            .transition(.move(edge: .top).combined(with: .opacity))
        }
    }
}

// MARK: - New Home View with Big Trip Card
struct NewHomeView: View {
    @EnvironmentObject var session: Session
    @EnvironmentObject var preferences: AppPreferences
    @StateObject private var achievementManager = AchievementNotificationManager.shared
    @State private var showingCreatePlan = false
    @State private var showingSettings = false
    @State private var showingAchievements = false
    @State private var showingCelebration = false
    @State private var greeting = "Good morning"
    @State private var timeline: [TimelineEvent] = []
    @State private var refreshID = UUID()
    @State private var lastSyncTime: Date?
    private let syncDebounceInterval: TimeInterval = 2.0  // Minimum 2 seconds between syncs

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

                            HStack(spacing: 12) {
                                // Achievements button with notification dot
                                Button(action: {
                                    if achievementManager.hasUnseenAchievements {
                                        showingCelebration = true
                                    } else {
                                        showingAchievements = true
                                    }
                                }) {
                                    ZStack(alignment: .topTrailing) {
                                        Circle()
                                            .fill(Color.orange.opacity(0.15))
                                            .frame(width: 44, height: 44)
                                            .overlay(
                                                Image(systemName: "trophy.fill")
                                                    .foregroundStyle(.orange)
                                                    .font(.system(size: 20))
                                            )

                                        // Red notification dot
                                        if achievementManager.hasUnseenAchievements {
                                            Circle()
                                                .fill(Color.red)
                                                .frame(width: 12, height: 12)
                                                .offset(x: 2, y: -2)
                                        }
                                    }
                                }

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
                        }
                        .padding(.horizontal)
                        .padding(.top, 8)

                        // Offline status banner
                        OfflineStatusBanner()
                            .padding(.horizontal)
                            .animation(.spring(response: 0.3), value: session.pendingActionsCount)

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

                        // Upcoming Trips Section (respects user preference)
                        if preferences.showUpcomingTrips {
                            UpcomingTripsSection()
                                .padding(.horizontal)
                                .id(refreshID)
                        }
                    }
                    .padding(.bottom, 100)
                }
                .scrollIndicators(.hidden)
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showingCreatePlan) {
                TripStartView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
                    .environmentObject(session)
                    .environmentObject(AppPreferences.shared)
                    .preferredColorScheme(preferences.colorScheme.colorScheme)
            }
            .sheet(isPresented: $showingAchievements) {
                AchievementsView()
                    .environmentObject(session)
            }
            .fullScreenCover(isPresented: $showingCelebration) {
                AchievementCelebrationView(
                    achievements: achievementManager.unseenAchievements,
                    onDismiss: {
                        achievementManager.markAllAsSeen()
                        showingCelebration = false
                        // Optionally show full achievements view after celebration
                        showingAchievements = true
                    }
                )
            }
            .task {
                updateGreeting()
                // Sync all data on app open
                await syncData()
                // Check for new achievements after data sync
                achievementManager.checkForNewAchievements(trips: session.allTrips)
            }
            .onChange(of: session.activeTrip?.id) { oldId, newId in
                // Clear timeline when active trip changes to prevent stale data display
                if oldId != newId {
                    timeline = []
                    // If there's a new active trip, reload its timeline
                    if let tripId = newId {
                        Task {
                            let events = await session.loadTimeline(planId: tripId)
                            await MainActor.run {
                                self.timeline = events
                            }
                        }
                    }
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
                Task {
                    // Sync when app comes to foreground
                    await syncData()
                    // Check for new achievements after sync
                    achievementManager.checkForNewAchievements(trips: session.allTrips)
                }
            }
        }
    }

    func updateGreeting() {
        let hour = Calendar.current.component(.hour, from: Date())
        greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
    }

    func syncData() async {
        // Debounce: skip if we synced recently
        // Use a single Date instance to avoid timing gaps between check and set
        let now = Date()
        if let lastSync = lastSyncTime,
           now.timeIntervalSince(lastSync) < syncDebounceInterval {
            debugLog("[NewHomeView] Skipping syncData - debounced (last sync: \(now.timeIntervalSince(lastSync))s ago)")
            return
        }
        lastSyncTime = now

        // Load all necessary data in parallel
        // Bug 3 fix: Check protection window before loading active plan to prevent overwriting local trip updates
        async let loadProfile: Void = session.loadUserProfile()
        async let loadTrips: [Trip] = session.loadAllTrips()  // Also load all trips for upcoming section

        // Conditionally load active plan based on protection window
        if session.shouldLoadActivePlan() {
            async let loadActive: Void = session.loadActivePlan()
            _ = await (loadActive, loadProfile, loadTrips)
        } else {
            _ = await (loadProfile, loadTrips)
        }

        // Load timeline for active trip
        if let tripId = session.activeTrip?.id {
            let events = await session.loadTimeline(planId: tripId)
            await MainActor.run {
                self.timeline = events
            }
        }

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

                    Image("Logo")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 100, height: 100)
                }

                // Title
                VStack(spacing: 8) {
                    Text("Start a New Trip")
                        .font(.title2)
                        .fontWeight(.bold)

                    // Text("Let someone know where you're going")
                    //     .font(.subheadline)
                    //     .foregroundStyle(.secondary)
                    //     .multilineTextAlignment(.center)
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

/// MARK: - Feature Row
struct FeatureRow: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundStyle(Color.hbBrand)
                .frame(width: 24)
                .accessibilityHidden(true)  // Icon is decorative, text provides meaning

            Text(text)
                .font(.subheadline)
                .foregroundStyle(.primary)

            Spacer()
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(text)
    }
}

// MARK: - Trip Time State
enum TripTimeState {
    case onTime          // Before ETA - countdown to expected return
    case graceWarning    // After ETA but before grace period ends - warning state
    case overdue         // After grace period ends - contacts notified
}

// MARK: - Active Plan Card Compact
struct ActivePlanCardCompact: View {
    let plan: Trip
    @Binding var timeline: [TimelineEvent]
    @EnvironmentObject var session: Session
    @EnvironmentObject var preferences: AppPreferences
    @State private var timeRemaining = ""
    @State private var timeState: TripTimeState = .onTime
    @State private var isPerformingAction = false
    @State private var showingExtendOptions = false
    @State private var selectedExtendMinutes = 30
    @State private var pulseAnimation = false
    @State private var showingError = false
    @State private var errorMessage = ""
    @State private var showPaywall = false
    // Checkout voting state (for group trips)
    @State private var showingVoteConfirmation = false
    @State private var voteResponse: CheckoutVoteResponse? = nil
    // Group trip checkout confirmation
    @State private var showingGroupCheckoutConfirmation = false

    /// All available extension options
    let allExtendOptions = [
        (15, "15 min"),
        (30, "30 min"),
        (60, "1 hr"),
        (120, "2 hrs"),
        (180, "3 hrs")
    ]

    /// Check if an extension time is available for the user
    func isExtensionAvailable(_ minutes: Int) -> Bool {
        session.featureLimits.extensions.contains(minutes)
    }

    /// Returns the current trip from session (live updates) or falls back to the initial plan parameter.
    /// This ensures the timer always uses the latest ETA even after extensions.
    private var liveTrip: Trip {
        session.activeTrip ?? plan
    }

    var statusColor: Color {
        switch timeState {
        case .onTime: return .green
        case .graceWarning: return .orange
        case .overdue: return .red
        }
    }

    var statusText: String {
        switch timeState {
        case .onTime: return "ACTIVE TRIP"
        case .graceWarning: return "CHECK IN NOW"
        case .overdue: return "OVERDUE"
        }
    }

    var urgentMessage: String {
        switch timeState {
        case .onTime: return ""
        case .graceWarning: return "You're past your expected return time. Check in or your contacts will be notified!"
        case .overdue: return "Your emergency contacts have been notified. Please check in immediately!"
        }
    }

    var isUrgent: Bool {
        timeState != .onTime
    }

    var urgentIcon: String {
        timeState == .overdue ? "exclamationmark.triangle.fill" : "exclamationmark.circle.fill"
    }

    var statusBadgeSize: CGFloat {
        timeState == .onTime ? 12 : 16
    }

    var statusFont: Font {
        timeState == .onTime ? .caption : .subheadline
    }

    var statusForeground: Color {
        timeState == .onTime ? .primary : statusColor
    }

    var bannerOpacity: Double {
        0.8
    }

    var borderOpacity: Double {
        0.75
    }

    // Check-in tracking computed properties
    var checkinEvents: [TimelineEvent] {
        timeline.filter { $0.kind == "checkin" }
    }

    var checkinCount: Int {
        checkinEvents.count
    }

    var lastCheckinTime: Date? {
        checkinEvents.compactMap(\.atDate).max()
    }

    /// Get the most recent check-in event (for displaying who checked in)
    var lastCheckinEvent: TimelineEvent? {
        checkinEvents.max(by: { ($0.atDate ?? .distantPast) < ($1.atDate ?? .distantPast) })
    }

    /// Format the "by USER" text for the last check-in
    var lastCheckinByText: String? {
        guard let event = lastCheckinEvent else { return nil }

        debugLog("[MainTabView] Last check-in: user_id=\(String(describing: event.user_id)), user_name=\(String(describing: event.user_name)), session.userId=\(String(describing: session.userId))")

        // Check if it's the current user
        if let eventUserId = event.user_id, let currentUserId = session.userId, eventUserId == currentUserId {
            return "by you"
        }

        // Use the user name from the event
        if let userName = event.user_name, !userName.isEmpty {
            // Just use first name for brevity
            let firstName = userName.components(separatedBy: " ").first ?? userName
            return "by \(firstName)"
        }

        return nil
    }

    /// Check if the current user is the trip owner
    var isOwner: Bool {
        guard let userId = session.userId else { return true } // Assume owner if no userId yet
        return plan.user_id == userId
    }

    func relativeTimeString(from date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    var body: some View {
        VStack(spacing: isUrgent ? 16 : 20) {
            // Urgent warning banner for overdue/warning states
            if isUrgent {
                urgentBannerView
            }

            // Status badge with pulse animation
            statusBadgeView

            // Plan info with activity icon
            planInfoView

            // Check-in info (count and last check-in)
            checkinInfoView

            // Action buttons with haptic feedback
            actionButtonsView

            // Extend time section
            extendTimeView

            // Safety Tips Carousel - hide when urgent to focus on action
            if !isUrgent {
                SafetyTipsCarousel(safetyTips: plan.activity.safety_tips)
            }
        }
        .padding(24)
        .glassmorphic(cornerRadius: 32, borderOpacity: 0.0)
        // Urgent pulsing border for overdue/warning states
        .overlay(
            RoundedRectangle(cornerRadius: 32)
                .stroke(
                    isUrgent ? statusColor : Color.clear,
                    lineWidth: isUrgent ? 3 : 0
                )
                .opacity(borderOpacity)
        )
        // Glow effect - red for overdue, orange for warning, activity color for normal
        // Pulses when urgent
        .shadow(
            color: glowColor.opacity(isUrgent && pulseAnimation ? 0.7 : 0.5),
            radius: isUrgent ? 25 : 20,
            y: 10
        )
        .shadow(
            color: glowColor.opacity(isUrgent && pulseAnimation ? 0.9 : 0.7),
            radius: isUrgent ? 15 : 12,
            y: 6
        )
        .task {
            // Initial update
            updateTimeRemaining()
            // Start pulse animation for the dot and glow only
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                pulseAnimation = true
            }
            // Timer loop - auto-cancelled when view disappears
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                updateTimeRemaining()
            }
        }
        .alert("Action Failed", isPresented: $showingError) {
            Button("OK", role: .cancel) {
                errorMessage = ""
            }
        } message: {
            Text(errorMessage)
        }
        .alert(voteResponse?.user_has_voted == true ? "Vote Recorded" : "Vote Removed", isPresented: $showingVoteConfirmation) {
            Button("OK", role: .cancel) { }
        } message: {
            if let response = voteResponse {
                let remaining = response.votes_needed - response.votes_cast
                if response.user_has_voted == true {
                    if remaining == 1 {
                        Text("Your vote has been recorded! 1 more vote needed to end the trip.")
                    } else {
                        Text("Your vote has been recorded! \(remaining) more votes needed to end the trip.")
                    }
                } else {
                    if remaining == 1 {
                        Text("Your vote has been removed. 1 more vote needed to end the trip.")
                    } else {
                        Text("Your vote has been removed. \(remaining) more votes needed to end the trip.")
                    }
                }
            }
        }
        .onChange(of: plan.eta_at) { _, _ in
            updateTimeRemaining()
        }
        .onChange(of: session.activeTrip?.eta_at) { _, _ in
            // Session.activeTrip was updated (e.g., from extendPlan)
            // Force immediate timer update with new ETA from liveTrip
            updateTimeRemaining()
        }
        .onChange(of: session.timelineLastUpdated) { _, _ in
            // Realtime update detected - refresh timeline to update check-in count
            Task {
                let events = await session.loadTimeline(planId: plan.id)
                await MainActor.run {
                    timeline = events
                }
            }
        }
    }

    var glowColor: Color {
        switch timeState {
        case .overdue: return .red
        case .graceWarning: return .orange
        case .onTime: return Color(hex: plan.activity.colors.primary) ?? .hbBrand
        }
    }

    var urgentBannerView: some View {
        HStack(spacing: 8) {
            Image(systemName: urgentIcon)
                .font(.title2)

            Text(urgentMessage)
                .font(.subheadline)
                .fontWeight(.semibold)
                .multilineTextAlignment(.leading)

            Spacer()
        }
        .foregroundStyle(.white)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(statusColor.opacity(bannerOpacity))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(statusColor, lineWidth: 2)
                .opacity(borderOpacity)
        )
    }

    var statusBadgeView: some View {
        HStack {
            Circle()
                .fill(statusColor)
                .frame(width: statusBadgeSize, height: statusBadgeSize)
                .overlay(
                    Circle()
                        .stroke(statusColor, lineWidth: 2)
                        .scaleEffect(pulseAnimation ? 2.0 : 1.0)
                        .opacity(pulseAnimation ? 0.0 : 1.0)
                        // .animation(.easeOut(duration: 1.0).repeatForever(autoreverses: false), value: pulseAnimation)
                )
                .accessibilityHidden(true) // Status is conveyed by text, hide decorative dot

            Text(statusText)
                .font(statusFont)
                .fontWeight(.bold)
                .foregroundStyle(statusForeground)
                .accessibilityLabel("Trip status: \(statusText)")

            Spacer()

            // Bell indicator for urgent states
            if isUrgent {
                Image(systemName: "bell.fill")
                    .font(.caption)
                    .foregroundStyle(statusColor)
            }
        }
    }

    var timeLabel: String {
        switch timeState {
        case .onTime: return "Expected return in"
        case .graceWarning: return "Contacts notified in"
        case .overdue: return "Overdue by"
        }
    }

    var timeLabelFont: Font {
        isUrgent ? .subheadline : .caption
    }

    var timeLabelWeight: Font.Weight {
        isUrgent ? .semibold : .regular
    }

    var timeLabelColor: Color {
        isUrgent ? statusColor.opacity(0.9) : .secondary
    }

    var timeFont: Font {
        isUrgent ? .largeTitle : .title3
    }

    var timeColor: Color {
        switch timeState {
        case .overdue: return .red
        case .graceWarning: return .orange
        case .onTime: return .primary
        }
    }

    var planInfoView: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Text(plan.activity.icon)
                    .font(.system(size: 32))

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(plan.title)
                            .font(.title2)
                            .fontWeight(.bold)
                            .foregroundStyle(.primary)

                        // Group trip badge
                        if plan.is_group_trip {
                            HStack(spacing: 2) {
                                Image(systemName: "person.3.fill")
                                    .font(.caption2)
                                if plan.participant_count > 0 {
                                    Text("\(plan.participant_count)")
                                        .font(.caption2)
                                        .fontWeight(.medium)
                                }
                            }
                            .foregroundStyle(Color.hbBrand)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 3)
                            .background(Color.hbBrand.opacity(0.15))
                            .cornerRadius(6)
                        }
                    }

                    Text(plan.activity.name)
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
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
                .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(timeLabel)
                    .font(timeLabelFont)
                    .fontWeight(timeLabelWeight)
                    .foregroundStyle(timeLabelColor)
                Text(timeRemaining)
                    .font(timeFont)
                    .fontWeight(.bold)
                    .foregroundStyle(timeColor)
            }
        }
    }

    var actionButtonsView: some View {
        HStack(spacing: 12) {
            // Only show Check In button when NOT urgent (on time)
            if !isUrgent {
                Button(action: {
                    if preferences.hapticFeedbackEnabled {
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    }
                    Task {
                        isPerformingAction = true
                        let success = await session.checkIn()

                        if success {
                            // Reload timeline using current activeTrip (not stale reference)
                            // If trip changed during checkIn, the onChange handler will clear timeline
                            if let tripId = session.activeTrip?.id {
                                let events = await session.loadTimeline(planId: tripId)
                                await MainActor.run {
                                    self.timeline = events
                                }
                            }
                            if preferences.hapticFeedbackEnabled {
                                UINotificationFeedbackGenerator().notificationOccurred(.success)
                            }
                        } else {
                            // Show error haptic and alert on failure
                            if preferences.hapticFeedbackEnabled {
                                UINotificationFeedbackGenerator().notificationOccurred(.error)
                            }
                            await MainActor.run {
                                errorMessage = session.lastError.isEmpty ? "Check-in failed. Please try again." : session.lastError
                                showingError = true
                            }
                        }

                        // Always reset action state
                        await MainActor.run {
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
            }

            // I'm Safe / Vote to End button
            if plan.is_group_trip, let settings = plan.group_settings, settings.checkout_mode == "vote" {
                // Check if user has voted from realtime status or local response
                let hasVoted = session.activeVoteStatus?.tripId == plan.id
                    ? session.activeVoteStatus?.userHasVoted ?? false
                    : (voteResponse?.user_has_voted ?? false)

                // Group trip with vote mode - show Vote to End or Remove Vote button
                Button(action: {
                    if preferences.hapticFeedbackEnabled {
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    }
                    Task {
                        isPerformingAction = true
                        let response: CheckoutVoteResponse?
                        if hasVoted {
                            // Remove vote
                            response = await session.removeVote(tripId: plan.id)
                        } else {
                            // Cast vote
                            response = await session.voteCheckout(tripId: plan.id)
                        }

                        if let response = response {
                            await MainActor.run {
                                voteResponse = response
                            }
                            if response.trip_completed {
                                // Trip was completed by vote - reload to clear active trip
                                await session.loadActivePlan()
                                if preferences.hapticFeedbackEnabled {
                                    UINotificationFeedbackGenerator().notificationOccurred(.success)
                                }
                            } else {
                                await MainActor.run {
                                    showingVoteConfirmation = true
                                }
                                if preferences.hapticFeedbackEnabled {
                                    UINotificationFeedbackGenerator().notificationOccurred(.success)
                                }
                                // Refresh vote status to update UI
                                await session.refreshVoteStatus(tripId: plan.id)
                            }
                        } else {
                            if preferences.hapticFeedbackEnabled {
                                UINotificationFeedbackGenerator().notificationOccurred(.error)
                            }
                            await MainActor.run {
                                errorMessage = session.lastError.isEmpty ? "Action failed. Please try again." : session.lastError
                                showingError = true
                            }
                        }
                        await MainActor.run {
                            isPerformingAction = false
                        }
                    }
                }) {
                    VStack(spacing: 2) {
                        if hasVoted {
                            Label("Remove Vote", systemImage: "hand.raised.slash.fill")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        } else {
                            Label("Vote to End", systemImage: "hand.raised.fill")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                        // Show vote count from realtime updates or local response
                        if let voteStatus = session.activeVoteStatus, voteStatus.tripId == plan.id, voteStatus.votesNeeded > 0 {
                            let remaining = voteStatus.votesNeeded - voteStatus.votesCast
                            if remaining > 0 {
                                Text(remaining == 1 ? "1 more vote needed" : "\(remaining) more votes needed")
                                    .font(.caption2)
                            }
                        } else if let response = voteResponse, !response.trip_completed {
                            let remaining = response.votes_needed - response.votes_cast
                            Text(remaining == 1 ? "1 more vote needed" : "\(remaining) more votes needed")
                                .font(.caption2)
                        }
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(hasVoted ? Color.orange : Color.purple)
                    .cornerRadius(12)
                    .shadow(color: (hasVoted ? Color.orange : Color.purple).opacity(0.3), radius: 8, y: 4)
                }
                .disabled(isPerformingAction)
            } else if plan.is_group_trip, let settings = plan.group_settings, settings.checkout_mode == "owner_only" {
                // Group trip with owner_only mode - only owner can end
                if isOwner {
                    // Owner can end the trip - show confirmation first
                    Button(action: {
                        if preferences.hapticFeedbackEnabled {
                            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                        }
                        showingGroupCheckoutConfirmation = true
                    }) {
                        Label("End Trip", systemImage: "house.fill")
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
                } else {
                    // Non-owner cannot end the trip
                    HStack {
                        Image(systemName: "lock.fill")
                            .font(.caption)
                        Text("Only the trip owner can end this trip")
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                }
            } else if plan.is_group_trip {
                // Group trip with "anyone" mode - show confirmation before ending
                Button(action: {
                    if preferences.hapticFeedbackEnabled {
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    }
                    showingGroupCheckoutConfirmation = true
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
            } else {
                // Regular solo trip - show I'm Safe button directly
                Button(action: {
                    if preferences.hapticFeedbackEnabled {
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    }
                    Task {
                        isPerformingAction = true
                        _ = await session.completePlan()
                        if preferences.hapticFeedbackEnabled {
                            UINotificationFeedbackGenerator().notificationOccurred(.success)
                        }
                        await MainActor.run {
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
        }
        .disabled(isPerformingAction)
        .alert("End Group Trip", isPresented: $showingGroupCheckoutConfirmation) {
            Button("End Trip", role: .destructive) {
                Task {
                    isPerformingAction = true
                    _ = await session.completePlan()
                    if preferences.hapticFeedbackEnabled {
                        UINotificationFeedbackGenerator().notificationOccurred(.success)
                    }
                    await MainActor.run {
                        isPerformingAction = false
                    }
                }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This will end the trip for all \(plan.participant_count) participants. Are you sure?")
        }
        .sheet(isPresented: $showPaywall) {
            PaywallView(feature: .allExtensions)
        }
    }

    @ViewBuilder
    var extendTimeView: some View {
        if showingExtendOptions {
            VStack(spacing: 8) {
                Text("Extend trip by:")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(allExtendOptions, id: \.0) { minutes, label in
                            let isAvailable = isExtensionAvailable(minutes)
                            Button(action: {
                                if isAvailable {
                                    if preferences.hapticFeedbackEnabled {
                                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                    }
                                    Task {
                                        isPerformingAction = true
                                        _ = await session.extendPlan(minutes: minutes)
                                        await MainActor.run {
                                            showingExtendOptions = false
                                            isPerformingAction = false
                                        }
                                    }
                                } else {
                                    showPaywall = true
                                }
                            }) {
                                HStack(spacing: 4) {
                                    Text(label)
                                        .font(.caption)
                                        .fontWeight(.medium)
                                    if !isAvailable {
                                        Image(systemName: "lock.fill")
                                            .font(.caption2)
                                    }
                                }
                                .foregroundStyle(isAvailable ? .primary : .secondary)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 8)
                                .glassmorphicButton(cornerRadius: 8)
                                .opacity(isAvailable ? 1 : 0.6)
                            }
                        }
                    }
                    .padding(.horizontal, 2)
                }
            }
        } else {
            // Show "Extend Time" text link for all states
            Button(action: {
                if preferences.hapticFeedbackEnabled {
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                }
                showingExtendOptions = true
            }) {
                Label("Extend Time", systemImage: "clock.arrow.circlepath")
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    var checkinInfoView: some View {
        if checkinCount > 0, let lastCheckin = lastCheckinTime {
            HStack {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle")
                        .font(.caption)
                    Text("\(checkinCount) check-in\(checkinCount == 1 ? "" : "s")")
                        .font(.caption)
                }
                .foregroundStyle(.secondary)

                Spacer()

                if let byText = lastCheckinByText {
                    Text("Last: \(relativeTimeString(from: lastCheckin)) \(byText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Last: \(relativeTimeString(from: lastCheckin))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    func updateTimeRemaining() {
        let now = Date()
        let trip = liveTrip  // Use live session data, not captured plan parameter
        let eta = trip.eta_at  // Expected return time - LIVE from session
        let graceEnd = trip.eta_at.addingTimeInterval(Double(trip.grace_minutes) * 60)  // When contacts are notified

        if now > graceEnd {
            // After grace period - fully overdue, contacts have been notified
            timeState = .overdue
            let interval = now.timeIntervalSince(graceEnd)
            timeRemaining = formatInterval(interval)
        } else if now > eta {
            // Past ETA but within grace period - warning state
            timeState = .graceWarning
            let interval = graceEnd.timeIntervalSince(now)
            timeRemaining = formatInterval(interval)
        } else {
            // Before ETA - normal countdown to expected return
            timeState = .onTime
            let interval = eta.timeIntervalSince(now)
            timeRemaining = formatInterval(interval)
        }
    }

    func formatInterval(_ interval: TimeInterval) -> String {
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60
        let seconds = Int(interval) % 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds) seconds"
        }
    }
}

// MARK: - Notification for trip creation
extension Notification.Name {
    static let tripCreated = Notification.Name("tripCreated")
}

// MARK: - Upcoming Trips Section
struct UpcomingTripsSection: View {
    @EnvironmentObject var session: Session
    @EnvironmentObject var preferences: AppPreferences
    @State private var currentTime = Date()
    @State private var startingTripId: Int? = nil
    @State private var failedTripIds: Set<Int> = [] // Track trips that failed to start
    @State private var tripToEdit: Trip? = nil
    @State private var showingError = false
    @State private var errorMessage = ""

    // Computed property from session state for reactive updates
    var upcomingPlans: [Trip] {
        Array(session.allTrips
            .filter { $0.status == "planned" }
            .sorted { $0.start_at < $1.start_at }
            .prefix(preferences.maxUpcomingTrips))
    }

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
                List {
                    ForEach(upcomingPlans) { plan in
                        UpcomingTripCard(
                            plan: plan,
                            currentTime: currentTime,
                            isStarting: startingTripId == plan.id,
                            onStartTrip: { tripId in
                                startTrip(tripId)
                            },
                            onEdit: {
                                tripToEdit = plan
                            }
                        )
                        .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            Button {
                                startTrip(plan.id)
                            } label: {
                                Label("Start", systemImage: "arrow.right.circle")
                            }
                            .tint(.green)

                            Button {
                                tripToEdit = plan
                            } label: {
                                Label("Edit", systemImage: "pencil")
                            }
                            .tint(.blue)
                        }
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
                .scrollIndicators(.hidden)
                .frame(height: CGFloat(upcomingPlans.count) * 120)
                .scrollDisabled(true)
            }
        }
        .task {
            await loadUpcomingPlans()
            // Timer loop for auto-start - auto-cancelled when view disappears
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                currentTime = Date()
                // Check if auto-start is enabled in preferences
                if preferences.autoStartTrips {
                    checkForTripsToAutoStart()
                }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
            Task {
                await loadUpcomingPlans()
                // Reset failed trips on foreground - allow retry
                failedTripIds.removeAll()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .tripCreated)) { _ in
            Task {
                await loadUpcomingPlans()
            }
        }
        .sheet(item: $tripToEdit) { trip in
            Group {
                CreatePlanView(existingTrip: trip)
                    .environmentObject(session)
                    .onDisappear {
                        Task {
                            await loadUpcomingPlans()
                        }
                    }
            }
        }
        .alert("Failed to Start Trip", isPresented: $showingError) {
            Button("OK", role: .cancel) {
                errorMessage = ""
            }
        } message: {
            Text(errorMessage)
        }
    }

    func loadUpcomingPlans() async {
        // Refresh trips from network/cache - updates session.allTrips
        // The computed property upcomingPlans will automatically update
        _ = await session.loadAllTrips()
    }

    func checkForTripsToAutoStart() {
        // Only auto-start if not already starting something and no failures
        guard startingTripId == nil else { return }

        for plan in upcomingPlans {
            // Skip trips that already failed
            if failedTripIds.contains(plan.id) { continue }

            // Auto-start if the start time has passed
            if plan.start_at <= currentTime {
                startTrip(plan.id)
                break
            }
        }
    }

    func startTrip(_ tripId: Int) {
        // Don't retry trips that already failed
        guard !failedTripIds.contains(tripId) else { return }
        guard startingTripId == nil else { return }

        startingTripId = tripId
        Task {
            let success = await session.startTrip(tripId)
            if success {
                // Refresh trips to update the computed property
                _ = await session.loadAllTrips()
            }
            await MainActor.run {
                startingTripId = nil
                if !success {
                    // Mark as failed so we don't retry automatically
                    failedTripIds.insert(tripId)
                    // Show error to user
                    errorMessage = session.lastError.isEmpty ? "Unable to start trip. Please try again." : session.lastError
                    showingError = true
                }
            }
        }
    }
}

// MARK: - Upcoming Trip Card
struct UpcomingTripCard: View {
    let plan: Trip
    let currentTime: Date
    var isStarting: Bool = false
    var onStartTrip: ((Int) -> Void)? = nil
    var onEdit: (() -> Void)? = nil

    var activity: ActivityTypeAdapter {
        ActivityTypeAdapter(activity: plan.activity)
    }

    var shouldStart: Bool {
        plan.start_at <= currentTime
    }

    var countdown: String {
        let interval = plan.start_at.timeIntervalSince(currentTime)

        if interval <= 0 {
            return isStarting ? "Starting..." : "Starting now"
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
                    Group {
                        if isStarting {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Text(activity.icon)
                                .font(.title3)
                        }
                    }
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

                // Show actual start date/time (in the trip's stored timezone)
                HStack(spacing: 4) {
                    Image(systemName: "calendar")
                        .font(.caption2)
                    Text(DateUtils.formatDateTime(plan.start_at, inTimezone: plan.start_timezone))
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                if shouldStart && !isStarting {
                    // Show "Start" button when time is up
                    Button(action: {
                        onStartTrip?(plan.id)
                    }) {
                        Text("Start")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.hbBrand)
                            .cornerRadius(8)
                    }
                } else {
                    Text(countdown)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(shouldStart ? .green : Color.hbBrand)

                    Text(shouldStart ? "" : "until start")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
        .background(shouldStart ? Color.green.opacity(0.1) : Color(.tertiarySystemBackground))
        .cornerRadius(12)
        .animation(.easeInOut(duration: 0.3), value: shouldStart)
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

#Preview {
    MainTabView()
        .environmentObject(Session())
}
