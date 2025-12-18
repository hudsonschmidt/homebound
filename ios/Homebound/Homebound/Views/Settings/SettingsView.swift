import SwiftUI
import Combine
import UserNotifications
import CoreLocation
import UniformTypeIdentifiers

// MARK: - App Preferences
private var preferenceCancellables = Set<AnyCancellable>()

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
    @Published var hapticFeedbackEnabled: Bool = true
    @Published var checkInSoundEnabled: Bool = true

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

    var shouldShowWhatsNew: Bool {
        let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
        // Only show if user has seen a previous version (not a fresh install) and it's different from current
        return !lastSeenWhatsNewVersion.isEmpty && lastSeenWhatsNewVersion != currentVersion
    }

    func markWhatsNewAsSeen() {
        let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
        lastSeenWhatsNewVersion = currentVersion
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

        // Home Screen - defaults to true/shown
        self.showUpcomingTrips = UserDefaults.standard.object(forKey: "showUpcomingTrips") == nil ? true : UserDefaults.standard.bool(forKey: "showUpcomingTrips")
        self.showStats = UserDefaults.standard.object(forKey: "showStats") == nil ? true : UserDefaults.standard.bool(forKey: "showStats")
        let savedMaxTrips = UserDefaults.standard.integer(forKey: "maxUpcomingTrips")
        self.maxUpcomingTrips = savedMaxTrips > 0 ? savedMaxTrips : 3

        // Sounds & Haptics - defaults to true/enabled
        self.hapticFeedbackEnabled = UserDefaults.standard.object(forKey: "hapticFeedbackEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "hapticFeedbackEnabled")
        self.checkInSoundEnabled = UserDefaults.standard.object(forKey: "checkInSoundEnabled") == nil ? true : UserDefaults.standard.bool(forKey: "checkInSoundEnabled")

        // Set up Combine subscribers to persist Sounds & Haptics changes
        // Using Combine instead of didSet because didSet doesn't reliably fire through SwiftUI bindings
        $hapticFeedbackEnabled
            .dropFirst()
            .sink { UserDefaults.standard.set($0, forKey: "hapticFeedbackEnabled") }
            .store(in: &preferenceCancellables)

        $checkInSoundEnabled
            .dropFirst()
            .sink { UserDefaults.standard.set($0, forKey: "checkInSoundEnabled") }
            .store(in: &preferenceCancellables)

        // Map
        let mapTypeRaw = UserDefaults.standard.string(forKey: "defaultMapType") ?? "standard"
        self.defaultMapType = MapType(rawValue: mapTypeRaw) ?? .standard

        // Units & Formats - default to locale-appropriate
        self.useMetricUnits = UserDefaults.standard.object(forKey: "useMetricUnits") == nil ? Locale.current.measurementSystem == .metric : UserDefaults.standard.bool(forKey: "useMetricUnits")
        self.use24HourTime = UserDefaults.standard.object(forKey: "use24HourTime") == nil ? false : UserDefaults.standard.bool(forKey: "use24HourTime")

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
    @Environment(\.dismiss) var dismiss
    @State private var showingClearCacheAlert = false
    @State private var showingWhatsNew = false

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
                if session.userEmail == "hudsonschmidt08@gmail.com" {
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

    let graceOptions = [15, 30, 45, 60, 90]

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
            } header: {
                Text("Live Activity")
            } footer: {
                if preferences.liveActivityEnabled {
                    Text(preferences.liveActivityDisplayMode.description)
                } else {
                    Text("Live Activities show your trip countdown on the Lock Screen and Dynamic Island during active trips.")
                }
            }

            // MARK: - Sounds & Haptics
            Section {
                Toggle("Haptic Feedback", isOn: $preferences.hapticFeedbackEnabled)
                Toggle("Check-in Sound", isOn: $preferences.checkInSoundEnabled)
            } header: {
                Text("Sounds & Haptics")
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
    var body: some View {
        List {
            Section {
                HStack {
                    Text("Made with ❤️ in California")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .scrollIndicators(.hidden)
        .navigationTitle("About")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    SettingsView()
        .environmentObject(Session())
        .environmentObject(AppPreferences.shared)
}