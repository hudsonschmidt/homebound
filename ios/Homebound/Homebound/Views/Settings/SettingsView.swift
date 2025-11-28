import SwiftUI
import PhotosUI
import Combine
import UserNotifications

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
                                .foregroundStyle(.purple)
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

                // Developer Section (only visible to developer)
                if session.userEmail == "hudsonschmidt08@gmail.com" {
                    Section("Developer") {
                        Toggle(isOn: Binding(
                            get: { session.useLocalServer },
                            set: { newValue in
                                session.useLocalServer = newValue
                            }
                        )) {
                            Label {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Use Local Server")
                                    Text(session.useLocalServer ? "Local Mac" : "Render")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            } icon: {
                                Image(systemName: "server.rack")
                                    .foregroundStyle(session.useLocalServer ? .green : .purple)
                            }
                        }
                    }
                }

                // Support Section
                Section("Support (Coming Soon)") {
                    Link(destination: URL(string: "https://homeboundapp.com/help")!) {
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
                                Text("Contact Us (Coming Soon)")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "envelope.fill")
                                .foregroundStyle(.green)
                        }
                    }
                }

                // Resources Section
                Section("Resources") {
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

                    Button(action: {
                        // TODO: Open App Store for rating
                    }) {
                        Label {
                            HStack {
                                Text("Rate in App Store (Coming Soon)")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "star.fill")
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
                                .foregroundStyle(.purple)
                        }
                    }
                    .foregroundStyle(.primary)
                }

                // Version info at bottom
                Section {
                    HStack {
                        Text("Version")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("1.0.0")
                            .foregroundStyle(.secondary)
                    }
                    .listRowBackground(Color.clear)
                }
            }
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

    @State private var showingImagePicker = false
    @State private var selectedImage: PhotosPickerItem?
    @State private var profileImage: UIImage?

    @State private var showingDeleteAlert = false
    @State private var deleteConfirmation = ""
    @State private var isDeleting = false

    @State private var showingLogoutAlert = false

    var body: some View {
        List {
            // Profile Photo Section
            Section {
                HStack {
                    Spacer()

                    PhotosPicker(selection: $selectedImage, matching: .images) {
                        ZStack {
                            if let profileImage = profileImage {
                                Image(uiImage: profileImage)
                                    .resizable()
                                    .scaledToFill()
                                    .frame(width: 120, height: 120)
                                    .clipShape(Circle())
                            } else {
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
                            }

                            // Camera icon overlay
                            Circle()
                                .fill(Color(.systemBackground))
                                .frame(width: 36, height: 36)
                                .overlay(
                                    Circle()
                                        .stroke(Color(.systemGray4), lineWidth: 1)
                                )
                                .overlay(
                                    Image(systemName: "camera.fill")
                                        .font(.system(size: 16))
                                        .foregroundStyle(Color.hbBrand)
                                )
                                .offset(x: 40, y: 40)
                        }
                    }
                    .onChange(of: selectedImage) { _, newItem in
                        Task {
                            if let data = try? await newItem?.loadTransferable(type: Data.self),
                               let image = UIImage(data: data) {
                                profileImage = image
                            }
                        }
                    }

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
                            .onSubmit {
                                saveAge()
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
        .navigationTitle("Customization")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Notification Settings View
struct NotificationSettingsView: View {
    @EnvironmentObject var preferences: AppPreferences
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
                Toggle(isOn: $preferences.tripRemindersEnabled) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Trip Reminders")
                        Text("Get notified before trips start and when approaching ETA")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(!notificationsAuthorized)

                Toggle(isOn: $preferences.checkInAlertsEnabled) {
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

            // Emergency notifications
            Section {
                Toggle(isOn: $preferences.emergencyNotificationsEnabled) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Emergency Notifications")
                        Text("Critical alerts when you're overdue")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(!notificationsAuthorized)
            } header: {
                Text("Safety Alerts")
            } footer: {
                Text("Emergency notifications are high priority and will override Do Not Disturb.")
            }
        }
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
    var body: some View {
        List {
            Section("Data & Privacy") {
                Text("Your data is encrypted and secure")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Privacy")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct AboutView: View {
    var body: some View {
        List {
            Section {
                HStack {
                    Text("Version")
                    Spacer()
                    Text("1.0.0")
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Text("Build")
                    Spacer()
                    Text("100")
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                Link("Terms of Service", destination: URL(string: "https://homeboundapp.com/terms")!)
                Link("Privacy Policy", destination: URL(string: "https://homeboundapp.com/privacy")!)
            }
        }
        .navigationTitle("About")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    SettingsView()
        .environmentObject(Session())
        .environmentObject(AppPreferences.shared)
}