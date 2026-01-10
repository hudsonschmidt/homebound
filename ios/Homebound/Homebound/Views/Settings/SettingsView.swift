import SwiftUI
import Combine
import UserNotifications
import CoreLocation
import UniformTypeIdentifiers

// MARK: - App Preferences

enum AppColorScheme: String, CaseIterable {
    case system = "system"
    case light = "light"
    case dark = "dark"

    var displayName: String {
        switch self {
        case .system: return "System"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

enum MapType: String, CaseIterable {
    case standard = "standard"
    case satellite = "satellite"
    case hybrid = "hybrid"

    var displayName: String {
        switch self {
        case .standard: return "Standard"
        case .satellite: return "Satellite"
        case .hybrid: return "Hybrid"
        }
    }
}

// LiveActivityDisplayMode is defined in TripActivityAttributes.swift
// (shared between main app and widget extension targets)

enum FriendStatType: String, CaseIterable, Codable, Identifiable {
    case joinDate = "joinDate"
    case age = "age"
    case achievements = "achievements"
    case totalTrips = "totalTrips"
    case adventureTime = "adventureTime"
    case favoriteActivity = "favoriteActivity"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .joinDate: return "Member Since"
        case .age: return "Age"
        case .achievements: return "Achievements"
        case .totalTrips: return "Total Trips"
        case .adventureTime: return "Adventure Time"
        case .favoriteActivity: return "Favorite Activity"
        }
    }

    var icon: String {
        switch self {
        case .joinDate: return "calendar.badge.clock"
        case .age: return "number"
        case .achievements: return "trophy.fill"
        case .totalTrips: return "figure.walk"
        case .adventureTime: return "hourglass"
        case .favoriteActivity: return "star.fill"
        }
    }

    var iconColor: Color {
        switch self {
        case .joinDate: return .blue
        case .age: return .purple
        case .achievements: return .orange
        case .totalTrips: return .red
        case .adventureTime: return .green
        case .favoriteActivity: return .yellow
        }
    }
}

class AppPreferences: ObservableObject {
    static let shared = AppPreferences()

    // MARK: - Appearance
    @Published var colorScheme: AppColorScheme {
        didSet {
            UserDefaults.standard.set(colorScheme.rawValue, forKey: "colorScheme")
        }
    }

    // MARK: - Trips
    @Published var autoStartTrips: Bool {
        didSet {
            UserDefaults.standard.set(autoStartTrips, forKey: "autoStartTrips")
        }
    }

    @Published var defaultGraceMinutes: Int {
        didSet {
            UserDefaults.standard.set(defaultGraceMinutes, forKey: "defaultGraceMinutes")
        }
    }

    @Published var defaultActivityId: Int? {
        didSet {
            if let id = defaultActivityId {
                UserDefaults.standard.set(id, forKey: "defaultActivityId")
            } else {
                UserDefaults.standard.removeObject(forKey: "defaultActivityId")
            }
        }
    }

    @Published var pinnedActivityIds: [Int] {
        didSet {
            // Limit to 3 pinned activities
            if pinnedActivityIds.count > 3 {
                // This will trigger didSet again, so return early to avoid double-save
                pinnedActivityIds = Array(pinnedActivityIds.prefix(3))
                return
            }
            // Only save when we have a valid count (avoids saving during the trim)
            if let data = try? JSONEncoder().encode(pinnedActivityIds) {
                UserDefaults.standard.set(data, forKey: "pinnedActivityIds")
            }
        }
    }

    // MARK: - Home Screen
    @Published var showUpcomingTrips: Bool {
        didSet {
            UserDefaults.standard.set(showUpcomingTrips, forKey: "showUpcomingTrips")
        }
    }

    @Published var showStats: Bool {
        didSet {
            UserDefaults.standard.set(showStats, forKey: "showStats")
        }
    }

    @Published var maxUpcomingTrips: Int {
        didSet {
            UserDefaults.standard.set(maxUpcomingTrips, forKey: "maxUpcomingTrips")
        }
    }

    // MARK: - Sounds & Haptics
    @Published var hapticFeedbackEnabled: Bool {
        didSet {
            UserDefaults.standard.set(hapticFeedbackEnabled, forKey: "hapticFeedbackEnabled")
        }
    }

    @Published var checkInSoundEnabled: Bool {
        didSet {
            UserDefaults.standard.set(checkInSoundEnabled, forKey: "checkInSoundEnabled")
        }
    }

    // MARK: - Map
    @Published var defaultMapType: MapType {
        didSet {
            UserDefaults.standard.set(defaultMapType.rawValue, forKey: "defaultMapType")
        }
    }

    // MARK: - Units & Formats
    @Published var useMetricUnits: Bool {
        didSet {
            UserDefaults.standard.set(useMetricUnits, forKey: "useMetricUnits")
        }
    }

    @Published var use24HourTime: Bool {
        didSet {
            UserDefaults.standard.set(use24HourTime, forKey: "use24HourTime")
        }
    }

    // MARK: - Notifications
    @Published var tripRemindersEnabled: Bool {
        didSet {
            UserDefaults.standard.set(tripRemindersEnabled, forKey: "tripRemindersEnabled")
        }
    }

    @Published var checkInAlertsEnabled: Bool {
        didSet {
            UserDefaults.standard.set(checkInAlertsEnabled, forKey: "checkInAlertsEnabled")
        }
    }

    @Published var emergencyNotificationsEnabled: Bool {
        didSet {
            UserDefaults.standard.set(emergencyNotificationsEnabled, forKey: "emergencyNotificationsEnabled")
        }
    }

    // MARK: - Live Activity
    private let appGroupIdentifier = "group.com.homeboundapp.Homebound"

    private var sharedDefaults: UserDefaults? {
        UserDefaults(suiteName: appGroupIdentifier)
    }

    @Published var liveActivityEnabled: Bool {
        didSet {
            sharedDefaults?.set(liveActivityEnabled, forKey: "liveActivityEnabled")
        }
    }

    @Published var liveActivityDisplayMode: LiveActivityDisplayMode {
        didSet {
            sharedDefaults?.set(liveActivityDisplayMode.rawValue, forKey: "liveActivityDisplayMode")
        }
    }

    // MARK: - What's New
    @Published var lastSeenWhatsNewVersion: String {
        didSet {
            UserDefaults.standard.set(lastSeenWhatsNewVersion, forKey: "lastSeenWhatsNewVersion")
        }
    }

    // MARK: - Getting Started
    @Published var hasSeenGettingStarted: Bool {
        didSet {
            UserDefaults.standard.set(hasSeenGettingStarted, forKey: "hasSeenGettingStarted")
        }
    }

    // MARK: - Debug
    @Published var debugUnlockAllAchievements: Bool {
        didSet {
            UserDefaults.standard.set(debugUnlockAllAchievements, forKey: "debugUnlockAllAchievements")
        }
    }

    // MARK: - Achievements
    @Published var seenAchievementIds: Set<String> {
        didSet {
            if let data = try? JSONEncoder().encode(Array(seenAchievementIds)) {
                UserDefaults.standard.set(data, forKey: "seenAchievementIds")
            }
        }
    }

    // MARK: - Friends Mini Profile
    @Published var showFriendJoinDate: Bool {
        didSet {
            UserDefaults.standard.set(showFriendJoinDate, forKey: "showFriendJoinDate")
        }
    }

    @Published var showFriendAge: Bool {
        didSet {
            UserDefaults.standard.set(showFriendAge, forKey: "showFriendAge")
        }
    }

    @Published var showFriendAchievements: Bool {
        didSet {
            UserDefaults.standard.set(showFriendAchievements, forKey: "showFriendAchievements")
        }
    }

    @Published var showFriendTotalTrips: Bool {
        didSet {
            UserDefaults.standard.set(showFriendTotalTrips, forKey: "showFriendTotalTrips")
        }
    }

    @Published var showFriendAdventureTime: Bool {
        didSet {
            UserDefaults.standard.set(showFriendAdventureTime, forKey: "showFriendAdventureTime")
        }
    }

    @Published var showFriendFavoriteActivity: Bool {
        didSet {
            UserDefaults.standard.set(showFriendFavoriteActivity, forKey: "showFriendFavoriteActivity")
        }
    }

    @Published var friendStatOrder: [FriendStatType] {
        didSet {
            if let data = try? JSONEncoder().encode(friendStatOrder) {
                UserDefaults.standard.set(data, forKey: "friendStatOrder")
            }
        }
    }

    var shouldShowWhatsNew: Bool {
        let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
        // Only show if user has seen a previous version (not a fresh install) and it's different from current
        return !lastSeenWhatsNewVersion.isEmpty && lastSeenWhatsNewVersion != currentVersion
    }

    func markWhatsNewAsSeen() {
        let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
        lastSeenWhatsNewVersion = currentVersion
    }

    var shouldShowGettingStarted: Bool {
        !hasSeenGettingStarted
    }

    func markGettingStartedAsSeen() {
        hasSeenGettingStarted = true
    }

    init() {
        // Appearance
        let schemeRaw = UserDefaults.standard.string(forKey: "colorScheme") ?? "system"
        self.colorScheme = AppColorScheme(rawValue: schemeRaw) ?? .system

        // Trips
        self.autoStartTrips = UserDefaults.standard.bool(forKey: "autoStartTrips")
        let savedGrace = UserDefaults.standard.integer(forKey: "defaultGraceMinutes")
        self.defaultGraceMinutes = savedGrace > 0 ? savedGrace : 30
        let savedActivityId = UserDefaults.standard.integer(forKey: "defaultActivityId")
        self.defaultActivityId = savedActivityId > 0 ? savedActivityId : nil

        // Pinned Activities
        if let data = UserDefaults.standard.data(forKey: "pinnedActivityIds"),
           let ids = try? JSONDecoder().decode([Int].self, from: data) {
            self.pinnedActivityIds = Array(ids.prefix(3))
        } else {
            self.pinnedActivityIds = []
        }

        // Home Screen - defaults to true/shown
        self.showUpcomingTrips = UserDefaults.standard.object(forKey: "showUpcomingTrips") == nil ? true : UserDefaults.standard.bool(forKey: "showUpcomingTrips")
        self.showStats = UserDefaults.standard.object(forKey: "showStats") == nil ? true : UserDefaults.standard.bool(forKey: "showStats")
        let savedMaxTrips = UserDefaults.standard.integer(forKey: "maxUpcomingTrips")
        self.maxUpcomingTrips = savedMaxTrips > 0 ? savedMaxTrips : 3

        // Sounds & Haptics - defaults to true/enabled
        self.hapticFeedbackEnabled = UserDefaults.standard.object(forKey: "hapticFeedbackEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "hapticFeedbackEnabled")
        self.checkInSoundEnabled = UserDefaults.standard.object(forKey: "checkInSoundEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "checkInSoundEnabled")

        // Map
        let mapTypeRaw = UserDefaults.standard.string(forKey: "defaultMapType") ?? "standard"
        self.defaultMapType = MapType(rawValue: mapTypeRaw) ?? .standard

        // Units & Formats - default to locale-appropriate
        self.useMetricUnits = UserDefaults.standard.object(forKey: "useMetricUnits") == nil ? Locale.current.measurementSystem == .metric : UserDefaults.standard.bool(forKey: "useMetricUnits")

        // Detect if locale uses 24-hour time by checking the short time format for AM/PM indicator
        let localeUses24Hour: Bool = {
            let formatter = DateFormatter()
            formatter.locale = Locale.current
            formatter.dateStyle = .none
            formatter.timeStyle = .short
            let timeString = formatter.string(from: Date())
            // If the formatted time contains AM/PM symbols, it's 12-hour format
            let amSymbol = formatter.amSymbol ?? "AM"
            let pmSymbol = formatter.pmSymbol ?? "PM"
            return !timeString.contains(amSymbol) && !timeString.contains(pmSymbol)
        }()
        self.use24HourTime = UserDefaults.standard.object(forKey: "use24HourTime") == nil ? localeUses24Hour : UserDefaults.standard.bool(forKey: "use24HourTime")

        // Notifications - defaults to enabled
        self.tripRemindersEnabled = UserDefaults.standard.object(forKey: "tripRemindersEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "tripRemindersEnabled")
        self.checkInAlertsEnabled = UserDefaults.standard.object(forKey: "checkInAlertsEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "checkInAlertsEnabled")
        self.emergencyNotificationsEnabled = UserDefaults.standard.object(forKey: "emergencyNotificationsEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "emergencyNotificationsEnabled")

        // Live Activity - defaults to enabled with standard display mode
        let groupDefaults = UserDefaults(suiteName: "group.com.homeboundapp.Homebound")
        self.liveActivityEnabled = groupDefaults?.object(forKey: "liveActivityEnabled") == nil ? true : (groupDefaults?.bool(forKey: "liveActivityEnabled") ?? true)
        let displayModeRaw = groupDefaults?.string(forKey: "liveActivityDisplayMode") ?? "standard"
        self.liveActivityDisplayMode = LiveActivityDisplayMode(rawValue: displayModeRaw) ?? .standard

        // What's New - if empty (fresh install), set to current version to skip What's New
        let storedVersion = UserDefaults.standard.string(forKey: "lastSeenWhatsNewVersion") ?? ""
        if storedVersion.isEmpty {
            let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
            self.lastSeenWhatsNewVersion = currentVersion
            UserDefaults.standard.set(currentVersion, forKey: "lastSeenWhatsNewVersion")
        } else {
            self.lastSeenWhatsNewVersion = storedVersion
        }

        // Getting Started - defaults to false (not seen)
        self.hasSeenGettingStarted = UserDefaults.standard.bool(forKey: "hasSeenGettingStarted")

        // Debug - defaults to false
        self.debugUnlockAllAchievements = UserDefaults.standard.bool(forKey: "debugUnlockAllAchievements")

        // Achievements - load seen achievement IDs
        if let data = UserDefaults.standard.data(forKey: "seenAchievementIds"),
           let ids = try? JSONDecoder().decode([String].self, from: data) {
            self.seenAchievementIds = Set(ids)
        } else {
            self.seenAchievementIds = []
        }

        // Friends Mini Profile - defaults (join date true, age false, rest true)
        self.showFriendJoinDate = UserDefaults.standard.object(forKey: "showFriendJoinDate") == nil ? true : UserDefaults.standard.bool(forKey: "showFriendJoinDate")
        self.showFriendAge = UserDefaults.standard.object(forKey: "showFriendAge") == nil ? false : UserDefaults.standard.bool(forKey: "showFriendAge")
        self.showFriendAchievements = UserDefaults.standard.object(forKey: "showFriendAchievements") == nil ? true : UserDefaults.standard.bool(forKey: "showFriendAchievements")
        self.showFriendTotalTrips = UserDefaults.standard.object(forKey: "showFriendTotalTrips") == nil ? true : UserDefaults.standard.bool(forKey: "showFriendTotalTrips")
        self.showFriendAdventureTime = UserDefaults.standard.object(forKey: "showFriendAdventureTime") == nil ? true : UserDefaults.standard.bool(forKey: "showFriendAdventureTime")
        self.showFriendFavoriteActivity = UserDefaults.standard.object(forKey: "showFriendFavoriteActivity") == nil ? true : UserDefaults.standard.bool(forKey: "showFriendFavoriteActivity")

        // Friend stat order - load or use default order
        if let data = UserDefaults.standard.data(forKey: "friendStatOrder"),
           let order = try? JSONDecoder().decode([FriendStatType].self, from: data) {
            self.friendStatOrder = order
        } else {
            self.friendStatOrder = FriendStatType.allCases
        }
    }

    // MARK: - Pinned Activities Helpers
    func pinActivity(_ activityId: Int) {
        guard !pinnedActivityIds.contains(activityId), pinnedActivityIds.count < 3 else { return }
        pinnedActivityIds.append(activityId)
    }

    func unpinActivity(_ activityId: Int) {
        pinnedActivityIds.removeAll { $0 == activityId }
    }

    func clearPinnedActivities() {
        pinnedActivityIds = []
    }

    func isActivityPinned(_ activityId: Int) -> Bool {
        pinnedActivityIds.contains(activityId)
    }

    // MARK: - Formatting Helpers
    func formatDistance(_ meters: Double) -> String {
        if useMetricUnits {
            if meters >= 1000 {
                return String(format: "%.1f km", meters / 1000)
            } else {
                return String(format: "%.0f m", meters)
            }
        } else {
            let miles = meters / 1609.34
            if miles >= 0.1 {
                return String(format: "%.1f mi", miles)
            } else {
                let feet = meters * 3.28084
                return String(format: "%.0f ft", feet)
            }
        }
    }

    func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = use24HourTime ? "HH:mm" : "h:mm a"
        return formatter.string(from: date)
    }

    func formatDateTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        if use24HourTime {
            formatter.setLocalizedDateFormatFromTemplate("Md HH:mm")
        }
        return formatter.string(from: date)
    }
}

// MARK: - Main Settings View
struct SettingsView: View {
    @EnvironmentObject var session: Session
    @EnvironmentObject var preferences: AppPreferences
    @StateObject private var subscriptionManager = SubscriptionManager.shared
    @Environment(\.dismiss) var dismiss
    @State private var showingClearCacheAlert = false
    @State private var showingWhatsNew = false
    @State private var showingGettingStarted = false

    var body: some View {
        NavigationStack {
            List {
                // Account Section
                Section {
                    NavigationLink(destination: AccountView()) {
                        HStack {
                            // Profile image placeholder
                            Circle()
                                .fill(
                                    LinearGradient(
                                        colors: [Color.hbBrand, Color.hbTeal],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .frame(width: 60, height: 60)
                                .overlay(
                                    Text(String(session.userName?.prefix(1).uppercased() ?? "U"))
                                        .font(.title2)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(.white)
                                )

                            VStack(alignment: .leading, spacing: 4) {
                                Text(session.userName ?? "User")
                                    .font(.headline)
                                Text(session.userEmail ?? "")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()
                        }
                        .padding(.vertical, 8)
                    }
                }

                // Subscription Section
                Section {
                    NavigationLink(destination: SubscriptionSettingsView()) {
                        HStack(spacing: 12) {
                            Image("Logo")
                                .resizable()
                                .scaledToFit()
                                .frame(width: 28, height: 28)
                                .clipShape(RoundedRectangle(cornerRadius: 6))

                            Text("Homebound+")

                            Spacer()

                            if session.featureLimits.isPremium {
                                if subscriptionManager.isTrialing {
                                    // Show trial badge instead of premium badge for trial users
                                    TrialBadge()
                                } else if !subscriptionManager.willAutoRenew {
                                    // Show cancelled indicator
                                    CancelledBadge()
                                } else {
                                    PremiumBadge()
                                }
                            } else {
                                Text("Upgrade")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                // Safety Section
                Section("Safety") {
                    NavigationLink(destination: EmergencyContactsView()) {
                        Label {
                            Text("Emergency Contacts")
                        } icon: {
                            Image(systemName: "person.2.fill")
                                .foregroundStyle(.orange)
                        }
                    }
                }

                // App Section
                Section("App") {
                    NavigationLink(destination: CustomizationView()) {
                        Label {
                            Text("Customization")
                        } icon: {
                            Image(systemName: "slider.horizontal.3")
                                .foregroundStyle(Color.hbBrand)
                        }
                    }

                    NavigationLink(destination: NotificationSettingsView()) {
                        Label {
                            Text("Notifications")
                        } icon: {
                            Image(systemName: "bell.fill")
                                .foregroundStyle(.red)
                        }
                    }

                    NavigationLink(destination: PrivacyView()) {
                        Label {
                            Text("Privacy")
                        } icon: {
                            Image(systemName: "lock.fill")
                                .foregroundStyle(.blue)
                        }
                    }

                    NavigationLink(destination: FriendsSettingsView()) {
                        Label {
                            Text("Friends")
                        } icon: {
                            Image(systemName: "person.2.fill")
                                .foregroundStyle(.green)
                        }
                    }

                    NavigationLink(destination: AboutView()) {
                        Label {
                            Text("About")
                        } icon: {
                            Image(systemName: "info.circle.fill")
                                .foregroundStyle(.gray)
                        }
                    }
                }

                // Developer Section
                if session.userEmail == "hudsonschmidt08@gmail.com" || session.userEmail == "parkcityht@gmail.com" {
                    Section("Developer") {
                        VStack(alignment: .leading, spacing: 8) {
                            Label {
                                Text("Server Environment")
                            } icon: {
                                Image(systemName: "server.rack")
                                    .foregroundStyle(session.serverEnvironment == .production ? Color.hbBrand : session.serverEnvironment == .devRender ? .orange : .green)
                            }

                            Picker("Server", selection: $session.serverEnvironment) {
                                ForEach(ServerEnvironment.allCases, id: \.self) { env in
                                    Text(env.displayName).tag(env)
                                }
                            }
                            .pickerStyle(.segmented)
                        }
                        .padding(.vertical, 4)

                        Toggle(isOn: $preferences.debugUnlockAllAchievements) {
                            Label {
                                Text("Unlock All Achievements")
                            } icon: {
                                Image(systemName: "trophy.fill")
                                    .foregroundStyle(.orange)
                            }
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Label {
                                Text("Subscription Tier Override")
                            } icon: {
                                Image(systemName: "crown.fill")
                                    .foregroundStyle(session.debugSubscriptionTier == "plus" ? Color.hbBrand : session.debugSubscriptionTier == "free" ? .orange : .secondary)
                            }

                            Picker("Tier", selection: $session.debugSubscriptionTier) {
                                Text("None").tag("")
                                Text("Free").tag("free")
                                Text("Plus").tag("plus")
                            }
                            .pickerStyle(.segmented)
                            .onChange(of: session.debugSubscriptionTier) { _, newValue in
                                session.applyDebugSubscriptionTier(newValue)
                            }

                            if !session.debugSubscriptionTier.isEmpty {
                                Text("Overriding to \(session.debugSubscriptionTier == "plus" ? "Homebound+" : "Free") tier")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Support Section
                Section("Support") {
                    Link(destination: URL(string: "https://www.homeboundapp.com/help")!) {
                        Label {
                            HStack {
                                Text("Help Center")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "questionmark.circle.fill")
                                .foregroundStyle(Color.hbBrand)
                        }
                    }

                    Link(destination: URL(string: "mailto:support@homeboundapp.com")!) {
                        Label {
                            HStack {
                                Text("Contact Us")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "envelope.fill")
                                .foregroundStyle(Color.hbBrand)
                        }
                    }
                }

                // Resources Section
                Section("Resources") {
                    Button(action: {
                        showingWhatsNew = true
                    }) {
                        Label {
                            HStack {
                                Text("What's New")
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "sparkles")
                                .foregroundStyle(.blue)
                        }
                    }
                    .foregroundStyle(.primary)

                    Button(action: {
                        showingGettingStarted = true
                    }) {
                        Label {
                            HStack {
                                Text("Getting Started")
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "flag.fill")
                                .foregroundStyle(.orange)
                        }
                    }
                    .foregroundStyle(.primary)

                    Button(action: {
                        showingClearCacheAlert = true
                    }) {
                        Label {
                            HStack {
                                Text("Clear Cache")
                                Spacer()
                                Image(systemName: "trash")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "tray.fill")
                                .foregroundStyle(Color.hbBrand)
                        }
                    }
                    .foregroundStyle(.primary)
                }

                Section("Help Make Homebound Better"){
                    Link(destination: URL(string: "https://homebound.canny.io/feature-requests")!) {
                        Label {
                            HStack {
                                Text("Request a Feature")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "lightbulb.fill")
                                .foregroundStyle(.yellow)
                        }
                    }

                    Link(destination: URL(string: "https://homebound.canny.io/bugs")!) {
                        Label {
                            HStack {
                                Text("Report a Bug")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "ladybug.fill")
                                .foregroundStyle(.red)
                        }
                    }
                }

                // Legal Section
                Section("Legal") {
                    Link(destination: URL(string: "https://www.homeboundapp.com/privacypolicy")!) {
                        Label {
                            HStack {
                                Text("Privacy Policy")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "shield.lefthalf.filled.badge.checkmark")
                                .foregroundStyle(.blue)
                        }
                    }

                    Link(destination: URL(string: "https://www.homeboundapp.com/termsofservice")!) {
                        Label {
                            HStack {
                                Text("Terms of Service")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "doc.text.fill")
                                .foregroundStyle(.gray)
                        }
                    }
                }

                // Version info at bottom
                Section {
                    VStack(spacing: 3) {
                        Image("Icon")
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 40, height: 40)
                            .clipShape(RoundedRectangle(cornerRadius: 12))

                        Text("Homebound v\(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")")
                            .font(.footnote)
                            .fontWeight(.medium)

                        Text("Made with love by Hudson Schmidt")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("in Park City & San Luis Obispo")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Text("© 2025")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .listRowBackground(Color.clear)
                }
            }
            .scrollIndicators(.hidden)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
            .alert("Clear Cache", isPresented: $showingClearCacheAlert) {
                Button("Cancel", role: .cancel) { }
                Button("Clear", role: .destructive) {
                    LocalStorage.shared.clearAll()
                }
            } message: {
                Text("This will clear all cached trips and activities. Data will be reloaded from the server.")
            }
            .fullScreenCover(isPresented: $showingWhatsNew) {
                WhatsNewView(isFromSettings: true)
            }
            .fullScreenCover(isPresented: $showingGettingStarted) {
                GettingStartedView(isFromSettings: true)
                    .environmentObject(preferences)
            }
        }
    }
}

// MARK: - Account View
struct AccountView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var firstName = ""
    @State private var lastName = ""
    @State private var age: Int = 0

    @State private var editingFirstName = false
    @State private var editingLastName = false
    @State private var editingAge = false

    @State private var tempFirstName = ""
    @State private var tempLastName = ""
    @State private var tempAge = ""

    @State private var showingDeleteAlert = false
    @State private var deleteConfirmation = ""
    @State private var isDeleting = false

    @State private var showingLogoutAlert = false
    @FocusState private var isAgeFocused: Bool

    var body: some View {
        List {
            // Profile Photo Section
            Section {
                HStack {
                    Spacer()

                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [Color.hbBrand, Color.hbTeal],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 120, height: 120)
                        .overlay(
                            Text(String(firstName.prefix(1).uppercased()))
                                .font(.largeTitle)
                                .fontWeight(.semibold)
                                .foregroundStyle(.white)
                        )

                    Spacer()
                }
                .listRowBackground(Color.clear)
            }

            // Personal Information Section
            Section("Personal Information") {
                // Email (non-editable)
                HStack {
                    Text("Email")
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(session.userEmail ?? "")
                        .foregroundStyle(.secondary)
                }

                // First Name
                HStack {
                    Text("First Name")
                        .foregroundStyle(editingFirstName ? Color.hbBrand : .primary)
                    Spacer()
                    if editingFirstName {
                        TextField("First Name", text: $tempFirstName)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                saveFirstName()
                            }
                    } else {
                        Text(firstName.isEmpty ? "Not set" : firstName)
                            .foregroundStyle(firstName.isEmpty ? .secondary : .primary)
                    }

                    Button(action: {
                        if editingFirstName {
                            saveFirstName()
                        } else {
                            tempFirstName = firstName
                            editingFirstName = true
                        }
                    }) {
                        Text(editingFirstName ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }

                // Last Name
                HStack {
                    Text("Last Name")
                        .foregroundStyle(editingLastName ? Color.hbBrand : .primary)
                    Spacer()
                    if editingLastName {
                        TextField("Last Name", text: $tempLastName)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                saveLastName()
                            }
                    } else {
                        Text(lastName.isEmpty ? "Not set" : lastName)
                            .foregroundStyle(lastName.isEmpty ? .secondary : .primary)
                    }

                    Button(action: {
                        if editingLastName {
                            saveLastName()
                        } else {
                            tempLastName = lastName
                            editingLastName = true
                        }
                    }) {
                        Text(editingLastName ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }

                // Age
                HStack {
                    Text("Age")
                        .foregroundStyle(editingAge ? Color.hbBrand : .primary)
                    Spacer()
                    if editingAge {
                        TextField("Age", text: $tempAge)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .keyboardType(.numberPad)
                            .focused($isAgeFocused)
                            .onSubmit {
                                saveAge()
                            }
                            .toolbar {
                                ToolbarItemGroup(placement: .keyboard) {
                                    Spacer()
                                    Button("Done") {
                                        isAgeFocused = false
                                        saveAge()
                                    }
                                }
                            }
                    } else {
                        Text(age > 0 ? "\(age)" : "Not set")
                            .foregroundStyle(age > 0 ? .primary : .secondary)
                    }

                    Button(action: {
                        if editingAge {
                            saveAge()
                        } else {
                            tempAge = age > 0 ? "\(age)" : ""
                            editingAge = true
                        }
                    }) {
                        Text(editingAge ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }
            }

            // Log Out
            Section {
                Button(action: {
                    showingLogoutAlert = true
                }) {
                    HStack {
                        Spacer()
                        Text("Log Out")
                            .foregroundStyle(.red)
                        Spacer()
                    }
                }
            }

            // Delete Account
            Section {
                Button(action: {
                    showingDeleteAlert = true
                }) {
                    HStack {
                        Spacer()
                        if isDeleting {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle())
                                .scaleEffect(0.8)
                        } else {
                            Text("Delete Account")
                                .foregroundStyle(.red)
                        }
                        Spacer()
                    }
                }
                .disabled(isDeleting)
            }
        }
        .scrollIndicators(.hidden)
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            loadUserData()
        }
        .alert("Log Out", isPresented: $showingLogoutAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Log Out", role: .destructive) {
                Task {
                    await MainActor.run {
                        session.signOut()
                    }
                }
            }
        } message: {
            Text("Are you sure you want to log out?")
        }
        .alert("Delete Account", isPresented: $showingDeleteAlert) {
            TextField("Type DELETE to confirm", text: $deleteConfirmation)
                .textInputAutocapitalization(.characters)

            Button("Cancel", role: .cancel) {
                deleteConfirmation = ""
            }

            Button("Delete Account", role: .destructive) {
                if deleteConfirmation == "DELETE" {
                    Task {
                        await deleteAccount()
                    }
                }
            }
            .disabled(deleteConfirmation != "DELETE")
        } message: {
            Text("This action cannot be undone. All your data will be permanently deleted. Type DELETE to confirm.")
        }
    }

    private func loadUserData() {
        // Parse full name into first and last
        if let fullName = session.userName {
            let components = fullName.split(separator: " ", maxSplits: 1)
            firstName = String(components.first ?? "")
            lastName = components.count > 1 ? String(components[1]) : ""
        }
        age = session.userAge ?? 0
    }

    private func saveFirstName() {
        firstName = tempFirstName
        updateProfile()
        editingFirstName = false
    }

    private func saveLastName() {
        lastName = tempLastName
        updateProfile()
        editingLastName = false
    }

    private func saveAge() {
        if let ageValue = Int(tempAge), ageValue > 0 && ageValue < 150 {
            age = ageValue
            updateProfile()
        }
        editingAge = false
    }

    private func updateProfile() {
        Task {
            let trimmedFirstName = firstName.trimmingCharacters(in: .whitespacesAndNewlines)
            let trimmedLastName = lastName.trimmingCharacters(in: .whitespacesAndNewlines)
            _ = await session.updateProfile(
                firstName: trimmedFirstName.isEmpty ? nil : trimmedFirstName,
                lastName: trimmedLastName.isEmpty ? nil : trimmedLastName,
                age: age > 0 ? age : nil
            )
        }
    }

    private func deleteAccount() async {
        isDeleting = true
        let success = await session.deleteAccount()
        if !success {
            isDeleting = false
        }
    }
}

// MARK: - Customization View
struct CustomizationView: View {
    @EnvironmentObject var session: Session
    @EnvironmentObject var preferences: AppPreferences
    @State private var selectedActivityToPin: Int? = nil
    @State private var showPaywall = false
    @State private var showLiveActivityPaywall = false
    @State private var isLoadingPinnedActivities = false

    let graceOptions = [15, 30, 45, 60, 90]

    var canPinActivities: Bool {
        session.canUse(feature: .pinnedActivities)
    }

    var pinnedActivities: [Activity] {
        preferences.pinnedActivityIds.compactMap { pinnedId in
            session.activities.first { $0.id == pinnedId }
        }
    }

    var unpinnedActivities: [Activity] {
        session.activities.filter { !preferences.isActivityPinned($0.id) }
    }

    var body: some View {
        List {
            // MARK: - Appearance
            Section {
                Picker("Theme", selection: $preferences.colorScheme) {
                    ForEach(AppColorScheme.allCases, id: \.self) { scheme in
                        Text(scheme.displayName).tag(scheme)
                    }
                }
            } header: {
                Text("Appearance")
            }

            // MARK: - Trips
            Section {
                Toggle(isOn: $preferences.autoStartTrips) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Auto-Start Trips")
                        Text(preferences.autoStartTrips ? "Starts automatically" : "Manual start")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Picker("Default Grace Period", selection: $preferences.defaultGraceMinutes) {
                    ForEach(graceOptions, id: \.self) { minutes in
                        Text("\(minutes) minutes").tag(minutes)
                    }
                }

                Picker("Default Activity", selection: $preferences.defaultActivityId) {
                    Text("None").tag(nil as Int?)
                    ForEach(session.activities) { activity in
                        Text("\(activity.icon) \(activity.name)").tag(activity.id as Int?)
                    }
                }
            } header: {
                Text("Trips")
            } footer: {
                Text("These defaults will be used when creating new trips.")
            }

            // MARK: - Favorite Activities
            Section {
                if !canPinActivities {
                    // Premium upsell for free users
                    HStack {
                        Image(systemName: "star.fill")
                            .foregroundStyle(Color.hbBrand)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Favorite Activities")
                                .font(.subheadline)
                                .fontWeight(.medium)
                            Text("Pin your most-used activities for quick access")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        PremiumBadge()
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        showPaywall = true
                    }
                } else if preferences.pinnedActivityIds.isEmpty {
                    Text("No favorite activities")
                        .foregroundStyle(.secondary)
                        .font(.subheadline)
                } else {
                    ForEach(pinnedActivities, id: \.id) { activity in
                        HStack {
                            Text(activity.icon)
                            Text(activity.name)
                            Spacer()
                            Button {
                                Task {
                                    let success = await session.unpinActivity(activityId: activity.id)
                                    if success {
                                        preferences.unpinActivity(activity.id)
                                    }
                                }
                            } label: {
                                Image(systemName: "star.slash")
                                    .foregroundStyle(.red)
                            }
                        }
                    }
                }

                if canPinActivities && preferences.pinnedActivityIds.count < 3 {
                    Picker("Add Favorite", selection: $selectedActivityToPin) {
                        Text("Select activity...").tag(nil as Int?)
                        ForEach(unpinnedActivities, id: \.id) { activity in
                            Text("\(activity.icon) \(activity.name)").tag(activity.id as Int?)
                        }
                    }
                    .onChange(of: selectedActivityToPin) { _, newValue in
                        if let activityId = newValue {
                            let position = preferences.pinnedActivityIds.count
                            Task {
                                let success = await session.pinActivity(activityId: activityId, position: position)
                                if success {
                                    preferences.pinActivity(activityId)
                                }
                            }
                            selectedActivityToPin = nil
                        }
                    }
                }
            } header: {
                HStack {
                    Text("Favorite Activities")
                    if !canPinActivities {
                        Spacer()
                        PremiumBadge()
                    }
                }
            } footer: {
                if canPinActivities {
                    Text("Pin up to 3 activities for quick access when creating trips.")
                } else {
                    Text("Upgrade to Homebound+ to pin your favorite activities.")
                }
            }

            // MARK: - Home Screen
            Section {
                Toggle("Show Upcoming Trips", isOn: $preferences.showUpcomingTrips)

                if preferences.showUpcomingTrips {
                    Stepper("Show \(preferences.maxUpcomingTrips) trips", value: $preferences.maxUpcomingTrips, in: 1...5)
                }

                Toggle("Show Trip Stats", isOn: $preferences.showStats)
            } header: {
                Text("Home Screen")
            }

            // MARK: - Live Activity
            Section {
                if session.canUse(feature: .liveActivity) {
                    Toggle(isOn: $preferences.liveActivityEnabled) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Live Activity")
                            Text("Show trip status on Lock Screen")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    if preferences.liveActivityEnabled {
                        Picker("Display Mode", selection: $preferences.liveActivityDisplayMode) {
                            ForEach(LiveActivityDisplayMode.allCases, id: \.self) { mode in
                                Text(mode.displayName).tag(mode)
                            }
                        }
                    }
                } else {
                    // Locked state for non-premium users
                    Button(action: { showLiveActivityPaywall = true }) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 8) {
                                    Text("Live Activity")
                                    PremiumBadge()
                                }
                                Text("Show trip status on Lock Screen")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "lock.fill")
                                .foregroundStyle(.secondary)
                        }
                    }
                    .foregroundStyle(.primary)
                }
            } header: {
                Text("Live Activity")
            } footer: {
                if session.canUse(feature: .liveActivity) {
                    if preferences.liveActivityEnabled {
                        Text(preferences.liveActivityDisplayMode.description)
                    } else {
                        Text("Live Activities show your trip countdown on the Lock Screen and Dynamic Island during active trips.")
                    }
                } else {
                    Text("Upgrade to Homebound+ to enable Live Activities on your Lock Screen and Dynamic Island.")
                }
            }

            // MARK: - Sounds & Haptics
            Section {
                Toggle(isOn: $preferences.hapticFeedbackEnabled) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Haptic Feedback")
                        Text("For check-ins and actions")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Toggle(isOn: $preferences.checkInSoundEnabled) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Check-in Sound")
                        Text("Play sound on successful check-in")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            } header: {
                Text("Sounds & Haptics")
            } footer: {
                Text("System haptics on sliders and controls are managed in iOS Settings.")
            }

            // MARK: - Map
            Section {
                Picker("Default Map Style", selection: $preferences.defaultMapType) {
                    ForEach(MapType.allCases, id: \.self) { type in
                        Text(type.displayName).tag(type)
                    }
                }
            } header: {
                Text("Map")
            }

            // MARK: - Units & Formats
            Section {
                Picker("Distance Units", selection: $preferences.useMetricUnits) {
                    Text("Miles").tag(false)
                    Text("Kilometers").tag(true)
                }

                Picker("Time Format", selection: $preferences.use24HourTime) {
                    Text("12-hour").tag(false)
                    Text("24-hour").tag(true)
                }
            } header: {
                Text("Units & Formats")
            }
        }
        .scrollIndicators(.hidden)
        .navigationTitle("Customization")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showPaywall) {
            PaywallView()
                .environmentObject(session)
        }
        .sheet(isPresented: $showLiveActivityPaywall) {
            PaywallView(feature: .liveActivity)
                .environmentObject(session)
        }
        .task {
            // Load pinned activities from backend and sync to local preferences
            if canPinActivities {
                let pinnedFromBackend = await session.loadPinnedActivities()
                // Sync backend pinned activities to local preferences
                for pinned in pinnedFromBackend {
                    if !preferences.isActivityPinned(pinned.activityId) {
                        preferences.pinActivity(pinned.activityId)
                    }
                }
            }
        }
    }
}

// MARK: - Notification Settings View
struct NotificationSettingsView: View {
    @EnvironmentObject var preferences: AppPreferences
    @EnvironmentObject var session: Session
    @State private var notificationsAuthorized = false
    @State private var showingSystemSettings = false

    var body: some View {
        List {
            // System permissions section
            Section {
                HStack {
                    Label {
                        Text("System Notifications")
                    } icon: {
                        Image(systemName: notificationsAuthorized ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundStyle(notificationsAuthorized ? .green : .red)
                    }

                    Spacer()

                    if !notificationsAuthorized {
                        Button("Enable") {
                            openSystemSettings()
                        }
                        .font(.subheadline)
                        .foregroundStyle(Color.hbBrand)
                    } else {
                        Text("Enabled")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            } footer: {
                if !notificationsAuthorized {
                    Text("Enable notifications in System Settings to receive alerts about your trips.")
                }
            }

            // Trip notifications
            Section {
                Toggle(isOn: Binding(
                    get: { preferences.tripRemindersEnabled },
                    set: { newValue in
                        preferences.tripRemindersEnabled = newValue
                        Task {
                            await session.syncNotificationPreferences(
                                tripReminders: newValue,
                                checkInAlerts: preferences.checkInAlertsEnabled
                            )
                        }
                    }
                )) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Trip Reminders")
                        Text("Get notified before trips start and when approaching ETA")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(!notificationsAuthorized)

                Toggle(isOn: Binding(
                    get: { preferences.checkInAlertsEnabled },
                    set: { newValue in
                        preferences.checkInAlertsEnabled = newValue
                        Task {
                            await session.syncNotificationPreferences(
                                tripReminders: preferences.tripRemindersEnabled,
                                checkInAlerts: newValue
                            )
                        }
                    }
                )) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Check-in Alerts")
                        Text("Reminders to check in during active trips")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(!notificationsAuthorized)
            } header: {
                Text("Trip Notifications")
            }

            // Emergency notifications - always enabled for safety
            Section {
                Toggle(isOn: .constant(true)) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Emergency Notifications")
                        Text("Critical alerts when you're overdue")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(true)
                .tint(.green)
            } header: {
                Text("Safety Alerts")
            } footer: {
                Text("Emergency notifications cannot be disabled to keep you safe. They will override Do Not Disturb.")
            }
        }
        .scrollIndicators(.hidden)
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            checkNotificationStatus()
        }
    }

    private func checkNotificationStatus() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                notificationsAuthorized = settings.authorizationStatus == .authorized
            }
        }
    }

    private func openSystemSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }
}

struct PrivacyView: View {
    @EnvironmentObject var session: Session
    @State private var locationStatus: CLAuthorizationStatus = .notDetermined
    @State private var isExporting = false
    @State private var showShareSheet = false
    @State private var exportData: Data?

    // Local storage counts (cached trips/activities loaded on appear, pending uses session's reactive property)
    @State private var cachedTripsCount = 0
    @State private var cachedActivitiesCount = 0

    var body: some View {
        List {
            // Location Section
            Section {
                HStack {
                    Label {
                        Text("Location Access")
                    } icon: {
                        Image(systemName: "location.fill")
                            .foregroundStyle(locationStatusColor)
                    }

                    Spacer()

                    Text(locationStatusText)
                        .foregroundStyle(.secondary)
                        .font(.subheadline)
                }

                if locationStatus == .denied || locationStatus == .restricted {
                    Button {
                        openSystemSettings()
                    } label: {
                        Label("Open Settings", systemImage: "gear")
                    }
                }
            } header: {
                Text("Location")
            } footer: {
                Text("Homebound uses your location to set trip locations and show nearby places. Your location is never tracked in the background.")
            }

            // Your Data Section
            Section {
                Button {
                    Task {
                        await exportUserData()
                    }
                } label: {
                    HStack {
                        Label {
                            Text("Export My Data")
                        } icon: {
                            Image(systemName: "square.and.arrow.up")
                                .foregroundStyle(.blue)
                        }

                        Spacer()

                        if isExporting {
                            ProgressView()
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .disabled(isExporting)
            } header: {
                Text("Your Data")
            } footer: {
                Text("Download a copy of your profile, trips, and contacts as a JSON file.")
            }

            // Local Storage Section
            Section {
                HStack {
                    Text("Cached Trips")
                    Spacer()
                    Text("\(cachedTripsCount)")
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Text("Cached Activities")
                    Spacer()
                    Text("\(cachedActivitiesCount)")
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Text("Pending Offline Actions")
                    Spacer()
                    Text("\(session.pendingActionsCount)")
                        .foregroundStyle(.secondary)
                    if session.pendingActionsCount > 0 {
                        Button("Clear") {
                            session.clearPendingActions()
                        }
                        .font(.caption)
                        .foregroundStyle(.red)
                    }
                }
            } header: {
                Text("Local Storage")
            } footer: {
                Text("Data cached on your device for offline access. Clear this in Settings > Resources > Clear Cache.")
            }
        }
        .scrollIndicators(.hidden)
        .navigationTitle("Privacy")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            checkLocationStatus()
            loadStorageCounts()
        }
        .sheet(isPresented: $showShareSheet) {
            if let data = exportData,
               let fileURL = writeExportDataToTempFile(data) {
                ShareSheet(activityItems: [fileURL])
            }
        }
    }

    private var locationStatusColor: Color {
        switch locationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            return .green
        case .denied, .restricted:
            return .red
        default:
            return .orange
        }
    }

    private var locationStatusText: String {
        switch locationStatus {
        case .authorizedWhenInUse:
            return "While Using"
        case .authorizedAlways:
            return "Always"
        case .denied:
            return "Denied"
        case .restricted:
            return "Restricted"
        case .notDetermined:
            return "Not Set"
        @unknown default:
            return "Unknown"
        }
    }

    private func checkLocationStatus() {
        locationStatus = CLLocationManager().authorizationStatus
    }

    private func openSystemSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }

    private func loadStorageCounts() {
        cachedTripsCount = LocalStorage.shared.getCachedTripsCount()
        cachedActivitiesCount = LocalStorage.shared.getCachedActivitiesCount()
    }

    private func exportUserData() async {
        isExporting = true
        defer { isExporting = false }

        if let data = await session.exportUserData() {
            await MainActor.run {
                exportData = data
                showShareSheet = true
            }
        }
    }

    private func writeExportDataToTempFile(_ data: Data) -> URL? {
        let tempDir = FileManager.default.temporaryDirectory
        let fileURL = tempDir.appendingPathComponent("homebound-export.json")
        do {
            try data.write(to: fileURL)
            return fileURL
        } catch {
            print("Failed to write export file: \(error)")
            return nil
        }
    }
}

// UIKit share sheet wrapper
struct ShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(
            activityItems: activityItems,
            applicationActivities: nil
        )
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct AboutView: View {
    @EnvironmentObject var session: Session
    @State private var stats: GlobalStats?
    @State private var isLoadingStats = true

    // MARK: - Mission Text (Edit these strings to update content)
    private let missionTitle = "Our Mission"
    private let missionTagline = "Plan in seconds. Get found fast."

    private let missionParagraph1 =
    "Homebound was built for a simple reason: every adventure should end with you safely back home."

    private let missionParagraph2 =
    "We help turn a quick, 10-second check-in into a meaningful signal. Share a basic plan and an ETA, then if you don’t check out, the people you chose can get the last-known details to start looking sooner."

    private let missionParagraph3 =
    "Our goal is to make searches smaller and rescues faster. Especially for day trips, which make up one of the biggest shares of park search and rescue calls."

    private let missionParagraph4 =
    "We’re building Homebound to be private by design and only track you when you explicitly choose to. No matter what, you are in control of your data and who sees it."

    private let missionFootnote =
    "Informed by patterns seen across decades of SAR reports and beacon outcomes, we’re aiming to prevent or significantly shorten a large share of lost-person incidents—across outdoor activities."
        
    private let aboutSections: [(title: String, body: String)] = [
        (
            "Why we built Homebound",
            "Most trips are uneventful, until they aren’t. When something goes wrong, the hardest part is often the first few hours: figuring out where to start. Homebound exists to make that starting point clearer, faster, and less stressful for everyone involved."
        ),
        (
            "What Homebound does",
            "• You set a simple plan (where, when, and who should know).\n" +
            "• You check in along the way if you want.\n" +
            "• If you miss checkout, your trusted contacts can be alerted with the details they need to help you."
        ),
        (
            "How it works",
            "1) Create a trip: destination, departure time, ETA, grace period, and notes.\n" +
            "2) Choose who to share with.\n" +
            "3) Check in (optional) during the trip.\n" +
            "4) Check out when you’re safe.\n\n" +
            "If checkout is missed, Homebound will prompt your contacts with last-known info so they can act quickly."
        ),
        (
            "Privacy by design",
            "Homebound is built to help you if trouble arrises. Not to watch you.\n\n" +
            "• No continuous tracking by default.\n" +
            "• You decide what to share and with whom.\n" +
            "• The goal is only to use location and trip details when they’re genuinely needed."
        ),
        (
            "Safety note",
            "Homebound is a safety tool, not a guarantee. Conditions, devices, and connectivity can fail.\n\n" +
            "Always carry the right gear for your activity (water, layers, light, navigation, etc.), and consider a dedicated SOS device for remote areas."
        ),
        (
            "Who it’s for",
            "Hikers, runners, skiers, climbers, surfers, divers, anyone who wants a simple way to create and share a plan. All to hopefully make the “where do we start looking?” moment easy if something were to go wrong."
        ),
        (
            "Built with gratitude",
            "To the search and rescue volunteers, rangers, patrol, and dispatch teams who drop everything to help strangers: thank you. Homebound is built with deep respect for your time and for the families waiting for answers."
        ),
        (
            "Help us improve",
            "If something feels confusing, slow, unreliable or you find a bug, we want to hear it. Your feedback directly shapes what we build next.\n" +
            "Report bugs and new feautures at the links in Settings under Resources.\n"
        )
    ]

    var body: some View {
        List {
            // Mission Section
            Section {
                VStack(alignment: .leading, spacing: 16) {
                    Text(missionParagraph1)
                        .font(.body)

                    Text(missionParagraph2)
                        .font(.body)

                    Text(missionParagraph3)
                        .font(.body)

                    Text(missionParagraph4)
                        .font(.body)

                    Text("“\(missionTagline)”")
                        .font(.headline)
                        .italic()
                        .padding(.top, 4)

                    Text(missionFootnote)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .padding(.top, 2)
                }
                .padding(.vertical, 8)
            } header: {
                Text(missionTitle)
            }

            // Other About Sections
            ForEach(aboutSections, id: \.title) { section in
                Section {
                    Text(section.body)
                        .font(.body)
                        .padding(.vertical, 8)
                } header: {
                    Text(section.title)
                }
            }

            // Community Stats Section
            if let stats = stats {
                Section {
                    HStack(spacing: 16) {
                        StatCard(
                            value: formatNumber(stats.total_users),
                            label: "adventurers"
                        )

                        StatCard(
                            value: formatNumber(stats.total_completed_trips),
                            label: "trips completed safely"
                        )
                    }
                    .listRowInsets(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16))
                    .listRowBackground(Color.clear)
                } header: {
                    Text("Community")
                }
            } else if isLoadingStats {
                Section {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                    .listRowBackground(Color.clear)
                } header: {
                    Text("Community")
                }
            }
        }
        .scrollIndicators(.hidden)
        .navigationTitle("About")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            stats = await session.fetchGlobalStats()
            isLoadingStats = false
        }
    }

    private func formatNumber(_ number: Int) -> String {
        if number >= 1000 {
            let thousands = Double(number) / 1000.0
            return String(format: "%.1fK", thousands)
        }
        return "\(number)"
    }
}

private struct StatCard: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title)
                .fontWeight(.bold)
                .foregroundStyle(Color.hbBrand)

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - Friends Settings View

struct FriendsSettingsView: View {
    @EnvironmentObject var preferences: AppPreferences
    @State private var isEditing = false

    var body: some View {
        List {
            Section {
                Text("Choose what information is visible when viewing a friend's profile. Drag to reorder.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .listRowBackground(Color.clear)

            Section("Always Shown") {
                HStack {
                    Image(systemName: "person.fill")
                        .foregroundStyle(.secondary)
                        .frame(width: 24)
                    Text("Name")
                    Spacer()
                    Image(systemName: "lock.fill")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }

                HStack {
                    Image(systemName: "heart.fill")
                        .foregroundStyle(.secondary)
                        .frame(width: 24)
                    Text("Friends Since")
                    Spacer()
                    Image(systemName: "lock.fill")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }

            Section("Stats") {
                ForEach(preferences.friendStatOrder) { statType in
                    HStack {
                        Image(systemName: statType.icon)
                            .foregroundStyle(statType.iconColor)
                            .frame(width: 24)

                        Text(statType.displayName)

                        Spacer()

                        Toggle("", isOn: binding(for: statType))
                            .labelsHidden()
                    }
                }
                .onMove { from, to in
                    preferences.friendStatOrder.move(fromOffsets: from, toOffset: to)
                }
            }
            .environment(\.editMode, .constant(.active))

            Section {
                NavigationLink(destination: FriendVisibilitySettingsView()) {
                    HStack {
                        Image(systemName: "eye.fill")
                            .foregroundStyle(.blue)
                            .frame(width: 24)
                        Text("What Friends See About You")
                    }
                }
            } header: {
                Text("Trip Visibility")
            } footer: {
                Text("Control what information friends can see when they're your safety contacts.")
            }
        }
        .scrollIndicators(.hidden)
        .navigationTitle("Friends")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func binding(for statType: FriendStatType) -> Binding<Bool> {
        switch statType {
        case .joinDate:
            return $preferences.showFriendJoinDate
        case .age:
            return $preferences.showFriendAge
        case .achievements:
            return $preferences.showFriendAchievements
        case .totalTrips:
            return $preferences.showFriendTotalTrips
        case .adventureTime:
            return $preferences.showFriendAdventureTime
        case .favoriteActivity:
            return $preferences.showFriendFavoriteActivity
        }
    }
}

// MARK: - Friend Visibility Settings View

struct FriendVisibilitySettingsView: View {
    @EnvironmentObject var session: Session
    @State private var settings: FriendVisibilitySettings = .defaults
    @State private var isLoading = true
    @State private var isSaving = false
    @State private var showLocationPermissionAlert = false

    var body: some View {
        List {
            Section {
                Toggle(isOn: $settings.friend_share_checkin_locations) {
                    Label("Share check-in locations", systemImage: "mappin.circle.fill")
                }
                .onChange(of: settings.friend_share_checkin_locations) { _, _ in saveSettings() }

                Toggle(isOn: $settings.friend_share_live_location) {
                    Label("Allow live location sharing", systemImage: "location.fill")
                }
                .onChange(of: settings.friend_share_live_location) { _, newValue in
                    if newValue && !LiveLocationManager.shared.hasRequiredAuthorization {
                        // Request permission upgrade - don't reset toggle yet
                        LiveLocationManager.shared.requestPermissionIfNeeded()
                        // Show alert explaining they may need to go to Settings
                        showLocationPermissionAlert = true
                        // Don't save yet - wait for permission check on app active
                        return
                    }
                    saveSettings()
                }

                Toggle(isOn: $settings.friend_share_notes) {
                    Label("Share trip notes", systemImage: "note.text")
                }
                .onChange(of: settings.friend_share_notes) { _, _ in saveSettings() }

                Toggle(isOn: $settings.friend_allow_update_requests) {
                    Label("Allow update requests", systemImage: "bell.badge.fill")
                }
                .onChange(of: settings.friend_allow_update_requests) { _, _ in saveSettings() }

                Toggle(isOn: $settings.friend_share_achievements) {
                    Label("Share achievements", systemImage: "trophy.fill")
                }
                .onChange(of: settings.friend_share_achievements) { _, _ in saveSettings() }
            } header: {
                Text("Trip visibility")
            } footer: {
                Text("These settings apply when friends are your safety contacts during trips.")
            }

            Section {
                Toggle(isOn: $settings.friend_share_age) {
                    Label("Share your age", systemImage: "number.circle.fill")
                }
                .onChange(of: settings.friend_share_age) { _, _ in saveSettings() }

                Toggle(isOn: $settings.friend_share_total_trips) {
                    Label("Share total trips", systemImage: "figure.hiking")
                }
                .onChange(of: settings.friend_share_total_trips) { _, _ in saveSettings() }

                Toggle(isOn: $settings.friend_share_adventure_time) {
                    Label("Share adventure time", systemImage: "clock.fill")
                }
                .onChange(of: settings.friend_share_adventure_time) { _, _ in saveSettings() }

                Toggle(isOn: $settings.friend_share_favorite_activity) {
                    Label("Share favorite activity", systemImage: "star.fill")
                }
                .onChange(of: settings.friend_share_favorite_activity) { _, _ in saveSettings() }
            } header: {
                Text("Profile stats")
            } footer: {
                Text("Control what stats friends see on your mini profile.")
            }

            Section {
                VStack(alignment: .leading, spacing: 12) {
                    Label("Friends vs Email Contacts", systemImage: "person.2.fill")
                        .font(.headline)

                    Text("Friends (app users) receive:")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    VStack(alignment: .leading, spacing: 6) {
                        BulletPoint("Check-in locations on a map")
                        BulletPoint("Real-time location (if enabled)")
                        BulletPoint("Rich overdue alerts with last known location")
                        BulletPoint("Ability to request updates")
                        BulletPoint("Achievement progress and details")
                    }

                    Text("Email contacts only receive basic notifications.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }
                .padding(.vertical, 4)
            } header: {
                Text("Why share more with friends?")
            }
        }
        .navigationTitle("Friend Visibility")
        .navigationBarTitleDisplayMode(.inline)
        .overlay {
            if isLoading {
                ProgressView()
            }
        }
        .disabled(isSaving)
        .task {
            await loadSettings()
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
            // Re-check permission when app becomes active (after returning from Settings)
            if settings.friend_share_live_location && !LiveLocationManager.shared.hasRequiredAuthorization {
                settings.friend_share_live_location = false
            } else if settings.friend_share_live_location {
                // Permission was granted, now save the setting
                saveSettings()
            }
        }
        .alert("Location Permission Required", isPresented: $showLocationPermissionAlert) {
            Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Live location sharing requires 'Always Allow' location permission so your friends can see your location even when the app is in the background. Please enable it in Settings.")
        }
    }

    private func loadSettings() async {
        isLoading = true
        settings = await session.loadFriendVisibilitySettings()
        isLoading = false
    }

    private func saveSettings() {
        isSaving = true
        Task {
            let success = await session.saveFriendVisibilitySettings(settings)
            await MainActor.run {
                isSaving = false
                if !success {
                    // Settings will be reloaded on next view appearance
                }
            }
        }
    }
}

private struct BulletPoint: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
                .font(.caption)
            Text(text)
                .font(.caption)
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(Session())
        .environmentObject(AppPreferences.shared)
}
