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
            HistoryView(showAsTab: true, showStats: true)
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
    @EnvironmentObject var preferences: AppPreferences
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
                CreatePlanView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
                    .environmentObject(session)
                    .environmentObject(AppPreferences.shared)
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
    @State private var appeared = false
    @State private var pulseAnimation = false

    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    let extendOptions = [
        (15, "15 min"),
        (30, "30 min"),
        (60, "1 hr"),
        (120, "2 hrs"),
        (180, "3 hrs")
    ]

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
        timeState == .onTime ? .white.opacity(0.9) : statusColor
    }

    var bannerOpacity: Double {
        0.8
    }

    var borderOpacity: Double {
        0.75
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
            // Start pulse animation for the dot and glow
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                pulseAnimation = true
            }
        }
    }

    var glowColor: Color {
        switch timeState {
        case .overdue: return .red
        case .graceWarning: return .orange
        case .onTime: return Color(hex: plan.activity.colors.primary) ?? .purple
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
                        .animation(.easeOut(duration: 1.0).repeatForever(autoreverses: false), value: pulseAnimation)
                )
                .scaleEffect(pulseAnimation && isUrgent ? 1.1 : 1.0)
                .animation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true), value: pulseAnimation)

            Text(statusText)
                .font(statusFont)
                .fontWeight(.bold)
                .foregroundStyle(statusForeground)

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
        isUrgent ? statusColor.opacity(0.9) : .white.opacity(0.7)
    }

    var timeFont: Font {
        isUrgent ? .largeTitle : .title3
    }

    var timeColor: Color {
        switch timeState {
        case .overdue: return .red
        case .graceWarning: return .orange
        case .onTime: return .white
        }
    }

    var planInfoView: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
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

            VStack(alignment: .leading, spacing: 4) {
                Text(timeLabel)
                    .font(timeLabelFont)
                    .fontWeight(timeLabelWeight)
                    .foregroundStyle(timeLabelColor)
                Text(timeRemaining)
                    .font(timeFont)
                    .fontWeight(.bold)
                    .foregroundStyle(timeColor)
                    .scaleEffect(timeState == .overdue ? 1.05 : 1.0)
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
                    if let token = plan.checkin_token {
                        Task {
                            isPerformingAction = true
                            await session.performTokenAction(token, action: "checkin")
                            if preferences.hapticFeedbackEnabled {
                                UINotificationFeedbackGenerator().notificationOccurred(.success)
                            }
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

            // I'm Safe button - always shown
            Button(action: {
                if preferences.hapticFeedbackEnabled {
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                }
                if let token = plan.checkout_token {
                    Task {
                        isPerformingAction = true
                        await session.performTokenAction(token, action: "checkout")
                        if preferences.hapticFeedbackEnabled {
                            UINotificationFeedbackGenerator().notificationOccurred(.success)
                        }
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
    }

    @ViewBuilder
    var extendTimeView: some View {
        if showingExtendOptions {
            VStack(spacing: 8) {
                Text("Extend trip by:")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.7))

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(extendOptions, id: \.0) { minutes, label in
                            Button(action: {
                                if preferences.hapticFeedbackEnabled {
                                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                }
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
            // Show "Extend Time" text link for all states
            Button(action: {
                if preferences.hapticFeedbackEnabled {
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                }
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

    func updateTimeRemaining() {
        let now = Date()
        let eta = plan.eta_at  // Expected return time
        let graceEnd = plan.eta_at.addingTimeInterval(Double(plan.grace_minutes) * 60)  // When contacts are notified

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
    @State private var upcomingPlans: [Trip] = []
    @State private var currentTime = Date()
    @State private var startingTripId: Int? = nil
    @State private var failedTripIds: Set<Int> = [] // Track trips that failed to start
    @State private var tripToEdit: Trip? = nil
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
                    SwipeToEditContainer(onEdit: { tripToEdit = plan }) {
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
                    }
                }
            }
        }
        .onReceive(timer) { time in
            currentTime = time
            // Check if auto-start is enabled in preferences
            if preferences.autoStartTrips {
                checkForTripsToAutoStart()
            }
        }
        .task {
            await loadUpcomingPlans()
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
            CreatePlanView(existingTrip: trip)
                .environmentObject(session)
                .onDisappear {
                    Task {
                        await loadUpcomingPlans()
                    }
                }
        }
    }

    func loadUpcomingPlans() async {
        // Load plans with caching support (uses LocalStorage for offline access)
        let allPlans = await session.loadAllTrips()

        await MainActor.run {
            let maxTrips = preferences.maxUpcomingTrips
            upcomingPlans = allPlans
                .filter { $0.status == "planned" }
                .sorted { $0.start_at < $1.start_at }
                .prefix(maxTrips)
                .map { $0 }
        }
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
            await MainActor.run {
                startingTripId = nil
                if success {
                    // Remove from upcoming list and reload
                    upcomingPlans.removeAll { $0.id == tripId }
                } else {
                    // Mark as failed so we don't retry automatically
                    failedTripIds.insert(tripId)
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
        .contextMenu {
            if let onEdit = onEdit {
                Button {
                    onEdit()
                } label: {
                    Label("Edit", systemImage: "pencil")
                }
            }
        }
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

// MARK: - Swipe to Edit Container
struct SwipeToEditContainer<Content: View>: View {
    let onEdit: () -> Void
    @ViewBuilder let content: () -> Content

    @State private var offset: CGFloat = 0
    @State private var isRevealed = false
    private let buttonWidth: CGFloat = 74

    var body: some View {
        ZStack(alignment: .trailing) {
            // Edit button - circular like native iOS swipe actions
            Button(action: {
                withAnimation(.spring(response: 0.3)) {
                    offset = 0
                    isRevealed = false
                }
                onEdit()
            }) {
                VStack(spacing: 4) {
                    // Circular button with icon
                    Circle()
                        .fill(Color.blue)
                        .frame(width: 52, height: 52)
                        .overlay(
                            Image(systemName: "pencil")
                                .font(.system(size: 22, weight: .medium))
                                .foregroundStyle(.white)
                        )

                    Text("Edit")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.blue)
                }
            }
            .frame(width: buttonWidth)
            .offset(x: 8)

            // Main card content
            content()
                .offset(x: offset)
                .gesture(
                    DragGesture(minimumDistance: 15)
                        .onChanged { value in
                            let translation = value.translation.width
                            if translation < 0 {
                                // Swiping left - reveal edit button
                                offset = max(translation, -buttonWidth - 10)
                            } else if isRevealed {
                                // Swiping right to close
                                offset = min(0, -buttonWidth + translation)
                            }
                        }
                        .onEnded { value in
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                if value.translation.width < -35 {
                                    offset = -buttonWidth
                                    isRevealed = true
                                } else {
                                    offset = 0
                                    isRevealed = false
                                }
                            }
                        }
                )
        }
    }
}

#Preview {
    MainTabView()
        .environmentObject(Session())
}