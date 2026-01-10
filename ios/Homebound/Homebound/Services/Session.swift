import Foundation
import Combine
import CoreLocation
import WidgetKit

// MARK: - Server Environment
enum ServerEnvironment: String, CaseIterable {
    case production = "production"
    case devRender = "devRender"
    case local = "local"

    var displayName: String {
        switch self {
        case .production: return "Production"
        case .devRender: return "Dev Render"
        case .local: return "Local"
        }
    }
}

// MARK: Routes
private enum Routes {
    static let sendCode  = "/api/v1/auth/request-magic-link"
    static let verify    = "/api/v1/auth/verify"
    static let refresh   = "/api/v1/auth/refresh"
}

private struct SendCodeRequest: Encodable {
    let email: String
}

private struct SendCodeResponse: Decodable {
    let ok: Bool?
    let message: String?
}

private struct VerifyRequest: Encodable {
    let email: String
    let code: String
}

private struct VerifyResponse: Decodable {
    let access: String?
    let refresh: String?
    let access_token: String?  // Fallback for compatibility
    let token: String?         // Fallback for compatibility
    let user: UserSummary?
    let message: String?
    struct UserSummary: Decodable {
        let id: Int?
        let email: String?
        let first_name: String?
        let last_name: String?
        let name: String?  // Fallback for compatibility
        let age: Int?
        let profile_completed: Bool?
    }
}

private struct GenericResponse: Decodable {
    let ok: Bool?
    let message: String?
}

private struct RefreshRequest: Encodable {
    let refresh_token: String
}

private struct RefreshResponse: Decodable {
    let access: String?
    let refresh: String?
    let access_token: String?  // Fallback for compatibility
    let user: UserSummary?  // Include user data from refresh

    struct UserSummary: Decodable {
        let id: Int?
        let email: String?
        let first_name: String?
        let last_name: String?
        let name: String?  // Fallback for compatibility
        let age: Int?
        let profile_completed: Bool?
    }
}
final class Session: ObservableObject {

    // MARK: - Shared Instance
    /// Shared singleton instance for use in non-SwiftUI contexts (widgets, background tasks, etc.)
    static let shared = Session()

    // MARK: API & Base URL

    static let productionURL: URL = {
        guard let url = URL(string: "https://api.homeboundapp.com") else {
            fatalError("Invalid production URL configuration")
        }
        return url
    }()

    static let devRenderURL: URL = {
        guard let url = URL(string: "https://homebound-21l1.onrender.com") else {
            fatalError("Invalid dev Render URL configuration")
        }
        return url
    }()

    static let localURL: URL = {
        guard let url = URL(string: "http://Hudsons-MacBook-Pro-337.local:3001") else {
            fatalError("Invalid local URL configuration")
        }
        return url
    }()

    @Published var serverEnvironment: ServerEnvironment = {
        let savedValue = UserDefaults.standard.string(forKey: "serverEnvironment") ?? "production"
        return ServerEnvironment(rawValue: savedValue) ?? .production
    }() {
        didSet {
            // When switching databases, sign out and clear all cached data
            // This prevents data mismatch between different databases
            if oldValue != serverEnvironment {
                signOut()
            }
            UserDefaults.standard.set(serverEnvironment.rawValue, forKey: "serverEnvironment")
            // Sync to app group for widget/live activity access
            LiveActivityConstants.setServerEnvironment(serverEnvironment.rawValue)
        }
    }

    var baseURL: URL {
        switch serverEnvironment {
        case .production: return Self.productionURL
        case .devRender: return Self.devRenderURL
        case .local: return Self.localURL
        }
    }

    /// Use real API client from `API.swift`
    let api = API()
    let keychain = KeychainHelper.shared

    // MARK: Auth/UI State

    @Published var email: String = ""
    @Published var code: String = ""
    @Published var showCodeSheet: Bool = false

    @Published var isRequesting: Bool = false
    @Published var isVerifying: Bool = false
    @Published var isAuthenticated: Bool = false

    @Published var error: String?
    @Published var notice: String = ""
    @Published var lastError: String = ""
    @Published var apnsToken: String? = nil
    private var deviceRegistrationRetryCount: Int = 0
    private let maxDeviceRegistrationRetries: Int = 3
    private var deviceRegistrationTask: Task<Void, Never>?

    /// Lock to prevent concurrent token refresh operations
    private var isRefreshingToken: Bool = false
    private var tokenRefreshContinuations: [CheckedContinuation<Bool, Never>] = []
    private let tokenRefreshTimeoutSeconds: TimeInterval = 30
    @Published var accessToken: String? = nil {
        didSet {
            // Save to both keychain and local storage for redundancy
            if let token = accessToken {
                keychain.saveAccessToken(token)
                // Also save to local storage as backup
                let refreshToken = keychain.getRefreshToken()
                LocalStorage.shared.saveAuthTokens(access: token, refresh: refreshToken)
                debugLog("[Session] ✅ Access token saved to keychain and local storage")

                // Register pending APNs token only on initial auth (not on token refresh)
                // This prevents redundant device registration on every token refresh
                if oldValue == nil, let apns = apnsToken {
                    Task { @MainActor in
                        self.handleAPNsToken(apns)
                    }
                }
            } else {
                debugLog("[Session] ⚠️ Access token set to nil")
            }
        }
    }

    // User profile
    @Published var userId: Int? = nil {
        didSet {
            saveUserDataToKeychain()
        }
    }
    @Published var userName: String? = nil {
        didSet {
            saveUserDataToKeychain()
        }
    }
    @Published var userAge: Int? = nil {
        didSet {
            saveUserDataToKeychain()
        }
    }
    @Published var userEmail: String? = nil {
        didSet {
            saveUserDataToKeychain()
        }
    }
    @Published var memberSince: Date? = nil
    @Published var profileCompleted: Bool = false {
        didSet {
            saveUserDataToKeychain()
        }
    }

    // Apple Sign In
    @Published var showAppleLinkAlert: Bool = false
    @Published var pendingAppleUserID: String? = nil
    @Published var pendingAppleEmail: String? = nil
    @Published var pendingAppleIdentityToken: String? = nil
    @Published var appleFirstName: String? = nil
    @Published var appleLastName: String? = nil

    // Active plan
    @Published var activeTrip: Trip? = nil
    @Published var allTrips: [Trip] = []
    @Published var isLoadingTrip: Bool = false

    // Offline state
    @Published var isOffline: Bool = false
    @Published var pendingActionsCount: Int = 0
    @Published var failedActionsCount: Int = 0

    // Activities
    @Published var activities: [Activity] = []
    @Published var isLoadingActivities: Bool = false

    // Contacts
    @Published var contacts: [Contact] = []

    // Friends
    @Published var friends: [Friend] = []
    @Published var pendingInvites: [PendingInvite] = []
    @Published var friendActiveTrips: [FriendActiveTrip] = []
    @Published var friendVisibilitySettings: FriendVisibilitySettings = .defaults
    @Published var tripInvitations: [TripInvitation] = []  // Pending group trip invitations

    // Subscription
    @Published var featureLimits: FeatureLimits = .free
    @Published var subscriptionTier: String = "free"
    @Published var debugSubscriptionTier: String = ""  // For developer testing: "", "free", or "plus"

    // Realtime update triggers - views observe these to know when to refresh
    @Published var timelineLastUpdated: Date = Date()

    // Active trip vote status (for group trips with vote checkout mode)
    @Published var activeVoteStatus: (tripId: Int, votesCast: Int, votesNeeded: Int, userHasVoted: Bool)? = nil

    // Update request cooldowns (trip_id -> cooldown_end_time)
    var updateRequestCooldowns: [Int: Date] = [:]

    /// Timestamp of last local activeTrip update to prevent Realtime race conditions
    /// When extending a trip, we update activeTrip locally. RealtimeManager then triggers
    /// loadActivePlan() which could overwrite with stale server data. This timestamp allows
    /// us to skip loadActivePlan() calls that happen immediately after local updates.
    private var lastLocalTripUpdate: Date?

    /// Flag to COMPLETELY block activeTrip updates during trip extension
    /// This is an aggressive protection that rejects ALL updates while extension is in progress
    private var isExtensionInProgress: Bool = false
    /// The expected new ETA during extension (for validation/logging)
    private var extensionNewETA: Date? = nil

    // Saved trip templates (local-only)
    @Published var savedTemplates: [SavedTripTemplate] = []

    // Initial data loading state
    @Published var isInitialDataLoaded: Bool = false

    private var networkObserver: NSObjectProtocol?
    private var backgroundSyncObserver: NSObjectProtocol?

    init() {
        // Load saved tokens and user data on init
        loadFromKeychain()

        // Sync server environment to app group for widget/live activity access
        LiveActivityConstants.setServerEnvironment(serverEnvironment.rawValue)

        // Log cache statistics for debugging
        let tripCount = LocalStorage.shared.getCachedTripsCount()
        let activityCount = LocalStorage.shared.getCachedActivitiesCount()
        let contactCount = LocalStorage.shared.getCachedContactsCount()
        let templateCount = LocalStorage.shared.getSavedTemplatesCount()
        debugLog("[Session] 📊 Cache stats: \(tripCount) trips, \(activityCount) activities, \(contactCount) contacts, \(templateCount) templates")

        // Load saved templates (not auth-dependent, stored locally)
        savedTemplates = LocalStorage.shared.getTemplates()

        // Load cached data immediately for instant offline support
        if accessToken != nil {
            let cachedTrips = LocalStorage.shared.getCachedTrips()
            self.allTrips = cachedTrips
            // Include active, overdue, and overdue_notified statuses (all "in progress" trips)
            self.activeTrip = cachedTrips.first { Constants.TripStatus.isActive($0.status) }
            self.contacts = LocalStorage.shared.getCachedContacts()
            self.activities = LocalStorage.shared.getCachedActivities()
            debugLog("[Session] ℹ️ Loaded cached data: \(cachedTrips.count) trips, \(contacts.count) contacts, \(activities.count) activities")
        }

        // Initialize pending actions count
        pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
        failedActionsCount = LocalStorage.shared.getFailedActionsCount()

        // Set up network monitoring
        setupNetworkMonitoring()

        // Activities are already loaded from cache above
        // loadInitialData() will refresh from network when appropriate
    }

    private func setupNetworkMonitoring() {
        // Observe network reconnection to sync pending actions
        networkObserver = NotificationCenter.default.addObserver(
            forName: .networkDidReconnect,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            Task { @MainActor in
                self.isOffline = false
                debugLog("[Session] 🌐 Network reconnected - syncing pending actions")
                await self.syncPendingActions()
            }
        }

        // Observe background sync requests (from background tasks and silent push)
        backgroundSyncObserver = NotificationCenter.default.addObserver(
            forName: .backgroundSyncRequested,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            Task { @MainActor in
                debugLog("[Session] 🔄 Background sync requested")
                await self.syncPendingActions()
            }
        }

        // Set initial offline state
        isOffline = !NetworkMonitor.shared.isConnected
    }

    deinit {
        if let observer = networkObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = backgroundSyncObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    private func loadFromKeychain() {
        // Try loading from keychain first
        accessToken = keychain.getAccessToken()

        // If keychain fails, try LocalStorage as backup
        if accessToken == nil {
            let tokens = LocalStorage.shared.getAuthTokens()
            if let access = tokens.access {
                debugLog("[Session] ℹ️ Loaded access token from LocalStorage backup")
                accessToken = access
                // Restore to keychain
                keychain.saveAccessToken(access)
            }
            if let refresh = tokens.refresh {
                keychain.saveRefreshToken(refresh)
            }
        }

        userId = keychain.getUserId()
        userName = keychain.getUserName()
        userEmail = keychain.getUserEmail()
        userAge = keychain.getUserAge()

        // Profile is completed if we have a name stored
        // This ensures existing users don't see onboarding again
        if let name = userName, !name.isEmpty {
            profileCompleted = true
        } else {
            profileCompleted = keychain.getProfileCompleted()
        }

        // If we have a token, we're authenticated
        if accessToken != nil {
            isAuthenticated = true
            debugLog("[Session] ✅ Loaded auth token - user authenticated")
        } else {
            debugLog("[Session] ℹ️ No auth token found - user not authenticated")
        }
    }

    private func saveUserDataToKeychain() {
        keychain.saveUserData(
            id: userId,
            name: userName,
            email: userEmail,
            age: userAge,
            profileCompleted: profileCompleted
        )
    }

    // MARK: - UI Testing Support

    /// Configure session for UI testing with mock authentication
    /// Call this when `--skip-auth` launch argument is present
    func configureForUITesting() {
        debugLog("[Session] 🧪 Configuring for UI testing mode")

        // Set mock authentication state
        accessToken = "ui-test-mock-token"
        isAuthenticated = true

        // Set mock user data
        userId = 99999
        userName = "Test User"
        userEmail = "test@example.com"
        userAge = 30
        profileCompleted = true

        // Mark initial data as loaded to skip loading screen
        isInitialDataLoaded = true

        // Create mock activities
        activities = [
            Activity(
                id: 1,
                name: "Hiking",
                icon: "🥾",
                default_grace_minutes: 30,
                colors: Activity.ActivityColors(primary: "#4CAF50", secondary: "#81C784", accent: "#2E7D32"),
                messages: Activity.ActivityMessages(start: "Have a great hike!", checkin: "Still hiking?", checkout: "Welcome back!", overdue: "Are you okay?", encouragement: ["Keep going!"]),
                safety_tips: ["Tell someone your route", "Bring plenty of water"],
                order: 1
            ),
            Activity(
                id: 2,
                name: "Running",
                icon: "🏃",
                default_grace_minutes: 15,
                colors: Activity.ActivityColors(primary: "#2196F3", secondary: "#64B5F6", accent: "#1565C0"),
                messages: Activity.ActivityMessages(start: "Enjoy your run!", checkin: "How's the run?", checkout: "Great job!", overdue: "Check in please", encouragement: ["You got this!"]),
                safety_tips: ["Stay visible", "Watch for traffic"],
                order: 2
            ),
            Activity(
                id: 3,
                name: "Other",
                icon: "📍",
                default_grace_minutes: 30,
                colors: Activity.ActivityColors(primary: "#9E9E9E", secondary: "#BDBDBD", accent: "#616161"),
                messages: Activity.ActivityMessages(start: "Stay safe!", checkin: "How's it going?", checkout: "Welcome back!", overdue: "Please check in", encouragement: ["Almost there!"]),
                safety_tips: ["Stay aware of your surroundings"],
                order: 99
            )
        ]

        // Create empty trips list (no active trip for testing new trip creation flow)
        allTrips = []
        activeTrip = nil

        // Create mock contacts
        contacts = [
            Contact(id: 1, user_id: 99999, name: "Emergency Contact", email: "emergency@example.com", group: nil)
        ]

        // Create mock friends
        friends = []
        pendingInvites = []
        tripInvitations = []

        debugLog("[Session] 🧪 UI testing mode configured successfully")
    }

    /// Check if running in UI testing mode
    static var isUITesting: Bool {
        CommandLine.arguments.contains("--uitesting") || CommandLine.arguments.contains("--skip-auth")
    }

    // MARK: - Trip Sync Helpers

    /// Updates a trip in allTrips array to keep it in sync with activeTrip changes.
    /// Must be called from MainActor.
    @MainActor
    private func syncTripInAllTrips(_ trip: Trip) {
        if let index = allTrips.firstIndex(where: { $0.id == trip.id }) {
            allTrips[index] = trip
            debugLog("[Session] Synced trip #\(trip.id) in allTrips")
        }
    }

    /// Safely update activeTrip from server response, rejecting stale ETA data.
    /// This prevents race conditions where Realtime-triggered fetches return stale data
    /// from database read replicas that haven't seen a recent trip extension.
    /// Returns true if the update was applied, false if rejected as stale.
    /// Must be called from MainActor.
    @MainActor
    private func safelyUpdateActiveTrip(with response: Trip?) -> Bool {
        // AGGRESSIVE: Block ALL updates during extension operation
        // This is the primary defense against stale data during trip extension
        if isExtensionInProgress {
            debugLog("[Session] ⛔ Rejecting activeTrip update - extension in progress")
            return false
        }

        // ETA-based staleness check:
        // Trip extensions always move the ETA forward in time.
        // If we have an active trip with a later ETA than the server response (same trip ID),
        // the server data is stale from a read replica that hasn't seen the extension yet.
        if let currentTrip = self.activeTrip,
           let serverTrip = response,
           currentTrip.id == serverTrip.id,
           currentTrip.eta_at > serverTrip.eta_at {
            debugLog("[Session] ⚠️ Rejecting stale activeTrip update: current ETA \(currentTrip.eta_at) > server ETA \(serverTrip.eta_at)")
            return false
        }

        // Log the update for debugging
        let oldETA = self.activeTrip?.eta_at
        self.activeTrip = response
        debugLog("[Session] ✅ activeTrip updated: ETA \(oldETA?.description ?? "nil") → \(response?.eta_at.description ?? "nil")")

        if let plan = response {
            LocalStorage.shared.cacheTrip(plan)
        }

        return true
    }

    /// Marks a trip as completed in allTrips array.
    /// Must be called from MainActor.
    @MainActor
    private func markTripCompletedInAllTrips(tripId: Int) {
        if let index = allTrips.firstIndex(where: { $0.id == tripId }) {
            let trip = allTrips[index]
            allTrips[index] = trip.with(
                status: "completed",
                completed_at: Date(),
                checkin_token: nil,
                checkout_token: nil
            )
            debugLog("[Session] Marked trip #\(tripId) as completed in allTrips")
        }
    }

    // MARK: URL helper

    func url(_ path: String) -> URL {
        if let u = URL(string: path), u.scheme != nil { return u }
        return baseURL.appending(path: path)
    }

    // MARK: Auth flows

    /// Validate APNs token format (should be 64 hex characters)
    private func isValidAPNsToken(_ token: String) -> Bool {
        // APNs tokens are typically 64 hex characters (32 bytes)
        // But can vary, so we check for reasonable length and hex format
        guard token.count >= 32 && token.count <= 128 else {
            return false
        }
        // Check if all characters are valid hex
        let hexCharacterSet = CharacterSet(charactersIn: "0123456789abcdefABCDEF")
        return token.unicodeScalars.allSatisfy { hexCharacterSet.contains($0) }
    }

    @MainActor
    func handleAPNsToken(_ token: String) {
        // Validate token format before storing
        guard isValidAPNsToken(token) else {
            debugLog("[APNs] ⚠️ Invalid token format: \(token.prefix(20))... (length: \(token.count))")
            return
        }

        self.apnsToken = token
        debugLog("[APNs] Received valid token: \(token.prefix(20))... (length: \(token.count))")

        // Register device token with backend once signed-in.
        guard let bearer = self.accessToken else {
            debugLog("[APNs] Not signed in, will register later")
            return
        }

        // Reset retry counter when we get a new token or fresh registration
        deviceRegistrationRetryCount = 0
        registerDeviceWithRetry(token: token, bearer: bearer)
    }

    /// Register device with backend, with exponential backoff retry
    /// The task is stored in `deviceRegistrationTask` so it can be cancelled on signOut.
    private func registerDeviceWithRetry(token: String, bearer: String) {
        debugLog("[APNs] Registering device with backend (attempt \(deviceRegistrationRetryCount + 1)/\(maxDeviceRegistrationRetries))...")

        struct DeviceRegister: Encodable {
            let platform: String
            let token: String
            let bundle_id: String
            let env: String
        }

        // Cancel any existing registration task before starting a new one
        deviceRegistrationTask?.cancel()

        deviceRegistrationTask = Task {
            do {
                // Check for cancellation before making API call
                guard !Task.isCancelled else {
                    debugLog("[APNs] Registration task cancelled")
                    return
                }

                let bundleId = Bundle.main.bundleIdentifier ?? "com.homeboundapp.Homebound"
                #if DEBUG
                let environment = "development"
                #else
                let environment = "production"
                #endif

                try await api.post(
                    url("/api/v1/devices/"),
                    body: DeviceRegister(
                        platform: "ios",
                        token: token,
                        bundle_id: bundleId,
                        env: environment
                    ),
                    bearer: bearer
                )
                debugLog("[APNs] ✅ Device registered successfully")
                await MainActor.run {
                    self.deviceRegistrationRetryCount = 0
                    self.deviceRegistrationTask = nil
                }
            } catch {
                // Check for cancellation before retrying
                guard !Task.isCancelled else {
                    debugLog("[APNs] Registration task cancelled during retry")
                    return
                }

                debugLog("[APNs] ❌ Registration failed: \(error.localizedDescription)")

                await MainActor.run {
                    self.deviceRegistrationRetryCount += 1

                    if self.deviceRegistrationRetryCount < self.maxDeviceRegistrationRetries {
                        // Exponential backoff: 1s, 2s, 4s
                        let delay = pow(2.0, Double(self.deviceRegistrationRetryCount - 1))
                        debugLog("[APNs] Retrying in \(delay) seconds...")

                        // Store the retry task for cancellation
                        self.deviceRegistrationTask = Task {
                            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                            guard !Task.isCancelled else {
                                debugLog("[APNs] Retry cancelled during sleep")
                                return
                            }
                            await MainActor.run {
                                if let currentBearer = self.accessToken {
                                    self.registerDeviceWithRetry(token: token, bearer: currentBearer)
                                }
                            }
                        }
                    } else {
                        // All retries exhausted
                        debugLog("[APNs] ❌ All registration attempts failed")
                        self.notice = "Could not register for push notifications. Please try again later."
                        self.deviceRegistrationTask = nil
                    }
                }
            }
        }
    }

    /// Handle APNs registration failure from the system
    @MainActor
    func handleAPNsRegistrationFailed(_ errorMessage: String) {
        debugLog("[APNs] ❌ System registration failed: \(errorMessage)")
        // Set notice to inform user - they may need to check notification settings
        self.notice = "Push notifications unavailable. Check your notification settings."
    }

    // MARK: - Live Activity Token Management

    /// Register a live activity push token with the backend
    /// This token is different from the regular APNs device token
    @discardableResult
    func registerLiveActivityToken(token: String, tripId: Int) async -> Bool {
        guard let bearer = accessToken else {
            debugLog("[LiveActivity] Cannot register token - not authenticated")
            return false
        }

        struct LiveActivityTokenRequest: Encodable {
            let token: String
            let trip_id: Int
            let bundle_id: String
            let env: String
        }

        let bundleId = Bundle.main.bundleIdentifier ?? "com.homeboundapp.Homebound"
        #if DEBUG
        let environment = "development"
        #else
        let environment = "production"
        #endif

        debugLog("[LiveActivity] Sending token registration: trip_id=\(tripId), env=\(environment), bundle_id=\(bundleId), token_prefix=\(token.prefix(20))...")

        do {
            let _: API.Empty = try await api.post(
                url("/api/v1/live-activity-tokens/"),
                body: LiveActivityTokenRequest(
                    token: token,
                    trip_id: tripId,
                    bundle_id: bundleId,
                    env: environment
                ),
                bearer: bearer
            )
            debugLog("[LiveActivity] ✅ Token registered for trip #\(tripId) (env=\(environment))")
            return true
        } catch {
            debugLog("[LiveActivity] ❌ Failed to register token for trip #\(tripId): \(error.localizedDescription)")
            return false
        }
    }

    /// Unregister a live activity push token when activity ends
    func unregisterLiveActivityToken(tripId: Int, caller: String = #function) async {
        debugLog("[LiveActivity] 🗑️ Unregistering token for trip #\(tripId) (called from: \(caller))")

        guard let bearer = accessToken else {
            debugLog("[LiveActivity] Cannot unregister token - not authenticated")
            return
        }

        do {
            let _: API.Empty = try await api.delete(
                url("/api/v1/live-activity-tokens/\(tripId)"),
                bearer: bearer
            )
            debugLog("[LiveActivity] ✅ Token unregistered for trip #\(tripId)")
        } catch {
            // Don't report error if token was already removed or trip doesn't exist
            debugLog("[LiveActivity] Token unregister result: \(error.localizedDescription)")
        }
    }

    /// Step 1: ask backend to send a code / magic link
    @MainActor
    func requestMagicLink(email: String) async {
        self.error = nil
        let e = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !e.isEmpty else { self.error = "Enter your email."; return }

        isRequesting = true
        defer { isRequesting = false }

        do {
            let _: SendCodeResponse = try await api.post(url(Routes.sendCode),
                                                        body: SendCodeRequest(email: e),
                                                        bearer: nil)
            showCodeSheet = true
        } catch let API.APIError.server(msg) {
            self.error = msg
        } catch {
            self.error = "Couldn’t send code. Check your connection and try again."
        }
    }

    @MainActor
    func verify() async {
        self.error = nil
        let e = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let c = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard c.count >= 6 else { self.error = "Enter the 6-digit code."; return }

        isVerifying = true
        defer { isVerifying = false }

        do {
            let resp: VerifyResponse = try await api.post(url(Routes.verify),
                                                        body: VerifyRequest(email: e, code: c),
                                                        bearer: nil)
            // Try all possible token field names for compatibility
            if let t = resp.access ?? resp.access_token ?? resp.token {
                accessToken = t
            }

            // Store refresh token if present
            if let refresh = resp.refresh {
                keychain.saveRefreshToken(refresh)
                // Also save to local storage as backup
                LocalStorage.shared.saveAuthTokens(access: accessToken, refresh: refresh)
                debugLog("[Session] ✅ Refresh token saved to keychain and local storage")
            }

            // Store user profile data
            if let user = resp.user {
                // Handle both separate first_name/last_name and combined name field
                if let firstName = user.first_name, let lastName = user.last_name {
                    userName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
                } else if let name = user.name {
                    userName = name
                } else {
                    userName = nil
                }

                userAge = user.age
                userEmail = user.email ?? email
                profileCompleted = user.profile_completed ?? false
            } else {
                userEmail = email
                profileCompleted = false
            }

            isAuthenticated = true
            showCodeSheet = false

            // Load activities after successful authentication
            await loadActivities()
        } catch let API.APIError.server(msg) {
            self.error = msg
        } catch {
            self.error = "Verification failed. Please try again."
        }
    }


    /// Compatibility helper for older call sites
    @MainActor
    func verifyMagic(code: String, email: String) async {
        self.email = email
        self.code = code
        self.error = nil
        self.isVerifying = true
        defer { self.isVerifying = false }
        await verify()
    }

    /// Sign in with Apple
    @MainActor
    func signInWithApple(
        userID: String,
        email: String?,
        firstName: String?,
        lastName: String?,
        identityToken: Data?
    ) async {
        self.error = nil
        self.isRequesting = true
        defer { self.isRequesting = false }

        // Convert identity token to string
        guard let tokenData = identityToken,
              let tokenString = String(data: tokenData, encoding: .utf8) else {
            self.error = "Invalid Apple Sign In token"
            return
        }

        struct AppleSignInRequest: Encodable {
            let identity_token: String
            let user_id: String
            let email: String?
            let first_name: String?
            let last_name: String?
        }

        struct AppleSignInResponse: Decodable {
            let account_exists: Bool
            let email: String
            let access: String?
            let refresh: String?
            let user: UserSummary?

            struct UserSummary: Decodable {
                let id: Int?
                let email: String?
                let first_name: String?
                let last_name: String?
                let age: Int?
                let profile_completed: Bool?
            }
        }

        do {
            let resp: AppleSignInResponse = try await api.post(
                url("/api/v1/auth/apple"),
                body: AppleSignInRequest(
                    identity_token: tokenString,
                    user_id: userID,
                    email: email,
                    first_name: firstName,
                    last_name: lastName
                ),
                bearer: nil
            )

            // Check if account exists and needs linking
            if resp.account_exists {
                debugLog("[Session] ⚠️  Account exists with email \(resp.email) - prompting for linking")
                // Store Apple credentials for linking later
                self.pendingAppleUserID = userID
                self.pendingAppleEmail = resp.email
                self.pendingAppleIdentityToken = tokenString
                self.showAppleLinkAlert = true
                return
            }

            // Normal sign in - store tokens and user data
            if let access = resp.access {
                accessToken = access
            }

            if let refresh = resp.refresh {
                keychain.saveRefreshToken(refresh)
                LocalStorage.shared.saveAuthTokens(access: accessToken, refresh: refresh)
            }

            // Store user profile data
            if let user = resp.user {
                if let firstName = user.first_name, let lastName = user.last_name {
                    userName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
                    // Store individual names for onboarding pre-fill
                    self.appleFirstName = firstName
                    self.appleLastName = lastName
                } else {
                    userName = nil
                    self.appleFirstName = nil
                    self.appleLastName = nil
                }

                userAge = user.age
                userEmail = user.email ?? email ?? ""
                profileCompleted = user.profile_completed ?? false
            }

            isAuthenticated = true
            debugLog("[Session] ✅ Apple Sign In successful")

            // Load activities after successful authentication
            await loadActivities()

        } catch let API.APIError.server(msg) {
            self.error = msg
        } catch {
            self.error = "Apple Sign In failed. Please try again."
        }
    }

    /// Link Apple ID to existing account
    @MainActor
    func linkAppleAccount() async {
        guard let userID = pendingAppleUserID,
              let email = pendingAppleEmail,
              let token = pendingAppleIdentityToken else {
            self.error = "No pending Apple account to link"
            return
        }

        self.error = nil
        self.isRequesting = true
        defer { self.isRequesting = false }

        struct AppleLinkRequest: Encodable {
            let identity_token: String
            let user_id: String
            let email: String
        }

        do {
            let resp: VerifyResponse = try await api.post(
                url("/api/v1/auth/apple/link"),
                body: AppleLinkRequest(
                    identity_token: token,
                    user_id: userID,
                    email: email
                ),
                bearer: nil
            )

            // Store tokens and user data (same as regular sign in)
            if let t = resp.access ?? resp.access_token ?? resp.token {
                accessToken = t
            }

            if let refresh = resp.refresh {
                keychain.saveRefreshToken(refresh)
                LocalStorage.shared.saveAuthTokens(access: accessToken, refresh: refresh)
            }

            if let user = resp.user {
                if let firstName = user.first_name, let lastName = user.last_name {
                    userName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
                } else if let name = user.name {
                    userName = name
                }

                userAge = user.age
                userEmail = user.email ?? email
                profileCompleted = user.profile_completed ?? false
            }

            isAuthenticated = true

            // Clear pending Apple credentials
            self.pendingAppleUserID = nil
            self.pendingAppleEmail = nil
            self.pendingAppleIdentityToken = nil
            self.showAppleLinkAlert = false

            debugLog("[Session] ✅ Apple account linked successfully")

        } catch let API.APIError.server(msg) {
            self.error = msg
        } catch {
            self.error = "Account linking failed. Please try again."
        }
    }

    /// Refresh the access token using the stored refresh token
    /// Uses a lock to prevent concurrent refresh operations - multiple callers will wait for the same refresh
    @MainActor
    func refreshAccessToken() async -> Bool {
        // If a refresh is already in progress, wait for it to complete with timeout
        if isRefreshingToken {
            debugLog("[Session] Token refresh already in progress - waiting...")
            let waiterCount = tokenRefreshContinuations.count + 1
            if waiterCount > 10 {
                debugLog("[Session] Warning: \(waiterCount) callers waiting for token refresh")
            }

            // Use withTaskGroup to implement timeout
            let result = await withTaskGroup(of: Bool?.self) { group in
                // Task 1: Wait for the continuation
                group.addTask { @MainActor in
                    return await withCheckedContinuation { continuation in
                        self.tokenRefreshContinuations.append(continuation)
                    }
                }

                // Task 2: Timeout after tokenRefreshTimeoutSeconds
                group.addTask {
                    try? await Task.sleep(nanoseconds: UInt64(self.tokenRefreshTimeoutSeconds * 1_000_000_000))
                    return nil as Bool?
                }

                // Return the first result (either continuation resumes or timeout)
                if let first = await group.next() {
                    group.cancelAll()
                    return first
                }
                return nil
            }

            if let result = result {
                return result
            } else {
                debugLog("[Session] Token refresh wait timed out")
                return false
            }
        }

        // Acquire lock
        isRefreshingToken = true
        defer {
            // Release lock and notify all waiting callers
            let result = accessToken != nil
            for continuation in tokenRefreshContinuations {
                continuation.resume(returning: result)
            }
            tokenRefreshContinuations.removeAll()
            isRefreshingToken = false
        }

        var refreshToken = keychain.getRefreshToken()

        // If keychain doesn't have it, try LocalStorage backup
        if refreshToken == nil {
            let tokens = LocalStorage.shared.getAuthTokens()
            refreshToken = tokens.refresh
            if refreshToken != nil {
                debugLog("[Session] ℹ️ Using refresh token from LocalStorage backup")
            }
        }

        guard let refreshToken = refreshToken else {
            debugLog("[Session] ❌ No refresh token available - user needs to re-authenticate")
            // No refresh token available, user needs to re-authenticate
            isAuthenticated = false
            accessToken = nil
            return false
        }

        debugLog("[Session] ℹ️ Attempting to refresh access token...")

        do {
            let resp: RefreshResponse = try await api.post(
                url(Routes.refresh),
                body: RefreshRequest(refresh_token: refreshToken),
                bearer: nil
            )

            // Update access token - fail if no token received
            guard let newToken = resp.access ?? resp.access_token else {
                debugLog("[Session] ❌ Token refresh response missing access token")
                isAuthenticated = false
                accessToken = nil
                return false
            }
            accessToken = newToken

            // Update refresh token if a new one was provided
            if let newRefresh = resp.refresh {
                keychain.saveRefreshToken(newRefresh)
                // Also save to local storage as backup
                LocalStorage.shared.saveAuthTokens(access: accessToken, refresh: newRefresh)
                debugLog("[Session] ✅ Token refreshed successfully - saved to keychain and local storage")
            }

            // Update user profile data if provided
            if let user = resp.user {
                // Handle both separate first_name/last_name and combined name field
                if let firstName = user.first_name, let lastName = user.last_name {
                    userName = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
                } else if let name = user.name {
                    userName = name
                }

                if let age = user.age {
                    userAge = age
                }

                if let email = user.email {
                    userEmail = email
                }

                if let completed = user.profile_completed {
                    profileCompleted = completed
                }
            }

            debugLog("[Session] ✅ Access token refresh successful")
            return true
        } catch {
            debugLog("[Session] ❌ Token refresh failed: \(error)")
            // Token refresh failed, user needs to re-authenticate
            isAuthenticated = false
            accessToken = nil
            keychain.clearAll()
            LocalStorage.shared.clearAuthTokens()
            return false
        }
    }

    /// Execute an authenticated API call with automatic token refresh on 401
    @MainActor
    private func withAuth<T>(_ operation: @escaping (String) async throws -> T) async throws -> T {
        guard let bearer = accessToken else {
            debugLog("[Session] ❌ No access token available - unauthorized")
            throw API.APIError.unauthorized
        }

        do {
            return try await operation(bearer)
        } catch API.APIError.unauthorized {
            debugLog("[Session] ⚠️ Got 401 Unauthorized - attempting token refresh...")

            // Try to refresh the token
            let refreshed = await refreshAccessToken()
            guard refreshed, let newBearer = accessToken else {
                debugLog("[Session] ❌ Token refresh failed - user needs to re-authenticate")
                throw API.APIError.unauthorized
            }

            debugLog("[Session] ✅ Token refreshed - retrying request with new token")
            // Retry the operation with the new token
            return try await operation(newBearer)
        }
    }

    // MARK: - Token Actions
    func performTokenAction(_ token: String, action: String) async {
        struct TokenResponse: Decodable { let ok: Bool }

        do {
            guard var urlComponents = URLComponents(url: url("/t/\(token)/\(action)"), resolvingAgainstBaseURL: false) else {
                await MainActor.run {
                    self.notice = "❌ Invalid URL for \(action)"
                }
                return
            }

            // For checkin, include current location coordinates
            if action == "checkin" {
                debugLog("[Session] Getting location for check-in...")
                if let location = await LocationManager.shared.getCurrentLocation() {
                    debugLog("[Session] ✅ Got location: \(location.latitude), \(location.longitude)")
                    urlComponents.queryItems = [
                        URLQueryItem(name: "lat", value: String(location.latitude)),
                        URLQueryItem(name: "lon", value: String(location.longitude))
                    ]
                } else {
                    debugLog("[Session] ❌ No location available for check-in")
                }
            }

            guard let requestURL = urlComponents.url else {
                await MainActor.run {
                    self.notice = "❌ Invalid URL for \(action)"
                }
                return
            }

            let _: TokenResponse = try await api.get(
                requestURL,
                bearer: nil
            )
            await MainActor.run {
                self.notice = "✅ \(action.capitalized) successful"
            }
        } catch {
            await MainActor.run {
                self.notice = "❌ \(action.capitalized) failed"
            }
        }
    }

    // MARK: - Plan Management
    func createPlan(_ plan: TripCreateRequest) async -> Trip? {
        do {
            let response: Trip = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/"),
                    body: plan,
                    bearer: bearer
                )
            }

            // Add to allTrips immediately for instant UI update
            await MainActor.run {
                self.allTrips.append(response)
                // Sort by start_at to maintain consistent order
                self.allTrips.sort { $0.start_at < $1.start_at }

                // Only set as active plan if the status is actually 'active'
                if response.status == "active" {
                    self.activeTrip = response
                    // Update widget data with new active trip
                    self.updateWidgetData()
                }
            }

            // Cache updated trips for offline access
            LocalStorage.shared.cacheTrips(self.allTrips)

            // Start Live Activity immediately for active trips
            if response.status == "active" {
                await LiveActivityManager.shared.startActivity(for: response)
            }

            return response
        } catch {
            await MainActor.run {
                self.lastError = "Failed to create plan: \(error.localizedDescription)"
            }
            return nil
        }
    }

    func updateTrip(_ tripId: Int, updates: TripUpdateRequest) async -> Trip? {
        do {
            let response: Trip = try await withAuth { bearer in
                try await self.api.put(
                    self.url("/api/v1/trips/\(tripId)"),
                    body: updates,
                    bearer: bearer
                )
            }

            debugLog("[Session] Trip \(tripId) updated successfully")

            // Update in allTrips immediately for instant UI update
            await MainActor.run {
                if let index = self.allTrips.firstIndex(where: { $0.id == tripId }) {
                    self.allTrips[index] = response
                    // Re-sort in case start_at changed
                    self.allTrips.sort { $0.start_at < $1.start_at }
                }
            }

            // Cache updated trips for offline access
            LocalStorage.shared.cacheTrips(self.allTrips)

            return response
        } catch {
            // Queue for later sync when offline
            var payload: [String: Any] = [:]

            // Convert TripUpdateRequest to payload dictionary
            if let title = updates.title { payload["title"] = title }
            if let activity = updates.activity { payload["activity"] = activity }
            if let start = updates.start { payload["start"] = ISO8601DateFormatter().string(from: start) }
            if let eta = updates.eta { payload["eta"] = ISO8601DateFormatter().string(from: eta) }
            if let graceMin = updates.grace_min { payload["grace_min"] = graceMin }
            if let locationText = updates.location_text { payload["location_text"] = locationText }
            if let lat = updates.gen_lat { payload["gen_lat"] = lat }
            if let lon = updates.gen_lon { payload["gen_lon"] = lon }
            if let notes = updates.notes { payload["notes"] = notes }
            if let contact1 = updates.contact1 { payload["contact1"] = contact1 }
            if let contact2 = updates.contact2 { payload["contact2"] = contact2 }
            if let contact3 = updates.contact3 { payload["contact3"] = contact3 }
            if let timezone = updates.timezone { payload["timezone"] = timezone }

            LocalStorage.shared.queuePendingAction(
                type: "update_trip",
                tripId: tripId,
                payload: payload
            )

            // Update local cache with ALL changes (not just eta)
            var cacheUpdates: [String: Any] = [:]
            if let title = updates.title { cacheUpdates["title"] = title }
            if let activity = updates.activity { cacheUpdates["activity"] = activity }
            if let eta = updates.eta { cacheUpdates["eta"] = eta }
            if let graceMin = updates.grace_min { cacheUpdates["grace_min"] = graceMin }
            if let locationText = updates.location_text { cacheUpdates["location_text"] = locationText }
            if let lat = updates.gen_lat { cacheUpdates["gen_lat"] = lat }
            if let lon = updates.gen_lon { cacheUpdates["gen_lon"] = lon }
            if let notes = updates.notes { cacheUpdates["notes"] = notes }
            if let contact1 = updates.contact1 { cacheUpdates["contact1"] = contact1 }
            if let contact2 = updates.contact2 { cacheUpdates["contact2"] = contact2 }
            if let contact3 = updates.contact3 { cacheUpdates["contact3"] = contact3 }
            if !cacheUpdates.isEmpty {
                LocalStorage.shared.updateCachedTripFields(tripId: tripId, updates: cacheUpdates)
            }

            await MainActor.run {
                self.notice = "Trip updated (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Update trip queued for offline sync")

            // Return the cached trip with updates applied for optimistic UI
            // This allows callers to distinguish success (cached trip) from true failure (nil)
            if let cachedTrip = LocalStorage.shared.getCachedTrip(id: tripId) {
                var updatedTrip = cachedTrip
                if let title = updates.title { updatedTrip.title = title }
                if let eta = updates.eta { updatedTrip.eta_at = eta }
                if let graceMin = updates.grace_min { updatedTrip.grace_minutes = graceMin }
                if let locationText = updates.location_text { updatedTrip.location_text = locationText }
                if let lat = updates.gen_lat { updatedTrip.location_lat = lat }
                if let lon = updates.gen_lon { updatedTrip.location_lng = lon }
                if let notes = updates.notes { updatedTrip.notes = notes }
                if let contact1 = updates.contact1 { updatedTrip.contact1 = contact1 }
                if let contact2 = updates.contact2 { updatedTrip.contact2 = contact2 }
                if let contact3 = updates.contact3 { updatedTrip.contact3 = contact3 }
                return updatedTrip
            }
            return nil
        }
    }

    /// Load all initial data needed before showing the main app
    func loadInitialData() async {
        // Clean up old cached data (older than 30 days) to prevent storage buildup
        LocalStorage.shared.cleanupOldCache()

        // ALWAYS load from cache first - don't check, just load whatever exists
        let cachedActivities = LocalStorage.shared.getCachedActivities()
        let cachedTrips = LocalStorage.shared.getCachedTrips()
        let cachedContacts = LocalStorage.shared.getCachedContacts()

        debugLog("[Session] 📦 Loading from cache: \(cachedActivities.count) activities, \(cachedTrips.count) trips, \(cachedContacts.count) contacts")

        await MainActor.run {
            // Populate from cache immediately - always set these to ensure UI gets updated
            self.allTrips = cachedTrips
            self.activities = cachedActivities.sorted { $0.order < $1.order }
            self.contacts = cachedContacts
            // Include active, overdue, and overdue_notified statuses (all "in progress" trips)
            if let activeTrip = cachedTrips.first(where: { Constants.TripStatus.isActive($0.status) }) {
                self.activeTrip = activeTrip
            }
            // Mark as loaded IMMEDIATELY so UI can render
            isInitialDataLoaded = true

            debugLog("[Session] ✅ Cache loaded - allTrips: \(self.allTrips.count), activities: \(self.activities.count), contacts: \(self.contacts.count), activeTrip: \(self.activeTrip?.title ?? "none")")
        }

        // If offline, we're done - cache is loaded
        if !NetworkMonitor.shared.isConnected {
            debugLog("[Session] 📦 Offline - using cached data only")
            return
        }

        // If online, refresh in background (don't block UI)
        debugLog("[Session] 🌐 Online - refreshing from network in background")
        Task {
            async let activitiesTask: Void = loadActivities()
            async let activePlanTask: Void = loadActivePlan()
            async let profileTask: Void = loadUserProfile()
            async let contactsTask: [Contact] = loadContacts()
            async let tripsTask: [Trip] = loadAllTrips()  // Cache all trips for offline access
            async let friendsTask: [Friend] = loadFriends()  // Load friends for offline access
            async let featureLimitsTask: Void = loadFeatureLimits()  // Load subscription feature limits
            _ = await (activitiesTask, activePlanTask, profileTask, contactsTask, tripsTask, friendsTask, featureLimitsTask)

            // Sync pending actions after data loads
            await syncPendingActions()

            // Start Supabase Realtime subscriptions for instant updates
            if let userId = self.userId {
                await RealtimeManager.shared.start(userId: userId)
            }
        }
    }

    /// Bug 3 fix: Public method to check if it's safe to call loadActivePlan()
    /// without overwriting a recent local update (e.g., from trip extension).
    /// RealtimeManager should call this before triggering loadActivePlan().
    /// Protection window is 30 seconds to account for network latency and database replication lag.
    func shouldLoadActivePlan() -> Bool {
        if let lastUpdate = lastLocalTripUpdate,
           Date().timeIntervalSince(lastUpdate) < 30.0 {
            debugLog("[Session] Realtime skipping loadActivePlan - recent local update within 30s")
            return false
        }
        return true
    }

    func loadActivePlan() async {
        // Prevent Realtime from overwriting recent local updates (race condition fix)
        // This happens when extending a trip: we update locally, then Realtime triggers
        // loadActivePlan() which might fetch stale data from the server
        // Protection window is 30 seconds to account for network latency and database replication lag
        if let lastUpdate = lastLocalTripUpdate,
           Date().timeIntervalSince(lastUpdate) < 30.0 {
            debugLog("[Session] Skipping loadActivePlan - recent local update within 30s")
            return
        }

        await MainActor.run {
            self.isLoadingTrip = true
        }

        // Show cached data immediately if we don't have an active trip yet
        // Include active, overdue, and overdue_notified statuses (all "in progress" trips)
        let cachedTrips = LocalStorage.shared.getCachedTrips()
        let cachedActive = cachedTrips.first { Constants.TripStatus.isActive($0.status) }

        // Only set activeTrip from cache if we don't have one AND the cached trip is actually active
        // (not just recently completed but still in cache)
        if self.activeTrip == nil, let cached = cachedActive {
            await MainActor.run {
                self.activeTrip = cached
            }
            // Start Live Activity from cache only when restoring from nil state
            let checkinCount = getCheckinCount(tripId: cached.id)
            await LiveActivityManager.shared.startActivity(for: cached, checkinCount: checkinCount)

            // Auto-start live location sharing if enabled for this trip
            if cached.share_live_location {
                await MainActor.run {
                    LiveLocationManager.shared.startSharing(forTripId: cached.id)
                }
            }
        }
        // If we already have an activeTrip, don't start a new Live Activity from cache
        // - the API response will handle updating it

        // If offline, use cache and return immediately - don't wait for network timeout
        if !NetworkMonitor.shared.isConnected {
            await MainActor.run {
                // Check for stale cache - don't regress ETA if we have a newer local value
                if let current = self.activeTrip,
                   let cached = cachedActive,
                   current.id == cached.id,
                   current.eta_at > cached.eta_at {
                    debugLog("[Session] ⚠️ Skipping stale cache in offline path - keeping current ETA \(current.eta_at)")
                    self.isLoadingTrip = false
                    return
                }
                self.activeTrip = cachedActive
                self.isLoadingTrip = false
                debugLog("[Session] 📦 Loaded active trip from cache (offline)")
            }
            return
        }

        // Then try network for fresh data
        do {
            let response: Trip? = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/active"),
                    bearer: bearer
                )
            }

            var didUpdate = false
            await MainActor.run {
                didUpdate = self.safelyUpdateActiveTrip(with: response)
                self.isLoadingTrip = false

                // Update widget data only if we actually updated
                if didUpdate {
                    self.updateWidgetData()
                }
            }

            // Skip Live Activity and location updates if stale data was rejected
            guard didUpdate else {
                debugLog("[Session] Skipping Live Activity/location updates - stale data rejected")
                return
            }

            // Update Live Activity
            let checkinCount = response != nil ? getCheckinCount(tripId: response!.id) : 0
            await LiveActivityManager.shared.restoreActivityIfNeeded(for: response, checkinCount: checkinCount)

            // Auto-start live location sharing if enabled for this trip
            if let trip = response, trip.share_live_location {
                await MainActor.run {
                    LiveLocationManager.shared.startSharing(forTripId: trip.id)
                }
            }
        } catch {
            // Network failed - already showing cached data, just stop loading
            var didUpdate = false
            await MainActor.run {
                // If we don't have anything yet, use cache
                // Otherwise, use safe update to avoid overwriting newer local data with stale cache
                if self.activeTrip == nil {
                    self.activeTrip = cachedActive
                    didUpdate = cachedActive != nil
                } else if cachedActive != nil {
                    didUpdate = self.safelyUpdateActiveTrip(with: cachedActive)
                }
                self.isLoadingTrip = false
            }

            // Only update Live Activity if we actually applied the cache update
            guard didUpdate, let cached = cachedActive else { return }

            let checkinCount = getCheckinCount(tripId: cached.id)
            await LiveActivityManager.shared.restoreActivityIfNeeded(for: cached, checkinCount: checkinCount)

            // Auto-start live location sharing if enabled for this trip
            if cached.share_live_location {
                await MainActor.run {
                    LiveLocationManager.shared.startSharing(forTripId: cached.id)
                }
            }
        }
    }

    /// Load all trips with caching for offline access
    func loadAllTrips() async -> [Trip] {
        // Get cached trips first for immediate display
        let cachedTrips = LocalStorage.shared.getCachedTrips()

        // If offline, return cached data immediately
        if !NetworkMonitor.shared.isConnected {
            debugLog("[Session] 📦 Offline - returning \(cachedTrips.count) cached trips")
            await MainActor.run {
                self.allTrips = cachedTrips
                // Note: activeTrip is managed by loadActivePlan() to prevent race conditions
            }
            return cachedTrips
        }

        do {
            let trips: [Trip] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/"),
                    bearer: bearer
                )
            }

            // Cache trips for offline access
            LocalStorage.shared.cacheTrips(trips)

            // Update published properties
            await MainActor.run {
                self.allTrips = trips
                // Note: activeTrip is managed by loadActivePlan() to prevent race conditions
            }

            return trips
        } catch {
            // Return cached trips when offline
            let cachedTrips = LocalStorage.shared.getCachedTrips()
            await MainActor.run {
                self.allTrips = cachedTrips
                // Note: activeTrip is managed by loadActivePlan() to prevent race conditions
                if !cachedTrips.isEmpty {
                    self.notice = "Showing cached trips (offline mode)"
                }
            }
            return cachedTrips
        }
    }

    /// Sync pending offline actions to server
    func syncPendingActions() async {
        let pendingActions = LocalStorage.shared.getPendingActions()

        guard !pendingActions.isEmpty else {
            debugLog("[Session] ℹ️ No pending actions to sync")
            return
        }

        debugLog("[Session] 🔄 Syncing \(pendingActions.count) pending action(s)...")

        var needsDataRefresh = false  // Track if we need to refresh data after sync

        for action in pendingActions {
            debugLog("[Session] Processing action #\(action.id): \(action.type)")
            do {
                switch action.type {
                case "checkin":
                    // Use token-based checkin endpoint (no auth required)
                    if let token = action.payload["token"] as? String {
                        guard var urlComponents = URLComponents(url: url("/t/\(token)/checkin"), resolvingAgainstBaseURL: false) else {
                            debugLog("[Session] ⚠️ checkin action has invalid URL - skipping")
                            continue
                        }

                        // Include coordinates if they were captured when queued
                        if let lat = action.payload["lat"] as? Double,
                           let lon = action.payload["lon"] as? Double {
                            urlComponents.queryItems = [
                                URLQueryItem(name: "lat", value: String(lat)),
                                URLQueryItem(name: "lon", value: String(lon))
                            ]
                        }

                        guard let requestURL = urlComponents.url else {
                            debugLog("[Session] ⚠️ checkin action URL construction failed - skipping")
                            continue
                        }

                        let _: GenericResponse = try await api.get(
                            requestURL,
                            bearer: nil
                        )
                        debugLog("[Session] ✅ Synced checkin action")
                    } else {
                        debugLog("[Session] ⚠️ checkin action missing token - removing invalid action")
                    }
                case "extend":
                    if let tripId = action.tripId,
                       let minutes = action.payload["minutes"] as? Int {
                        // Construct URL with query parameters properly
                        guard var urlComponents = URLComponents(url: url("/api/v1/trips/\(tripId)/extend"), resolvingAgainstBaseURL: false) else {
                            debugLog("[Session] ⚠️ extend action has invalid URL - skipping")
                            continue
                        }
                        var queryItems = [URLQueryItem(name: "minutes", value: String(minutes))]
                        // Include coordinates if they were captured when queued
                        if let lat = action.payload["lat"] as? Double,
                           let lon = action.payload["lon"] as? Double {
                            queryItems.append(URLQueryItem(name: "lat", value: String(lat)))
                            queryItems.append(URLQueryItem(name: "lon", value: String(lon)))
                        }
                        urlComponents.queryItems = queryItems

                        guard let requestURL = urlComponents.url else {
                            debugLog("[Session] ⚠️ extend action URL construction failed - skipping")
                            continue
                        }

                        let _: GenericResponse = try await withAuth { bearer in
                            try await self.api.post(
                                requestURL,
                                body: API.Empty(),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced extend action for trip #\(tripId)")
                    } else {
                        debugLog("[Session] ⚠️ extend action missing tripId or minutes - removing invalid action")
                    }
                case "complete":
                    if let tripId = action.tripId {
                        let _: GenericResponse = try await withAuth { bearer in
                            try await self.api.post(
                                self.url("/api/v1/trips/\(tripId)/complete"),
                                body: API.Empty(),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced complete action for trip #\(tripId)")
                    } else {
                        debugLog("[Session] ⚠️ complete action missing tripId - removing invalid action")
                    }

                case "update_trip":
                    if let tripId = action.tripId {
                        // Reconstruct TripUpdateRequest from payload
                        var updates = TripUpdateRequest()
                        if let title = action.payload["title"] as? String { updates.title = title }
                        if let activity = action.payload["activity"] as? String { updates.activity = activity }
                        // Use DateUtils for robust parsing (handles multiple date formats)
                        if let startStr = action.payload["start"] as? String,
                           let start = DateUtils.parseISO8601(startStr) { updates.start = start }
                        if let etaStr = action.payload["eta"] as? String,
                           let eta = DateUtils.parseISO8601(etaStr) { updates.eta = eta }
                        if let graceMin = action.payload["grace_min"] as? Int { updates.grace_min = graceMin }
                        if let locationText = action.payload["location_text"] as? String { updates.location_text = locationText }
                        if let lat = action.payload["gen_lat"] as? Double { updates.gen_lat = lat }
                        if let lon = action.payload["gen_lon"] as? Double { updates.gen_lon = lon }
                        if let notes = action.payload["notes"] as? String { updates.notes = notes }
                        if let contact1 = action.payload["contact1"] as? Int { updates.contact1 = contact1 }
                        if let contact2 = action.payload["contact2"] as? Int { updates.contact2 = contact2 }
                        if let contact3 = action.payload["contact3"] as? Int { updates.contact3 = contact3 }
                        if let timezone = action.payload["timezone"] as? String { updates.timezone = timezone }

                        let _: Trip = try await withAuth { bearer in
                            try await self.api.put(
                                self.url("/api/v1/trips/\(tripId)"),
                                body: updates,
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced update_trip action for trip #\(tripId)")
                    } else {
                        debugLog("[Session] ⚠️ update_trip action missing tripId - removing invalid action")
                    }

                case "start_trip":
                    if let tripId = action.tripId {
                        let _: GenericResponse = try await withAuth { bearer in
                            try await self.api.post(
                                self.url("/api/v1/trips/\(tripId)/start"),
                                body: API.Empty(),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced start_trip action for trip #\(tripId)")
                    } else {
                        debugLog("[Session] ⚠️ start_trip action missing tripId - removing invalid action")
                    }

                case "delete_trip":
                    if let tripId = action.tripId {
                        let _: GenericResponse = try await withAuth { bearer in
                            try await self.api.delete(
                                self.url("/api/v1/trips/\(tripId)"),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced delete_trip action for trip #\(tripId)")
                    } else {
                        debugLog("[Session] ⚠️ delete_trip action missing tripId - removing invalid action")
                    }

                case "add_contact":
                    if let name = action.payload["name"] as? String,
                       let email = action.payload["email"] as? String {
                        struct ContactCreate: Codable { let name: String; let email: String }
                        let newContact: Contact = try await withAuth { bearer in
                            try await self.api.post(
                                self.url("/api/v1/contacts/"),
                                body: ContactCreate(name: name, email: email),
                                bearer: bearer
                            )
                        }

                        // Replace temporary contact with real one from server
                        if let tempId = action.payload["temp_id"] as? Int {
                            LocalStorage.shared.removeCachedContact(contactId: tempId)
                            LocalStorage.shared.cacheContact(newContact)
                            debugLog("[Session] ✅ Replaced temp contact #\(tempId) with real contact #\(newContact.id)")
                        } else {
                            // No temp_id (legacy action), just cache the new contact
                            LocalStorage.shared.cacheContact(newContact)
                        }
                        debugLog("[Session] ✅ Synced add_contact action")
                    } else {
                        debugLog("[Session] ⚠️ add_contact action missing name or email - removing invalid action")
                    }

                case "update_contact":
                    if let contactId = action.payload["contact_id"] as? Int,
                       let name = action.payload["name"] as? String,
                       let email = action.payload["email"] as? String {
                        struct ContactUpdate: Codable { let name: String; let email: String }
                        let _: Contact = try await withAuth { bearer in
                            try await self.api.put(
                                self.url("/api/v1/contacts/\(contactId)"),
                                body: ContactUpdate(name: name, email: email),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced update_contact action for contact #\(contactId)")
                    } else {
                        debugLog("[Session] ⚠️ update_contact action missing contactId, name, or email - removing invalid action")
                    }

                case "delete_contact":
                    if let contactId = action.payload["contact_id"] as? Int {
                        let _: GenericResponse = try await withAuth { bearer in
                            try await self.api.delete(
                                self.url("/api/v1/contacts/\(contactId)"),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced delete_contact action for contact #\(contactId)")
                    } else {
                        debugLog("[Session] ⚠️ delete_contact action missing contactId - removing invalid action")
                    }

                case "update_profile":
                    struct UpdateProfileRequest: Encodable {
                        let first_name: String?
                        let last_name: String?
                        let age: Int?
                    }

                    let firstName = action.payload["first_name"] as? String
                    let lastName = action.payload["last_name"] as? String
                    let age = action.payload["age"] as? Int

                    let _: GenericResponse = try await withAuth { bearer in
                        try await self.api.patch(
                            self.url("/api/v1/profile"),
                            body: UpdateProfileRequest(first_name: firstName, last_name: lastName, age: age),
                            bearer: bearer
                        )
                    }
                    debugLog("[Session] ✅ Synced update_profile action")

                default:
                    debugLog("[Session] ⚠️ Unknown action type: \(action.type)")
                }

                // Remove successfully synced action
                LocalStorage.shared.removePendingAction(id: action.id)
                debugLog("[Session] ✅ Removed synced action id=\(action.id)")
            } catch let error as API.APIError {
                // Handle API errors - remove action on permanent failures
                switch error {
                case .unauthorized:
                    // Token refresh failed - permanent failure, user needs to re-authenticate
                    debugLog("[Session] ⚠️ Removing action \(action.type) due to auth failure")
                    LocalStorage.shared.removePendingAction(id: action.id)
                    LocalStorage.shared.logFailedAction(
                        type: action.type,
                        tripId: action.tripId,
                        error: "Authentication expired. Please log in again."
                    )
                case .httpError(let statusCode, let message) where statusCode >= 400 && statusCode < 500:
                    // Client errors (400-499) are permanent - don't retry
                    debugLog("[Session] ⚠️ Removing action \(action.type) due to permanent error: \(statusCode)")
                    LocalStorage.shared.removePendingAction(id: action.id)

                    // Log failed action for user awareness
                    LocalStorage.shared.logFailedAction(
                        type: action.type,
                        tripId: action.tripId,
                        error: "Server rejected: \(message)"
                    )
                default:
                    // Server errors (5xx) - keep for retry
                    debugLog("[Session] ❌ Failed to sync action \(action.type): \(error)")
                }
            } catch is DecodingError {
                // Decode errors mean we got a response but couldn't parse it - action was likely processed
                // Remove action but flag for data refresh to get correct state from server
                debugLog("[Session] ⚠️ Decode error for \(action.type) - removing action and flagging for refresh")
                LocalStorage.shared.removePendingAction(id: action.id)
                needsDataRefresh = true
            } catch let error as URLError {
                // Network errors - keep for retry only if it's a connectivity issue
                if error.code == .notConnectedToInternet || error.code == .networkConnectionLost {
                    debugLog("[Session] ❌ Network error, will retry: \(error.localizedDescription)")
                } else {
                    // Other URL errors (timeout, etc.) - remove to prevent stuck actions
                    debugLog("[Session] ⚠️ URL error for \(action.type) - removing: \(error.localizedDescription)")
                    LocalStorage.shared.removePendingAction(id: action.id)
                }
            } catch {
                // Unknown errors - remove to prevent stuck actions
                debugLog("[Session] ⚠️ Unknown error for \(action.type) - removing: \(error)")
                LocalStorage.shared.removePendingAction(id: action.id)
            }
        }

        // Update pending count and failed count after sync
        await MainActor.run {
            self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            self.failedActionsCount = LocalStorage.shared.getFailedActionsCount()
            debugLog("[Session] 📊 After sync: \(self.pendingActionsCount) pending, \(self.failedActionsCount) failed")
        }

        // Refresh data after sync
        if needsDataRefresh {
            // Decode error occurred - do full refresh to get correct state from server
            debugLog("[Session] 🔄 Doing full data refresh after decode error")
            _ = await loadAllTrips()
            _ = await loadContacts()
        }
        // Bug 3 fix: Check protection window to prevent overwriting local trip updates
        if shouldLoadActivePlan() {
            await loadActivePlan()
        }
    }

    /// Clear all pending actions (for stuck/stale actions)
    @MainActor
    func clearPendingActions() {
        LocalStorage.shared.clearPendingActions()
        pendingActionsCount = 0
        debugLog("[Session] ✅ Cleared all pending actions")
    }

    /// Clear all failed actions (after user acknowledges)
    @MainActor
    func clearFailedActions() {
        LocalStorage.shared.clearFailedActions()
        failedActionsCount = 0
        debugLog("[Session] ✅ Cleared all failed actions")
    }

    func checkIn() async -> Bool {
        guard let plan = activeTrip else { return false }

        debugLog("[Session] 📍 Check-in started, fetching location...")

        // Get current location for check-in (non-blocking, 5s timeout)
        let location = await LocationManager.shared.getCurrentLocation()

        if let loc = location {
            debugLog("[Session] 📍 Got location for check-in: \(loc.latitude), \(loc.longitude)")
        } else {
            debugLog("[Session] ⚠️ No location available for check-in")
        }

        // For group trips, use authenticated endpoint so the correct user is recorded
        if plan.is_group_trip {
            debugLog("[Session] 👥 Group trip - using authenticated check-in endpoint")
            return await authenticatedCheckIn(plan: plan, location: location)
        }

        // For solo trips, use token-based endpoint
        guard let token = plan.checkin_token else {
            debugLog("[Session] ❌ No check-in token available")
            return false
        }

        // Check if offline FIRST - queue immediately without waiting for network timeout
        if !NetworkMonitor.shared.isConnected {
            return await queueOfflineCheckIn(plan: plan, token: token, location: location)
        }

        // Block Realtime from overwriting activeTrip during the API call
        // This prevents race conditions where Realtime updates arrive before the API response
        await MainActor.run {
            self.lastLocalTripUpdate = Date()
        }

        do {
            // Build URL with coordinates if available
            guard var urlComponents = URLComponents(url: url("/t/\(token)/checkin"), resolvingAgainstBaseURL: false) else {
                debugLog("[Session] ❌ Failed to construct check-in URL")
                return false
            }
            if let loc = location {
                urlComponents.queryItems = [
                    URLQueryItem(name: "lat", value: String(loc.latitude)),
                    URLQueryItem(name: "lon", value: String(loc.longitude))
                ]
                debugLog("[Session] 📍 Check-in URL with coords: \(urlComponents.url?.absoluteString ?? "nil")")
            } else {
                debugLog("[Session] ⚠️ Check-in URL without coords: \(urlComponents.url?.absoluteString ?? "nil")")
            }

            guard let requestURL = urlComponents.url else {
                debugLog("[Session] ❌ Failed to build check-in request URL")
                return false
            }

            // Use token-based checkin endpoint (no auth required)
            let _: GenericResponse = try await api.get(
                requestURL,
                bearer: nil
            )

            // Update local activeTrip with new last_checkin timestamp immediately
            let checkinTimestamp = ISO8601DateFormatter().string(from: Date())
            let hasLocation = location != nil

            await MainActor.run {
                // Update local activeTrip state so UI reflects the check-in
                if var updatedTrip = self.activeTrip {
                    updatedTrip.last_checkin = checkinTimestamp
                    self.activeTrip = updatedTrip
                    self.lastLocalTripUpdate = Date()  // Prevent Realtime from overwriting this update
                    // Sync to allTrips as well
                    self.syncTripInAllTrips(updatedTrip)
                }
                // Show appropriate notice based on location availability
                self.notice = hasLocation ? "Checked in successfully!" : "Checked in (location unavailable)"
                // Update widget data with new check-in
                self.updateWidgetData()
            }

            // Also update local cache for consistency
            LocalStorage.shared.updateCachedTripFields(
                tripId: plan.id,
                updates: ["last_checkin": checkinTimestamp]
            )

            debugLog("[Session] ✅ Check-in successful, local state updated")
            return true
        } catch let error as URLError where error.code == .notConnectedToInternet ||
                                            error.code == .networkConnectionLost {
            // Only queue for actual network connectivity issues
            debugLog("[Session] ⚠️ Check-in network error - queueing offline: \(error.code)")
            return await queueOfflineCheckIn(plan: plan, token: token, location: location)
        } catch let error as URLError where error.code == .timedOut {
            // Timeout is tricky - server may have processed. Queue but log warning.
            debugLog("[Session] ⚠️ Check-in timed out - server may have processed, queueing anyway")
            return await queueOfflineCheckIn(plan: plan, token: token, location: location)
        } catch {
            // Other errors (server errors, decode errors) - don't queue, show error
            // The server may have processed the request, so queueing could cause duplicates
            debugLog("[Session] ❌ Check-in failed with non-network error: \(error)")
            await MainActor.run {
                self.lastError = "Check-in failed. Please try again."
            }
            return false
        }
    }

    private func queueOfflineCheckIn(plan: Trip, token: String, location: CLLocationCoordinate2D?) async -> Bool {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var payload: [String: Any] = ["token": token, "timestamp": timestamp]
        if let loc = location {
            payload["lat"] = loc.latitude
            payload["lon"] = loc.longitude
        }
        LocalStorage.shared.queuePendingAction(
            type: "checkin",
            tripId: plan.id,
            payload: payload
        )

        // Update local cache with check-in timestamp
        LocalStorage.shared.updateCachedTripFields(
            tripId: plan.id,
            updates: ["last_checkin": timestamp]
        )

        await MainActor.run {
            // Update local activeTrip state so UI reflects the check-in
            if var updatedTrip = self.activeTrip {
                updatedTrip.last_checkin = timestamp
                self.activeTrip = updatedTrip
                // Sync to allTrips as well
                self.syncTripInAllTrips(updatedTrip)
            }
            self.notice = "Check-in saved (will sync when online)"
            self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
        }

        debugLog("[Session] ℹ️ Check-in queued for offline sync")
        return true
    }

    /// Authenticated check-in for group trips - uses the participant check-in endpoint
    /// which records the correct user_id for the check-in event.
    private func authenticatedCheckIn(plan: Trip, location: CLLocationCoordinate2D?) async -> Bool {
        // Check if offline FIRST - queue immediately without waiting for network timeout
        if !NetworkMonitor.shared.isConnected {
            // For group trips offline, queue with authenticated flag
            return await queueOfflineAuthenticatedCheckIn(plan: plan, location: location)
        }

        // Block Realtime from overwriting activeTrip during the API call
        // This prevents race conditions where Realtime updates arrive before the API response
        await MainActor.run {
            self.lastLocalTripUpdate = Date()
        }

        do {
            // Build URL with coordinates if available
            guard var urlComponents = URLComponents(url: url("/api/v1/trips/\(plan.id)/checkin"), resolvingAgainstBaseURL: false) else {
                debugLog("[Session] ❌ Failed to construct authenticated check-in URL")
                return false
            }

            if let loc = location {
                urlComponents.queryItems = [
                    URLQueryItem(name: "lat", value: String(loc.latitude)),
                    URLQueryItem(name: "lon", value: String(loc.longitude))
                ]
                debugLog("[Session] 📍 Authenticated check-in URL with coords: \(urlComponents.url?.absoluteString ?? "nil")")
            } else {
                debugLog("[Session] ⚠️ Authenticated check-in URL without coords: \(urlComponents.url?.absoluteString ?? "nil")")
            }

            guard let requestURL = urlComponents.url else {
                debugLog("[Session] ❌ Failed to build authenticated check-in request URL")
                return false
            }

            // Use authenticated participant checkin endpoint
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    requestURL,
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Update local activeTrip with new last_checkin timestamp immediately
            let checkinTimestamp = ISO8601DateFormatter().string(from: Date())
            let hasLocation = location != nil

            await MainActor.run {
                // Update local activeTrip state so UI reflects the check-in
                if var updatedTrip = self.activeTrip {
                    updatedTrip.last_checkin = checkinTimestamp
                    self.activeTrip = updatedTrip
                    self.lastLocalTripUpdate = Date()  // Prevent Realtime from overwriting this update
                    // Sync to allTrips as well
                    self.syncTripInAllTrips(updatedTrip)
                }
                // Show appropriate notice based on location availability
                self.notice = hasLocation ? "Checked in successfully!" : "Checked in (location unavailable)"
                // Update widget data with new check-in
                self.updateWidgetData()
            }

            // Also update local cache for consistency
            LocalStorage.shared.updateCachedTripFields(
                tripId: plan.id,
                updates: ["last_checkin": checkinTimestamp]
            )

            debugLog("[Session] ✅ Authenticated check-in successful, local state updated")
            return true
        } catch let error as URLError where error.code == .notConnectedToInternet ||
                                            error.code == .networkConnectionLost {
            // Only queue for actual network connectivity issues
            debugLog("[Session] ⚠️ Authenticated check-in network error - queueing offline: \(error.code)")
            return await queueOfflineAuthenticatedCheckIn(plan: plan, location: location)
        } catch let error as URLError where error.code == .timedOut {
            // Timeout is tricky - server may have processed. Queue but log warning.
            debugLog("[Session] ⚠️ Authenticated check-in timed out - server may have processed, queueing anyway")
            return await queueOfflineAuthenticatedCheckIn(plan: plan, location: location)
        } catch {
            // Other errors (server errors, decode errors) - don't queue, show error
            debugLog("[Session] ❌ Authenticated check-in failed with non-network error: \(error)")
            await MainActor.run {
                self.lastError = "Check-in failed. Please try again."
            }
            return false
        }
    }

    private func queueOfflineAuthenticatedCheckIn(plan: Trip, location: CLLocationCoordinate2D?) async -> Bool {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var payload: [String: Any] = ["trip_id": plan.id, "timestamp": timestamp, "authenticated": true]
        if let loc = location {
            payload["lat"] = loc.latitude
            payload["lon"] = loc.longitude
        }
        LocalStorage.shared.queuePendingAction(
            type: "checkin_authenticated",
            tripId: plan.id,
            payload: payload
        )

        // Update local cache with check-in timestamp
        LocalStorage.shared.updateCachedTripFields(
            tripId: plan.id,
            updates: ["last_checkin": timestamp]
        )

        await MainActor.run {
            // Update local activeTrip state so UI reflects the check-in
            if var updatedTrip = self.activeTrip {
                updatedTrip.last_checkin = timestamp
                self.activeTrip = updatedTrip
                // Sync to allTrips as well
                self.syncTripInAllTrips(updatedTrip)
            }
            self.notice = "Check-in saved (will sync when online)"
            self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
        }

        debugLog("[Session] ℹ️ Authenticated check-in queued for offline sync")
        return true
    }

    func completePlan() async -> Bool {
        guard let plan = activeTrip else { return false }

        // Check if offline FIRST - queue immediately without waiting for network timeout
        if !NetworkMonitor.shared.isConnected {
            return await queueOfflineCompletePlan(plan: plan)
        }

        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(plan.id)/complete"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Update local cache with completed status BEFORE loading other trips
            // This prevents loadActivePlan() from finding stale "active" status in cache
            LocalStorage.shared.updateCachedTripFields(
                tripId: plan.id,
                updates: [
                    "status": "completed",
                    "completed_at": ISO8601DateFormatter().string(from: Date())
                ]
            )

            // Clear cached timeline for this trip
            LocalStorage.shared.clearCachedTimeline(tripId: plan.id)

            // End Live Activity
            await LiveActivityManager.shared.endActivity(for: plan)

            // Stop live location sharing and update UI state in a single dispatch
            await MainActor.run {
                LiveLocationManager.shared.stopSharing()
                self.activeTrip = nil
                self.markTripCompletedInAllTrips(tripId: plan.id)
                self.notice = "Welcome back! Trip completed safely."
                // Update widget data (clears it since no active trip)
                self.updateWidgetData()
                // Check for new achievements after trip completion
                AchievementNotificationManager.shared.checkForNewAchievements(trips: self.allTrips)
            }

            // Reload to check for any other active plans
            // Bug 3 fix: Check protection window to prevent overwriting local trip updates
            if shouldLoadActivePlan() {
                await loadActivePlan()
            }

            return true
        } catch let error as URLError where error.code == .notConnectedToInternet ||
                                            error.code == .networkConnectionLost {
            // Only queue for actual network connectivity issues
            debugLog("[Session] ⚠️ Complete plan network error - queueing offline: \(error.code)")
            return await queueOfflineCompletePlan(plan: plan)
        } catch let error as URLError where error.code == .timedOut {
            // Timeout is tricky - server may have processed. Queue but log warning.
            debugLog("[Session] ⚠️ Complete plan timed out - server may have processed, queueing anyway")
            return await queueOfflineCompletePlan(plan: plan)
        } catch {
            // Other errors (server errors, decode errors) - don't queue, show error
            debugLog("[Session] ❌ Complete plan failed with non-network error: \(error)")
            await MainActor.run {
                self.lastError = "Failed to complete trip. Please try again."
            }
            return false
        }
    }

    private func queueOfflineCompletePlan(plan: Trip) async -> Bool {
        let completedAt = ISO8601DateFormatter().string(from: Date())
        LocalStorage.shared.queuePendingAction(
            type: "complete",
            tripId: plan.id,
            payload: ["completed_at": completedAt]
        )

        // Update local cache with completed status
        LocalStorage.shared.updateCachedTripFields(
            tripId: plan.id,
            updates: [
                "status": "completed",
                "completed_at": completedAt
            ]
        )

        // Clear cached timeline for this trip
        LocalStorage.shared.clearCachedTimeline(tripId: plan.id)

        // End Live Activity
        await LiveActivityManager.shared.endActivity(for: plan)

        // Stop live location sharing and update UI state in a single dispatch
        await MainActor.run {
            LiveLocationManager.shared.stopSharing()
            self.activeTrip = nil
            self.markTripCompletedInAllTrips(tripId: plan.id)
            self.notice = "Trip completed (will sync when online)"
            self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            // Check for new achievements after trip completion
            AchievementNotificationManager.shared.checkForNewAchievements(trips: self.allTrips)
        }

        debugLog("[Session] ℹ️ Complete trip queued for offline sync")
        return true
    }

    func extendPlan(minutes: Int = 30) async -> Bool {
        guard let plan = activeTrip else {
            await MainActor.run {
                self.lastError = "No active plan to extend"
            }
            return false
        }

        // Get current location for extend event (non-blocking, 5s timeout)
        let location = await LocationManager.shared.getCurrentLocation()

        // Calculate new ETA locally for offline update
        // If currently past ETA (overdue), extend from now instead of original ETA
        let now = Date()
        let baseTime = now > plan.eta_at ? now : plan.eta_at
        let newETA = baseTime.addingTimeInterval(Double(minutes) * 60)
        let newETAString = ISO8601DateFormatter().string(from: newETA)

        // Check if offline FIRST - queue immediately without waiting for network timeout
        if !NetworkMonitor.shared.isConnected {
            return await queueOfflineExtendPlan(plan: plan, minutes: minutes, newETA: newETA, newETAString: newETAString, location: location)
        }

        // AGGRESSIVE PROTECTION: Set extension lock FIRST
        // This blocks ALL activeTrip updates from Realtime while extension is in progress
        await MainActor.run {
            self.isExtensionInProgress = true
            self.extensionNewETA = newETA
            self.lastLocalTripUpdate = Date()
            debugLog("[Session] 🔒 Extension lock acquired - blocking all activeTrip updates")
        }

        // Helper to release the lock after a delay
        func releaseExtensionLock() {
            Task {
                // Wait 2 seconds to let UI settle and any pending Realtime events clear
                try? await Task.sleep(for: .seconds(2))
                await MainActor.run {
                    self.isExtensionInProgress = false
                    self.extensionNewETA = nil
                    debugLog("[Session] 🔓 Extension lock released")
                }
            }
        }

        do {
            struct ExtendResponse: Decodable {
                let ok: Bool
                let message: String
                let new_eta: String
            }

            // Construct URL with query parameters properly
            guard var urlComponents = URLComponents(url: url("/api/v1/trips/\(plan.id)/extend"), resolvingAgainstBaseURL: false) else {
                debugLog("[Session] ❌ Failed to construct extend URL")
                releaseExtensionLock()
                return false
            }
            var queryItems = [URLQueryItem(name: "minutes", value: String(minutes))]
            if let loc = location {
                queryItems.append(URLQueryItem(name: "lat", value: String(loc.latitude)))
                queryItems.append(URLQueryItem(name: "lon", value: String(loc.longitude)))
            }
            urlComponents.queryItems = queryItems

            guard let requestURL = urlComponents.url else {
                debugLog("[Session] ❌ Failed to build extend request URL")
                releaseExtensionLock()
                return false
            }

            let response: ExtendResponse = try await withAuth { bearer in
                try await self.api.post(
                    requestURL,
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Parse the server's new_eta and apply it immediately
            // This prevents race conditions with Realtime updates that might have stale data
            if let newETADate = DateUtils.parseISO8601(response.new_eta) {
                // 1. Update cache FIRST to prevent any race with cache reads
                LocalStorage.shared.updateCachedTripFields(
                    tripId: plan.id,
                    updates: ["eta": response.new_eta]
                )

                // 2. Then update in-memory state
                await MainActor.run {
                    if let currentTrip = self.activeTrip {
                        // Update activeTrip with the server's authoritative new ETA
                        let updatedTrip = currentTrip.with(eta_at: newETADate)
                        self.activeTrip = updatedTrip
                        self.lastLocalTripUpdate = Date()  // Prevent Realtime from overwriting this update
                        self.syncTripInAllTrips(updatedTrip)
                        debugLog("[Session] ✅ Applied new ETA from extend response: \(response.new_eta)")
                    }
                }

                // 3. Update Live Activity immediately with the new ETA
                if let updatedTrip = self.activeTrip {
                    let checkinCount = getCheckinCount(tripId: updatedTrip.id)
                    await LiveActivityManager.shared.updateActivity(with: updatedTrip, checkinCount: checkinCount)
                }
            }

            // Skip loadActivePlan() - we already have the authoritative new ETA from the response
            // The activeTrip, allTrips, LiveActivity, and cache are all updated above
            // Calling loadActivePlan() here would overwrite the just-updated activeTrip and cause UI issues

            await MainActor.run {
                self.notice = "Trip extended by \(minutes) minutes"
                // Update widget data with new ETA
                self.updateWidgetData()
            }

            // Release extension lock after a delay to let UI settle
            releaseExtensionLock()
            return true
        } catch let error as URLError where error.code == .notConnectedToInternet ||
                                            error.code == .networkConnectionLost {
            // Only queue for actual network connectivity issues
            debugLog("[Session] ⚠️ Extend plan network error - queueing offline: \(error.code)")
            releaseExtensionLock()
            return await queueOfflineExtendPlan(plan: plan, minutes: minutes, newETA: newETA, newETAString: newETAString, location: location)
        } catch let error as URLError where error.code == .timedOut {
            // Timeout is tricky - server may have processed. Queue but log warning.
            debugLog("[Session] ⚠️ Extend plan timed out - server may have processed, queueing anyway")
            releaseExtensionLock()
            return await queueOfflineExtendPlan(plan: plan, minutes: minutes, newETA: newETA, newETAString: newETAString, location: location)
        } catch {
            // Other errors (server errors, permission denied, etc.) - don't queue, show error
            debugLog("[Session] ❌ Extend plan failed with non-network error: \(error)")
            await MainActor.run {
                self.lastError = "Failed to extend trip. Please try again."
            }
            releaseExtensionLock()
            return false
        }
    }

    private func queueOfflineExtendPlan(plan: Trip, minutes: Int, newETA: Date, newETAString: String, location: CLLocationCoordinate2D?) async -> Bool {
        var payload: [String: Any] = ["minutes": minutes, "new_eta": newETAString]
        if let loc = location {
            payload["lat"] = loc.latitude
            payload["lon"] = loc.longitude
        }
        LocalStorage.shared.queuePendingAction(
            type: "extend",
            tripId: plan.id,
            payload: payload
        )

        // Update local cache with new ETA
        LocalStorage.shared.updateCachedTripFields(
            tripId: plan.id,
            updates: ["eta": newETAString]
        )

        // Update in-memory active trip
        await MainActor.run {
            if let currentTrip = self.activeTrip {
                let updatedTrip = currentTrip.with(eta_at: newETA)
                self.activeTrip = updatedTrip
                self.lastLocalTripUpdate = Date()  // Prevent Realtime from overwriting this update
                // Sync to allTrips as well
                self.syncTripInAllTrips(updatedTrip)
            }
            self.notice = "Trip extended (will sync when online)"
            self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
        }

        debugLog("[Session] ℹ️ Extend trip queued for offline sync")
        return true
    }

    /// Start a planned trip (change status from 'planned' to 'active')
    func startTrip(_ tripId: Int) async -> Bool {
        // Check if offline FIRST - queue immediately without waiting for network timeout
        if !NetworkMonitor.shared.isConnected {
            return await queueOfflineStartTrip(tripId: tripId)
        }

        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/start"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Start Live Activity immediately with known trip data
            if let trip = self.allTrips.first(where: { $0.id == tripId }) {
                let activeTrip = trip.with(status: "active")
                let checkinCount = getCheckinCount(tripId: tripId)
                await LiveActivityManager.shared.startActivity(for: activeTrip, checkinCount: checkinCount)
            }

            // Reload active plan to update UI
            // Bug 3 fix: Check protection window to prevent overwriting local trip updates
            if shouldLoadActivePlan() {
                await loadActivePlan()
            }

            await MainActor.run {
                self.notice = "Trip started!"
                // Update widget data with new active trip
                self.updateWidgetData()
            }
            return true
        } catch {
            // Network failed - queue for later sync
            return await queueOfflineStartTrip(tripId: tripId)
        }
    }

    private func queueOfflineStartTrip(tripId: Int) async -> Bool {
        LocalStorage.shared.queuePendingAction(
            type: "start_trip",
            tripId: tripId,
            payload: ["started_at": ISO8601DateFormatter().string(from: Date())]
        )

        // Update local cache with active status
        LocalStorage.shared.updateCachedTripFields(
            tripId: tripId,
            updates: ["status": "active"]
        )

        // Try to set this trip as the active trip from cache
        let cachedTrips = LocalStorage.shared.getCachedTrips()
        if let trip = cachedTrips.first(where: { $0.id == tripId }) {
            await MainActor.run {
                // Create an updated version with active status
                self.activeTrip = trip.with(status: "active")
                self.notice = "Trip started (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }
        } else {
            await MainActor.run {
                self.notice = "Trip started (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }
        }

        debugLog("[Session] ℹ️ Start trip queued for offline sync")
        return true
    }

    func loadTimeline(planId: Int) async -> [TimelineEvent] {
        // Get cached events first for fallback
        let cachedEvents = LocalStorage.shared.getCachedTimeline(tripId: planId)

        do {
            // Backend returns array of TimelineEvent directly (not wrapped in TimelineResponse)
            let events: [TimelineEvent] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/\(planId)/timeline"),
                    bearer: bearer
                )
            }

            debugLog("[Session] ✅ Loaded \(events.count) timeline events for trip \(planId)")

            // Cache for offline access
            LocalStorage.shared.cacheTimeline(tripId: planId, events: events)

            return events
        } catch {
            debugLog("[Session] ❌ Failed to load timeline: \(error.localizedDescription)")

            // Return cached data as fallback
            if !cachedEvents.isEmpty {
                debugLog("[Session] Using \(cachedEvents.count) cached timeline events")
                return cachedEvents
            }

            return []
        }
    }

    /// Notify views that timeline data has been updated (called by RealtimeManager)
    func notifyTimelineUpdated() {
        timelineLastUpdated = Date()
        debugLog("[Session] Timeline update notification sent")
    }

    // MARK: - Profile Management
    func updateProfile(firstName: String? = nil, lastName: String? = nil, age: Int? = nil) async -> Bool {
        struct UpdateProfileRequest: Encodable {
            let first_name: String?
            let last_name: String?
            let age: Int?
        }

        // Check offline first - queue for later sync
        if !NetworkMonitor.shared.isConnected {
            var payload: [String: Any] = [:]
            if let firstName = firstName { payload["first_name"] = firstName }
            if let lastName = lastName { payload["last_name"] = lastName }
            if let age = age { payload["age"] = age }

            LocalStorage.shared.queuePendingAction(
                type: "update_profile",
                tripId: nil,
                payload: payload
            )

            // Update local state immediately
            await MainActor.run {
                if let first = firstName, let last = lastName {
                    self.userName = "\(first) \(last)"
                }
                if let age = age {
                    self.userAge = age
                }
                self.notice = "Profile updated (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Profile update queued for offline sync")
            return true
        }

        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.patch(
                    self.url("/api/v1/profile"),
                    body: UpdateProfileRequest(first_name: firstName, last_name: lastName, age: age),
                    bearer: bearer
                )
            }

            await MainActor.run {
                if let first = firstName, let last = lastName {
                    self.userName = "\(first) \(last)"
                }
                if let age = age {
                    self.userAge = age
                }
                self.notice = "Profile updated successfully"
            }
            return true
        } catch {
            // Network error - queue for later sync
            var payload: [String: Any] = [:]
            if let firstName = firstName { payload["first_name"] = firstName }
            if let lastName = lastName { payload["last_name"] = lastName }
            if let age = age { payload["age"] = age }

            LocalStorage.shared.queuePendingAction(
                type: "update_profile",
                tripId: nil,
                payload: payload
            )

            // Update local state immediately
            await MainActor.run {
                if let first = firstName, let last = lastName {
                    self.userName = "\(first) \(last)"
                }
                if let age = age {
                    self.userAge = age
                }
                self.notice = "Profile updated (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Profile update queued for offline sync")
            return true
        }
    }

    // MARK: - Delete Account
    func deleteAccount() async -> Bool {
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/profile/account"),
                    bearer: bearer
                )
            }

            await MainActor.run {
                // Clear all data and sign out
                self.signOut()
            }
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to delete account: \(error.localizedDescription)"
            }
            return false
        }
    }

    // MARK: - Delete Plan
    func deletePlan(_ planId: Int) async -> Bool {
        // Check if user is a participant (not owner) of a group trip
        // If so, call leaveTrip instead of delete
        if let trip = allTrips.first(where: { $0.id == planId }),
           let currentUserId = self.userId,
           trip.user_id != currentUserId,
           trip.is_group_trip {
            // User is a participant, not the owner - leave instead of delete
            debugLog("[Session] User is a participant, calling leaveTrip instead of delete")
            let success = await leaveTrip(tripId: planId)
            if success {
                // Clear cached data
                LocalStorage.shared.clearCachedTimeline(tripId: planId)
                LocalStorage.shared.removeCachedTrip(tripId: planId)

                await MainActor.run {
                    self.allTrips.removeAll { $0.id == planId }
                    if self.activeTrip?.id == planId {
                        self.activeTrip = nil
                    }
                }
            }
            return success
        }

        // User is the owner - proceed with delete
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/trips/\(planId)"),
                    bearer: bearer
                )
            }

            // Clear cached timeline for this trip
            LocalStorage.shared.clearCachedTimeline(tripId: planId)

            await MainActor.run {
                self.allTrips.removeAll { $0.id == planId }
                self.notice = "Trip deleted successfully"
            }
            return true
        } catch {
            // Queue for later sync when offline
            LocalStorage.shared.queuePendingAction(
                type: "delete_trip",
                tripId: planId,
                payload: ["deleted_at": ISO8601DateFormatter().string(from: Date())]
            )

            // Remove from local cache
            LocalStorage.shared.removeCachedTrip(tripId: planId)

            // Clear cached timeline for this trip
            LocalStorage.shared.clearCachedTimeline(tripId: planId)

            await MainActor.run {
                self.allTrips.removeAll { $0.id == planId }
                // Clear active trip if it was the one being deleted
                if self.activeTrip?.id == planId {
                    self.activeTrip = nil
                }
                self.notice = "Trip deleted (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Delete trip queued for offline sync")
            return true
        }
    }

    // MARK: - Load User Profile
    func loadUserProfile() async {
        struct UserProfileResponse: Decodable {
            let id: Int?
            let email: String?
            let first_name: String?
            let last_name: String?
            let age: Int?
            let profile_completed: Bool?
            let created_at: String?
        }

        do {
            let response: UserProfileResponse = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/profile"),
                    bearer: bearer
                )
            }

            await MainActor.run {
                // Store user ID for ownership checks
                if let id = response.id {
                    self.userId = id
                }
                // Combine first and last name
                if let first = response.first_name, let last = response.last_name {
                    self.userName = "\(first) \(last)"
                }
                if let age = response.age {
                    self.userAge = age
                }
                if let email = response.email {
                    self.userEmail = email
                }
                if let createdAt = response.created_at {
                    self.memberSince = DateUtils.parseISO8601(createdAt)
                }
                self.profileCompleted = response.profile_completed ?? false

                // Save to keychain
                self.saveUserDataToKeychain()
            }
        } catch {
            // If profile endpoint fails, just keep existing cached data
            // Don't auto-signout - tokens last 30 days and user should stay signed in
            debugLog("Failed to load user profile: \(error.localizedDescription)")
        }
    }

    // MARK: - Sync Notification Preferences
    func syncNotificationPreferences(tripReminders: Bool, checkInAlerts: Bool) async {
        struct NotificationPrefsUpdate: Encodable {
            let notify_trip_reminders: Bool
            let notify_checkin_alerts: Bool
        }

        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.put(
                    self.url("/api/v1/profile"),
                    body: NotificationPrefsUpdate(
                        notify_trip_reminders: tripReminders,
                        notify_checkin_alerts: checkInAlerts
                    ),
                    bearer: bearer
                )
            }
            debugLog("[Session] Notification preferences synced: tripReminders=\(tripReminders), checkInAlerts=\(checkInAlerts)")
        } catch {
            debugLog("[Session] Failed to sync notification preferences: \(error.localizedDescription)")
        }
    }

    // MARK: - Export User Data
    func exportUserData() async -> Data? {
        do {
            let data: Data = try await withAuth { bearer in
                // Get raw JSON data instead of decoding
                guard let url = URL(string: "\(self.baseURL)/api/v1/profile/export") else {
                    throw API.APIError.server("Invalid URL")
                }

                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    throw API.APIError.server("Failed to export data")
                }

                return data
            }
            return data
        } catch {
            await MainActor.run {
                self.lastError = "Failed to export data: \(error.localizedDescription)"
            }
            return nil
        }
    }

    // MARK: - Saved Contacts Management
    func loadContacts(forceRefresh: Bool = false) async -> [Contact] {
        // Return cached immediately if available and not forcing refresh
        if !forceRefresh && !contacts.isEmpty {
            debugLog("[Session] 📦 Using \(contacts.count) cached contacts (in-memory)")
            return contacts
        }

        // Try local storage cache for immediate display
        let cachedContacts = LocalStorage.shared.getCachedContacts()
        if !cachedContacts.isEmpty && !forceRefresh {
            await MainActor.run {
                self.contacts = cachedContacts
            }
        }

        // If offline, return cached data
        if !NetworkMonitor.shared.isConnected {
            debugLog("[Session] 📦 Offline - returning \(cachedContacts.count) cached contacts")
            return cachedContacts
        }

        do {
            let loadedContacts: [Contact] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/contacts/"),
                    bearer: bearer
                )
            }

            // Cache contacts for offline access
            LocalStorage.shared.cacheContacts(loadedContacts)

            await MainActor.run {
                self.contacts = loadedContacts
            }
            return loadedContacts
        } catch {
            debugLog("Failed to load saved contacts: \(error.localizedDescription)")

            // Fall back to cached contacts when offline
            if !cachedContacts.isEmpty {
                debugLog("[Session] 📦 Using \(cachedContacts.count) cached contacts")
                await MainActor.run {
                    self.contacts = cachedContacts
                }
                return cachedContacts
            }

            return []
        }
    }

    func addContact(name: String, email: String) async -> Contact? {
        struct AddContactRequest: Encodable {
            let name: String
            let email: String
        }

        let requestBody = AddContactRequest(name: name, email: email)

        do {
            let response: Contact = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/contacts/"),
                    body: requestBody,
                    bearer: bearer
                )
            }

            // Cache the new contact
            LocalStorage.shared.cacheContact(response)

            return response
        } catch {
            // Create a temporary contact with a negative ID for local use
            // Use UUID hash to guarantee uniqueness (timestamp could collide if multiple contacts created in same second)
            let tempId = -abs(UUID().hashValue)
            let tempContact = Contact(id: tempId, user_id: 0, name: name, email: email, group: nil)

            // Queue for later sync when offline (include temp_id for cleanup after sync)
            LocalStorage.shared.queuePendingAction(
                type: "add_contact",
                tripId: nil,
                payload: ["name": name, "email": email, "temp_id": tempId]
            )

            // Cache the temporary contact
            LocalStorage.shared.cacheContact(tempContact)

            // Add to in-memory contacts list
            await MainActor.run {
                self.contacts.append(tempContact)
                self.notice = "Contact saved (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Add contact queued for offline sync")
            return tempContact
        }
    }

    func updateContact(contactId: Int, name: String, email: String) async -> Bool {
        struct UpdateContactRequest: Encodable {
            let name: String
            let email: String
        }

        do {
            let _: Contact = try await withAuth { bearer in
                try await self.api.put(
                    self.url("/api/v1/contacts/\(contactId)"),
                    body: UpdateContactRequest(name: name, email: email),
                    bearer: bearer
                )
            }

            // Update cached contact
            LocalStorage.shared.updateCachedContact(contactId: contactId, name: name, email: email)

            return true
        } catch {
            // Queue for later sync when offline
            LocalStorage.shared.queuePendingAction(
                type: "update_contact",
                tripId: nil,
                payload: ["contact_id": contactId, "name": name, "email": email]
            )

            // Update cached contact locally
            LocalStorage.shared.updateCachedContact(contactId: contactId, name: name, email: email)

            // Update in-memory contacts list
            await MainActor.run {
                if let index = self.contacts.firstIndex(where: { $0.id == contactId }) {
                    self.contacts[index] = Contact(id: contactId, user_id: self.contacts[index].user_id, name: name, email: email, group: self.contacts[index].group)
                }
                self.notice = "Contact updated (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Update contact queued for offline sync")
            return true
        }
    }

    func deleteContact(_ contactId: Int) async -> Bool {
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/contacts/\(contactId)"),
                    bearer: bearer
                )
            }

            // Remove from cache
            LocalStorage.shared.removeCachedContact(contactId: contactId)

            return true
        } catch {
            // Queue for later sync when offline
            LocalStorage.shared.queuePendingAction(
                type: "delete_contact",
                tripId: nil,
                payload: ["contact_id": contactId]
            )

            // Remove from cache locally
            LocalStorage.shared.removeCachedContact(contactId: contactId)

            // Remove from in-memory contacts list
            await MainActor.run {
                self.contacts.removeAll { $0.id == contactId }
                self.notice = "Contact deleted (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Delete contact queued for offline sync")
            return true
        }
    }

    // MARK: - Friends Management

    /// Load all friends for the current user
    func loadFriends(forceRefresh: Bool = false) async -> [Friend] {
        // Return cached immediately if available and not forcing refresh
        if !forceRefresh && !friends.isEmpty {
            debugLog("[Session] 📦 Using \(friends.count) cached friends (in-memory)")
            return friends
        }

        // Try local storage cache for immediate display
        let cachedFriends = LocalStorage.shared.getCachedFriends()
        if !cachedFriends.isEmpty && !forceRefresh {
            await MainActor.run {
                self.friends = cachedFriends
            }
        }

        // If offline, return cached data
        if !NetworkMonitor.shared.isConnected {
            debugLog("[Session] 📦 Offline - returning \(cachedFriends.count) cached friends")
            return cachedFriends
        }

        do {
            let loadedFriends: [Friend] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/friends/"),
                    bearer: bearer
                )
            }

            // Cache friends for offline access
            LocalStorage.shared.cacheFriends(loadedFriends)

            await MainActor.run {
                self.friends = loadedFriends
            }
            debugLog("[Session] ✅ Loaded \(loadedFriends.count) friends")
            return loadedFriends
        } catch {
            debugLog("[Session] ❌ Failed to load friends: \(error.localizedDescription)")
            return cachedFriends
        }
    }

    /// Load pending invites sent by the current user
    func loadPendingInvites() async -> [PendingInvite] {
        do {
            let invites: [PendingInvite] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/friends/invites/pending"),
                    bearer: bearer
                )
            }

            await MainActor.run {
                self.pendingInvites = invites
            }
            debugLog("[Session] ✅ Loaded \(invites.count) pending invites")
            return invites
        } catch {
            debugLog("[Session] ❌ Failed to load pending invites: \(error.localizedDescription)")
            return []
        }
    }

    /// Load active trips where the current user is a friend safety contact
    func loadFriendActiveTrips() async -> [FriendActiveTrip] {
        do {
            let trips: [FriendActiveTrip] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/friends/active-trips"),
                    bearer: bearer
                )
            }

            await MainActor.run {
                self.friendActiveTrips = trips
            }
            debugLog("[Session] ✅ Loaded \(trips.count) friend active trips")
            return trips
        } catch {
            debugLog("[Session] ❌ Failed to load friend active trips: \(error.localizedDescription)")
            return []
        }
    }

    /// Load detailed achievements for a friend
    /// Returns nil if friend has disabled achievement sharing or on error
    func loadFriendAchievements(friendUserId: Int) async -> FriendAchievementsResponse? {
        do {
            let response: FriendAchievementsResponse = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/friends/\(friendUserId)/achievements"),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Loaded \(response.earned_count) achievements for friend \(friendUserId)")
            return response
        } catch API.APIError.httpError(let statusCode, _) where statusCode == 403 {
            // Friend has disabled achievement sharing
            debugLog("[Session] 🔒 Friend \(friendUserId) has disabled achievement sharing")
            return nil
        } catch {
            debugLog("[Session] ❌ Failed to load friend achievements: \(error.localizedDescription)")
            return nil
        }
    }

    /// Request an update from a trip owner (friend ping feature)
    /// Returns the response with cooldown info if rate limited
    func requestTripUpdate(tripId: Int) async -> UpdateRequestResponse {
        do {
            let response: UpdateRequestResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/friends/trips/\(tripId)/request-update"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }
            if response.ok {
                debugLog("[Session] ✅ Sent update request for trip \(tripId)")
            } else {
                debugLog("[Session] ⏳ Update request rate limited: \(response.cooldown_remaining_seconds ?? 0)s remaining")
            }
            return response
        } catch {
            debugLog("[Session] ❌ Failed to send update request: \(error.localizedDescription)")
            return UpdateRequestResponse(ok: false, message: "Failed to send request", cooldown_remaining_seconds: nil)
        }
    }

    /// Get remaining cooldown seconds for a trip's update request
    func getCooldownRemaining(for tripId: Int) -> Int? {
        guard let endTime = updateRequestCooldowns[tripId] else { return nil }
        let remaining = Int(endTime.timeIntervalSinceNow)
        if remaining <= 0 {
            updateRequestCooldowns.removeValue(forKey: tripId)
            return nil
        }
        return remaining
    }

    /// Set cooldown for a trip's update request
    func setCooldown(for tripId: Int, seconds: Int) {
        updateRequestCooldowns[tripId] = Date().addingTimeInterval(Double(seconds))
    }

    /// Update live location for a trip
    /// Sends the current location to the server for friends to see
    func updateLiveLocation(
        tripId: Int,
        latitude: Double,
        longitude: Double,
        altitude: Double?,
        horizontalAccuracy: Double?,
        speed: Double?
    ) async throws -> Bool {
        struct LiveLocationBody: Encodable {
            let latitude: Double
            let longitude: Double
            let altitude: Double?
            let horizontal_accuracy: Double?
            let speed: Double?
        }

        struct LiveLocationResponse: Decodable {
            let ok: Bool
            let message: String
        }

        let body = LiveLocationBody(
            latitude: latitude,
            longitude: longitude,
            altitude: altitude,
            horizontal_accuracy: horizontalAccuracy,
            speed: speed
        )

        let response: LiveLocationResponse = try await withAuth { bearer in
            try await self.api.post(
                self.url("/api/v1/trips/\(tripId)/live-location"),
                body: body,
                bearer: bearer
            )
        }

        return response.ok
    }

    /// Load friend visibility settings
    func loadFriendVisibilitySettings() async -> FriendVisibilitySettings {
        do {
            let settings: FriendVisibilitySettings = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/profile/friend-visibility"),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Loaded friend visibility settings")
            await MainActor.run {
                self.friendVisibilitySettings = settings
            }
            return settings
        } catch {
            debugLog("[Session] ❌ Failed to load friend visibility settings: \(error.localizedDescription)")
            return .defaults
        }
    }

    /// Save friend visibility settings
    func saveFriendVisibilitySettings(_ settings: FriendVisibilitySettings) async -> Bool {
        do {
            let _: FriendVisibilitySettings = try await withAuth { bearer in
                try await self.api.put(
                    self.url("/api/v1/profile/friend-visibility"),
                    body: settings,
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Saved friend visibility settings")
            await MainActor.run {
                self.friendVisibilitySettings = settings
            }
            return true
        } catch {
            debugLog("[Session] ❌ Failed to save friend visibility settings: \(error.localizedDescription)")
            await MainActor.run {
                self.lastError = "Failed to save settings"
            }
            return false
        }
    }

    /// Get or create the user's reusable friend invite link
    /// - Parameter regenerate: If true, invalidates the old link and creates a new one
    func createFriendInvite(regenerate: Bool = false) async -> FriendInvite? {
        do {
            let urlString = regenerate
                ? "/api/v1/friends/invite?regenerate=true"
                : "/api/v1/friends/invite"
            let invite: FriendInvite = try await withAuth { bearer in
                try await self.api.post(
                    self.url(urlString),
                    body: API.Empty(),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Got friend invite: \(invite.invite_url)")
            return invite
        } catch {
            await MainActor.run {
                self.lastError = "Failed to get invite: \(error.localizedDescription)"
            }
            return nil
        }
    }

    /// Get preview of a friend invite (public - no auth required)
    func getFriendInvitePreview(token: String) async -> FriendInvitePreview? {
        do {
            let preview: FriendInvitePreview = try await api.get(
                url("/api/v1/friends/invite/\(token)"),
                bearer: nil  // Public endpoint
            )
            debugLog("[Session] ✅ Got invite preview for token: \(token.prefix(8))...")
            return preview
        } catch {
            debugLog("[Session] ❌ Failed to get invite preview: \(error.localizedDescription)")
            return nil
        }
    }

    /// Accept a friend invite and create the friendship
    func acceptFriendInvite(token: String) async -> Friend? {
        do {
            let friend: Friend = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/friends/invite/\(token)/accept"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Add to local friends list
            await MainActor.run {
                self.friends.insert(friend, at: 0)  // Most recent first
                self.notice = "You're now friends with \(friend.fullName)!"
            }

            // Update cache
            LocalStorage.shared.cacheFriend(friend)

            debugLog("[Session] ✅ Accepted invite, now friends with \(friend.fullName)")
            return friend
        } catch let API.APIError.httpError(statusCode, message) {
            await MainActor.run {
                switch statusCode {
                case 404:
                    self.lastError = "Invite not found"
                case 409:
                    self.lastError = "You're already friends!"
                case 410:
                    self.lastError = "This invite has expired"
                default:
                    self.lastError = message
                }
            }
            return nil
        } catch {
            await MainActor.run {
                self.lastError = "Failed to accept invite: \(error.localizedDescription)"
            }
            return nil
        }
    }

    /// Remove a friend
    func removeFriend(userId: Int) async -> Bool {
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/friends/\(userId)"),
                    bearer: bearer
                )
            }

            // Remove from local lists
            await MainActor.run {
                self.friends.removeAll { $0.user_id == userId }
                // Also remove any active trips from this friend
                self.friendActiveTrips.removeAll { $0.owner.user_id == userId }
                self.notice = "Friend removed"
            }

            // Remove from cache
            LocalStorage.shared.removeCachedFriend(userId: userId)

            debugLog("[Session] ✅ Removed friend \(userId)")
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to remove friend: \(error.localizedDescription)"
            }
            return false
        }
    }

    /// Get a specific friend's profile
    func getFriend(userId: Int) async -> Friend? {
        // Check cache first
        if let cached = friends.first(where: { $0.user_id == userId }) {
            return cached
        }

        do {
            let friend: Friend = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/friends/\(userId)"),
                    bearer: bearer
                )
            }
            return friend
        } catch {
            debugLog("[Session] ❌ Failed to get friend: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Group Trip Participants

    /// Invite friends to a group trip
    func inviteParticipants(tripId: Int, friendUserIds: [Int]) async -> [TripParticipant]? {
        do {
            let request = ParticipantInviteRequest(friend_user_ids: friendUserIds)
            let participants: [TripParticipant] = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/participants"),
                    body: request,
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Invited \(friendUserIds.count) friends to trip \(tripId)")
            return participants
        } catch {
            await MainActor.run {
                self.lastError = "Failed to invite participants: \(error.localizedDescription)"
            }
            return nil
        }
    }

    /// Get all participants for a group trip
    func getParticipants(tripId: Int) async -> ParticipantListResponse? {
        do {
            let response: ParticipantListResponse = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/\(tripId)/participants"),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Loaded \(response.participants.count) participants for trip \(tripId)")
            return response
        } catch {
            debugLog("[Session] ❌ Failed to get participants: \(error.localizedDescription)")
            return nil
        }
    }

    /// Get the current user's safety contacts for a trip (their own contacts, not owner's)
    func getMyTripContacts(tripId: Int) async -> [TripContact] {
        do {
            let response: MyTripContactsResponse = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/\(tripId)/my-contacts"),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Loaded \(response.contacts.count) contacts for trip \(tripId)")
            return response.contacts
        } catch {
            debugLog("[Session] ❌ Failed to get my contacts: \(error.localizedDescription)")
            return []
        }
    }

    /// Refresh the vote status for a group trip (called by RealtimeManager)
    func refreshVoteStatus(tripId: Int) async {
        guard let response = await getParticipants(tripId: tripId) else { return }
        if response.checkout_votes_needed > 0 {
            let hasVoted = response.user_has_voted ?? false
            activeVoteStatus = (tripId: tripId, votesCast: response.checkout_votes, votesNeeded: response.checkout_votes_needed, userHasVoted: hasVoted)
            debugLog("[Session] Vote status updated: \(response.checkout_votes)/\(response.checkout_votes_needed), userHasVoted=\(hasVoted)")
        }
    }

    /// Accept an invitation to join a group trip with personal notification settings
    func acceptTripInvitation(
        tripId: Int,
        safetyContactIds: [Int],
        safetyFriendIds: [Int] = [],
        checkinIntervalMin: Int = 30,
        notifyStartHour: Int? = nil,
        notifyEndHour: Int? = nil
    ) async -> Bool {
        debugLog("[Session] 🔵 ACCEPT called for trip \(tripId) with contacts \(safetyContactIds), friends \(safetyFriendIds)")
        do {
            let request = AcceptInvitationRequest(
                safety_contact_ids: safetyContactIds,
                safety_friend_ids: safetyFriendIds,
                checkin_interval_min: checkinIntervalMin,
                notify_start_hour: notifyStartHour,
                notify_end_hour: notifyEndHour
            )
            debugLog("[Session] 🔵 Sending POST to /accept endpoint for trip \(tripId)")
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/participants/accept"),
                    body: request,
                    bearer: bearer
                )
            }
            await MainActor.run {
                self.notice = "Joined the trip!"
            }
            debugLog("[Session] ✅ Accepted trip invitation for trip \(tripId) with \(safetyContactIds.count) contacts, \(safetyFriendIds.count) friends")
            return true
        } catch {
            debugLog("[Session] ❌ FAILED to accept trip \(tripId): \(error)")
            await MainActor.run {
                self.lastError = "Failed to accept invitation: \(error.localizedDescription)"
            }
            return false
        }
    }

    /// Decline an invitation to join a group trip
    func declineTripInvitation(tripId: Int) async -> Bool {
        debugLog("[Session] 🔴 DECLINE called for trip \(tripId)")
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/participants/decline"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Declined trip invitation for trip \(tripId)")
            return true
        } catch {
            debugLog("[Session] ❌ FAILED to decline trip \(tripId): \(error)")
            await MainActor.run {
                self.lastError = "Failed to decline invitation: \(error.localizedDescription)"
            }
            return false
        }
    }

    /// Leave a group trip
    func leaveTrip(tripId: Int) async -> Bool {
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/participants/leave"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }
            await MainActor.run {
                self.notice = "Left the trip"
            }
            debugLog("[Session] ✅ Left trip \(tripId)")
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to leave trip: \(error.localizedDescription)"
            }
            return false
        }
    }

    /// Remove a participant from a group trip (owner only)
    func removeParticipant(tripId: Int, userId: Int) async -> Bool {
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/trips/\(tripId)/participants/\(userId)"),
                    bearer: bearer
                )
            }
            await MainActor.run {
                self.notice = "Participant removed"
            }
            debugLog("[Session] ✅ Removed participant \(userId) from trip \(tripId)")
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to remove participant: \(error.localizedDescription)"
            }
            return false
        }
    }

    /// Get all participant locations for a group trip
    func getParticipantLocations(tripId: Int) async -> [ParticipantLocation]? {
        do {
            let locations: [ParticipantLocation] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/\(tripId)/locations"),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Loaded \(locations.count) participant locations for trip \(tripId)")
            return locations
        } catch {
            debugLog("[Session] ❌ Failed to get participant locations: \(error.localizedDescription)")
            return nil
        }
    }

    /// Check in to a group trip as a participant
    func checkinGroupTrip(tripId: Int, lat: Double? = nil, lon: Double? = nil) async -> Bool {
        do {
            var urlString = "/api/v1/trips/\(tripId)/checkin"
            var queryParams: [String] = []
            if let lat = lat {
                queryParams.append("lat=\(lat)")
            }
            if let lon = lon {
                queryParams.append("lon=\(lon)")
            }
            if !queryParams.isEmpty {
                urlString += "?" + queryParams.joined(separator: "&")
            }

            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url(urlString),
                    body: API.Empty(),
                    bearer: bearer
                )
            }
            await MainActor.run {
                self.notice = "Checked in!"
            }
            debugLog("[Session] ✅ Checked in to group trip \(tripId)")
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to check in: \(error.localizedDescription)"
            }
            return false
        }
    }

    /// Cast a vote to checkout (end) the group trip
    func voteCheckout(tripId: Int) async -> CheckoutVoteResponse? {
        do {
            let response: CheckoutVoteResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/checkout/vote"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }
            await MainActor.run {
                if response.trip_completed {
                    self.notice = "Trip completed!"
                } else {
                    self.notice = "Vote recorded (\(response.votes_cast)/\(response.votes_needed))"
                }
            }
            debugLog("[Session] ✅ Checkout vote for trip \(tripId): \(response.votes_cast)/\(response.votes_needed)")
            return response
        } catch {
            await MainActor.run {
                self.lastError = "Failed to vote: \(error.localizedDescription)"
            }
            return nil
        }
    }

    /// Remove a previously cast checkout vote
    func removeVote(tripId: Int) async -> CheckoutVoteResponse? {
        do {
            let response: CheckoutVoteResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/trips/\(tripId)/checkout/vote"),
                    bearer: bearer
                )
            }
            await MainActor.run {
                self.notice = "Vote removed (\(response.votes_cast)/\(response.votes_needed))"
            }
            debugLog("[Session] ✅ Removed vote for trip \(tripId): \(response.votes_cast)/\(response.votes_needed)")
            return response
        } catch {
            await MainActor.run {
                self.lastError = "Failed to remove vote: \(error.localizedDescription)"
            }
            return nil
        }
    }

    /// Get pending trip invitations for the current user
    func getPendingTripInvitations() async -> [TripInvitation]? {
        do {
            let invitations: [TripInvitation] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/invitations/pending"),
                    bearer: bearer
                )
            }
            debugLog("[Session] ✅ Loaded \(invitations.count) pending trip invitations")
            return invitations
        } catch {
            debugLog("[Session] ❌ Failed to get pending invitations: \(error.localizedDescription)")
            return nil
        }
    }

    /// Load trip invitations and update the published property
    @MainActor
    func loadTripInvitations() async {
        if let invitations = await getPendingTripInvitations() {
            self.tripInvitations = invitations
        }
    }

    // MARK: - Activities Management
    @MainActor
    func loadActivities() async {
        // If offline, use cache immediately - don't wait for network timeout
        if !NetworkMonitor.shared.isConnected {
            let cachedActivities = LocalStorage.shared.getCachedActivities()
            if !cachedActivities.isEmpty {
                self.activities = cachedActivities.sorted { $0.order < $1.order }
                debugLog("[Session] 📦 Loaded \(cachedActivities.count) activities from cache (offline)")
            }
            return
        }

        debugLog("[Session] 🔄 Loading activities from backend...")
        do {
            let response: [Activity] = try await api.get(
                url("/api/v1/activities/"),
                bearer: nil  // Activities endpoint doesn't require auth
            )

            // Already on MainActor - update state directly
            self.activities = response.sorted { $0.order < $1.order }
            debugLog("[Session] ✅ Loaded \(response.count) activities from backend")

            // Cache for offline access
            LocalStorage.shared.cacheActivities(response)
            debugLog("[Session] 💾 Activities cached to local storage")
        } catch {
            debugLog("[Session] ❌ Failed to load activities from backend: \(error)")

            // Fall back to cached activities on error
            // Already on MainActor - update state directly
            let cachedActivities = LocalStorage.shared.getCachedActivities()
            if !cachedActivities.isEmpty {
                self.activities = cachedActivities
                self.notice = "Showing cached activities (offline mode)"
                debugLog("[Session] 📦 Using \(cachedActivities.count) cached activities")
            } else {
                // No activities available - user needs internet connection
                self.activities = []
                self.lastError = "Unable to load activities. Please check your internet connection."
                debugLog("[Session] ❌ No activities available (no backend or cache)")
            }
        }
    }

    @MainActor
    func refreshActivities() async {
        isLoadingActivities = true
        await loadActivities()
        isLoadingActivities = false
    }

    // MARK: - Global Stats

    /// Fetch global platform statistics (public endpoint, no auth required)
    func fetchGlobalStats() async -> GlobalStats? {
        do {
            let stats: GlobalStats = try await api.get(
                url("/api/v1/stats/global"),
                bearer: nil
            )
            debugLog("[Session] ✅ Loaded global stats: \(stats.total_users) users, \(stats.total_completed_trips) trips")
            return stats
        } catch {
            debugLog("[Session] ❌ Failed to load global stats: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Trip Templates

    /// Load templates from local storage
    func loadTemplates() {
        savedTemplates = LocalStorage.shared.getTemplates()
        debugLog("[Session] 📋 Loaded \(savedTemplates.count) saved templates")
    }

    /// Save a new template
    func saveTemplate(_ template: SavedTripTemplate) {
        LocalStorage.shared.saveTemplate(template)
        loadTemplates()
        debugLog("[Session] ✅ Saved template: \(template.name)")
    }

    /// Delete a template
    func deleteTemplate(_ template: SavedTripTemplate) {
        LocalStorage.shared.deleteTemplate(id: template.id)
        loadTemplates()
        debugLog("[Session] 🗑️ Deleted template: \(template.name)")
    }

    /// Mark template as used (updates lastUsedAt for sorting)
    func markTemplateUsed(_ template: SavedTripTemplate) {
        LocalStorage.shared.updateTemplateLastUsed(id: template.id)
        loadTemplates()
        debugLog("[Session] 📝 Marked template as used: \(template.name)")
    }

    // MARK: - Live Activity Helpers

    /// Get check-in count from cached timeline events for a trip
    private func getCheckinCount(tripId: Int) -> Int {
        let cachedTimeline = LocalStorage.shared.getCachedTimeline(tripId: tripId)
        return cachedTimeline.filter { $0.kind == "checkin" }.count
    }

    // MARK: - Widget Data Sharing

    /// Update shared widget data with current active trip
    /// Call this whenever activeTrip changes to keep widgets in sync
    @MainActor
    func updateWidgetData() {
        guard let trip = activeTrip else {
            // Clear widget data when no active trip
            TripStateManager.shared.clearTripState()
            debugLog("[Session] 📱 Cleared widget data (no active trip)")
            return
        }

        // Get check-in count from timeline
        let checkinCount = getCheckinCount(tripId: trip.id)

        // Use TripStateManager to update widget data with proper Codable encoding
        TripStateManager.shared.updateTripState(trip: trip, checkinCount: checkinCount)
        debugLog("[Session] 📱 Updated widget data for trip: \(trip.title)")
    }

    // MARK: - Subscription Management

    /// UserDefaults key for cached feature limits
    private static let featureLimitsCacheKey = "cachedFeatureLimits"

    /// Load feature limits from the backend with offline caching
    @MainActor
    func loadFeatureLimits() async {
        guard let token = accessToken else {
            debugLog("[Session] No access token, using default feature limits")
            loadCachedFeatureLimits()
            return
        }

        let url = baseURL.appendingPathComponent("/api/v1/subscriptions/limits")

        do {
            let limits: FeatureLimits = try await api.get(url, bearer: token)
            self.featureLimits = limits
            self.subscriptionTier = limits.tier

            // Cache feature limits for offline use
            cacheFeatureLimits(limits)

            // Sync widgets enabled status to shared defaults for widget access
            LiveActivityConstants.setWidgetsEnabled(limits.widgetsEnabled)
            // Apply premium feature restrictions for free tier
            applyTierRestrictions(isPremium: limits.isPremium)
            debugLog("[Session] Feature limits loaded: tier=\(limits.tier), premium=\(limits.isPremium)")
        } catch {
            debugLog("[Session] Failed to load feature limits: \(error)")
            // Try to load from cache for offline support
            loadCachedFeatureLimits()
        }
    }

    /// Cache feature limits to UserDefaults for offline access
    private func cacheFeatureLimits(_ limits: FeatureLimits) {
        do {
            let data = try JSONEncoder().encode(limits)
            UserDefaults.standard.set(data, forKey: Session.featureLimitsCacheKey)
            debugLog("[Session] Feature limits cached for offline use")
        } catch {
            debugLog("[Session] Failed to cache feature limits: \(error)")
        }
    }

    /// Load cached feature limits from UserDefaults
    private func loadCachedFeatureLimits() {
        // First check if we have cached data
        if let data = UserDefaults.standard.data(forKey: Session.featureLimitsCacheKey) {
            do {
                let cachedLimits = try JSONDecoder().decode(FeatureLimits.self, from: data)
                self.featureLimits = cachedLimits
                self.subscriptionTier = cachedLimits.tier
                LiveActivityConstants.setWidgetsEnabled(cachedLimits.widgetsEnabled)
                debugLog("[Session] Loaded cached feature limits: tier=\(cachedLimits.tier)")
                return
            } catch {
                debugLog("[Session] Failed to decode cached feature limits: \(error)")
            }
        }

        // Fallback: Check StoreKit subscription status for offline premium detection
        if SubscriptionManager.shared.subscriptionStatus.isPremium {
            // User has local subscription, use premium defaults
            self.featureLimits = .plus
            self.subscriptionTier = "plus"
            LiveActivityConstants.setWidgetsEnabled(true)
            debugLog("[Session] Using premium defaults based on local subscription status")
        } else {
            // Default to free tier
            debugLog("[Session] No cached limits, using free tier defaults")
        }
    }

    /// Apply tier-based restrictions for premium features
    private func applyTierRestrictions(isPremium: Bool) {
        let groupDefaults = UserDefaults(suiteName: "group.com.homeboundapp.Homebound")

        if !isPremium {
            // Free tier: disable Live Activity if currently enabled
            if groupDefaults?.bool(forKey: "liveActivityEnabled") == true {
                groupDefaults?.set(false, forKey: "liveActivityEnabled")
            }
            // Free tier: clear pinned activities (both UserDefaults and in-memory)
            UserDefaults.standard.removeObject(forKey: "pinnedActivityIds")
            AppPreferences.shared.clearPinnedActivities()
        }

        // Force widget refresh to reflect tier change
        // This ensures widgets update their UI immediately when subscription changes
        WidgetCenter.shared.reloadAllTimelines()
        debugLog("[Session] Triggered widget refresh after tier change (isPremium: \(isPremium))")
    }

    /// Check if a premium feature is available
    func canUse(feature: PremiumFeature) -> Bool {
        switch feature {
        case .moreContacts:
            return true  // Always allow, just enforce limit
        case .savedTrips:
            return featureLimits.savedTripsLimit > 0
        case .unlimitedHistory:
            return featureLimits.historyDays == nil
        case .allExtensions:
            return featureLimits.extensions.count > 1
        case .allStats:
            return featureLimits.visibleStats > 2
        case .widgets:
            return featureLimits.widgetsEnabled
        case .liveActivity:
            return featureLimits.liveActivityEnabled
        case .customIntervals:
            return featureLimits.customIntervalsEnabled
        case .tripMap:
            return featureLimits.tripMapEnabled
        case .pinnedActivities:
            return featureLimits.pinnedActivitiesLimit > 0
        case .groupTrips:
            return featureLimits.groupTripsEnabled
        case .contactGroups:
            return featureLimits.contactGroupsEnabled
        case .customMessages:
            return featureLimits.customMessagesEnabled
        case .export:
            return featureLimits.exportEnabled
        }
    }

    /// Apply debug subscription tier override (for developer testing)
    func applyDebugSubscriptionTier(_ tier: String) {
        if tier.isEmpty {
            // Reset to real subscription - reload from backend
            Task {
                await loadFeatureLimits()
            }
        } else if tier == "free" {
            featureLimits = .free
            subscriptionTier = "free"
            // Sync to shared defaults for widget access
            LiveActivityConstants.setWidgetsEnabled(false)
            // Apply tier restrictions
            applyTierRestrictions(isPremium: false)
        } else if tier == "plus" {
            featureLimits = .plus
            subscriptionTier = "plus"
            // Sync to shared defaults for widget access
            LiveActivityConstants.setWidgetsEnabled(true)
            // No restrictions for premium
        }
    }

    /// Check if user has reached contact limit for trips
    func isContactLimitReached(currentCount: Int) -> Bool {
        return currentCount >= featureLimits.contactsPerTrip
    }

    /// Check if an extension duration is allowed
    func isExtensionAllowed(minutes: Int) -> Bool {
        return featureLimits.extensions.contains(minutes)
    }

    /// Get available extension options
    func availableExtensions() -> [Int] {
        return featureLimits.extensions
    }

    /// Check if trip history date is within allowed range
    func isTripDateVisible(date: Date) -> Bool {
        guard let historyDays = featureLimits.historyDays else {
            return true  // Unlimited
        }

        let cutoff = Calendar.current.date(byAdding: .day, value: -historyDays, to: Date()) ?? Date()
        return date >= cutoff
    }

    /// Called by RealtimeManager when subscription state changes in database
    func handleSubscriptionChange() async {
        debugLog("[Session] Subscription change detected via Realtime")

        // Update StoreKit state first (local source of truth for entitlements)
        await SubscriptionManager.shared.updateSubscriptionStatus()

        // Then reload feature limits from backend (syncs with server state)
        await loadFeatureLimits()
    }

    /// Get subscription status from backend
    @MainActor
    func loadSubscriptionStatus() async -> SubscriptionStatusResponse? {
        guard let token = accessToken else { return nil }

        let url = baseURL.appendingPathComponent("/api/v1/subscriptions/status")

        do {
            let status: SubscriptionStatusResponse = try await api.get(url, bearer: token)
            debugLog("[Session] Subscription status: tier=\(status.tier), active=\(status.isActive)")
            return status
        } catch {
            debugLog("[Session] Failed to load subscription status: \(error)")
            return nil
        }
    }

    /// Get pinned activities
    @MainActor
    func loadPinnedActivities() async -> [PinnedActivity] {
        guard let token = accessToken else { return [] }

        let url = baseURL.appendingPathComponent("/api/v1/subscriptions/pinned-activities")

        do {
            let pinned: [PinnedActivity] = try await api.get(url, bearer: token)
            debugLog("[Session] Loaded \(pinned.count) pinned activities")
            return pinned
        } catch {
            debugLog("[Session] Failed to load pinned activities: \(error)")
            return []
        }
    }

    /// Pin an activity (premium feature)
    @MainActor
    func pinActivity(activityId: Int, position: Int) async -> Bool {
        guard let token = accessToken else { return false }

        let url = baseURL.appendingPathComponent("/api/v1/subscriptions/pinned-activities")

        struct PinRequest: Encodable {
            let activity_id: Int
            let position: Int
        }

        do {
            let _: PinnedActivity = try await api.post(
                url,
                body: PinRequest(activity_id: activityId, position: position),
                bearer: token
            )
            debugLog("[Session] Pinned activity \(activityId) at position \(position)")
            return true
        } catch {
            debugLog("[Session] Failed to pin activity: \(error)")
            return false
        }
    }

    /// Unpin an activity
    @MainActor
    func unpinActivity(activityId: Int) async -> Bool {
        guard let token = accessToken else { return false }

        let url = baseURL.appendingPathComponent("/api/v1/subscriptions/pinned-activities/\(activityId)")

        do {
            let _: GenericResponse = try await api.delete(url, bearer: token)
            debugLog("[Session] Unpinned activity \(activityId)")
            return true
        } catch {
            debugLog("[Session] Failed to unpin activity: \(error)")
            return false
        }
    }

    // MARK: - Sign Out
    @MainActor
    func signOut() {
        debugLog("[Session] 🔒 Signing out - clearing all data")

        // Cancel pending device registration retries
        deviceRegistrationTask?.cancel()
        deviceRegistrationTask = nil
        deviceRegistrationRetryCount = 0

        // End all Live Activities and stop Realtime subscriptions
        Task {
            await LiveActivityManager.shared.endAllActivities()
            await RealtimeManager.shared.stop()
        }

        // Clear keychain
        keychain.clearAll()

        // Clear local storage
        LocalStorage.shared.clearAll()

        // Clear session state
        accessToken = nil
        email = ""
        code = ""
        showCodeSheet = false
        isAuthenticated = false
        error = nil
        notice = ""
        lastError = ""
        userName = nil
        userAge = nil
        userEmail = nil
        profileCompleted = false
        activeTrip = nil
        activities = []
        contacts = []
        friends = []
        pendingInvites = []
        isInitialDataLoaded = false

        // Reset subscription state
        featureLimits = .free
        subscriptionTier = "free"

        debugLog("[Session] ✅ Sign out complete")
    }
}
