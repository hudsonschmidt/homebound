import Foundation
import Combine

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
        let phone: String?
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
        let phone: String?
        let profile_completed: Bool?
    }
}
final class Session: ObservableObject {

    // MARK: API & Base URL

    static let productionURL = URL(string: "https://api.homeboundapp.com")!
    static let localURL = URL(string: "http://Hudsons-MacBook-Pro-337.local:3001")!

    @Published var useLocalServer: Bool = UserDefaults.standard.bool(forKey: "useLocalServer") {
        didSet {
            // When switching databases, sign out and clear all cached data
            // This prevents data mismatch between local and production databases
            if oldValue != useLocalServer {
                signOut()
            }
            UserDefaults.standard.set(useLocalServer, forKey: "useLocalServer")
        }
    }

    var baseURL: URL {
        useLocalServer ? Self.localURL : Self.productionURL
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
    @Published var accessToken: String? = nil {
        didSet {
            // Save to both keychain and local storage for redundancy
            if let token = accessToken {
                keychain.saveAccessToken(token)
                // Also save to local storage as backup
                let refreshToken = keychain.getRefreshToken()
                LocalStorage.shared.saveAuthTokens(access: token, refresh: refreshToken)
                debugLog("[Session] ✅ Access token saved to keychain and local storage")

                // Register pending APNs token if we have one
                if let apns = apnsToken {
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
    @Published var userPhone: String? = nil {
        didSet {
            saveUserDataToKeychain()
        }
    }
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
    @Published var isLoadingTrip: Bool = false

    // Offline state
    @Published var isOffline: Bool = false
    @Published var pendingActionsCount: Int = 0

    // Activities
    @Published var activities: [Activity] = []
    @Published var isLoadingActivities: Bool = false

    // Contacts
    @Published var contacts: [Contact] = []

    // Initial data loading state
    @Published var isInitialDataLoaded: Bool = false

    private var networkObserver: NSObjectProtocol?
    private var backgroundSyncObserver: NSObjectProtocol?

    init() {
        // Load saved tokens and user data on init
        loadFromKeychain()

        // Initialize pending actions count
        pendingActionsCount = LocalStorage.shared.getPendingActionsCount()

        // Set up network monitoring
        setupNetworkMonitoring()

        // Set up background sync observer
        setupBackgroundSyncObserver()

        // Load activities on app launch
        Task {
            await loadActivities()
        }
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

        // Set initial offline state
        isOffline = !NetworkMonitor.shared.isConnected
    }

    private func setupBackgroundSyncObserver() {
        // Observe background sync requests
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

        userName = keychain.getUserName()
        userEmail = keychain.getUserEmail()
        userAge = keychain.getUserAge()

        // Profile is completed if we have a name stored
        // This ensures existing users don't see onboarding again
        if userName != nil && !userName!.isEmpty {
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
            name: userName,
            email: userEmail,
            age: userAge,
            profileCompleted: profileCompleted
        )
    }

    // MARK: URL helper

    func url(_ path: String) -> URL {
        if let u = URL(string: path), u.scheme != nil { return u }
        return baseURL.appending(path: path)
    }

    // MARK: Auth flows
    @MainActor
    func handleAPNsToken(_ token: String) {
        self.apnsToken = token
        debugLog("[APNs] Received token: \(token.prefix(20))...")

        // Register device token with backend once signed-in.
        guard let bearer = self.accessToken else {
            debugLog("[APNs] Not signed in, will register later")
            return
        }
        debugLog("[APNs] Registering device with backend...")
        struct DeviceRegister: Encodable {
            let platform: String
            let token: String
            let bundle_id: String
            let env: String
        }
        Task {
            do {
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
            } catch {
                // Non-fatal; just surface a notice in your dev UI.
                debugLog("[APNs] ❌ Registration failed: \(error.localizedDescription)")
                await MainActor.run { self.notice = "APNs register failed: \(error.localizedDescription)" }
            }
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
    func verifyMagic(code: String, email: String) async {
        await MainActor.run {
            self.email = email
            self.code = code
        }
        await MainActor.run { self.error = nil }
        await MainActor.run { self.isVerifying = true }
        defer { Task { await MainActor.run { self.isVerifying = false } } }
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
    @MainActor
    func refreshAccessToken() async -> Bool {
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

            // Update access token
            if let t = resp.access ?? resp.access_token {
                accessToken = t
            }

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

    // MARK: - Dev helpers

    /// Dev-only: peek the current magic code for an email
    @MainActor
    func devPeekCode(email: String) async -> String? {
        struct PeekResponse: Decodable {
            let email: String?
            let code: String?
            let expires_at: String?
        }

        do {
            let response: PeekResponse = try await api.get(
                url("/api/v1/auth/_dev/peek-code/?email=\(email)"),
                bearer: nil
            )
            return response.code
        } catch {
            await MainActor.run { self.notice = "Peek failed: \(error.localizedDescription)" }
            return nil
        }
    }

    /// Ping the /health endpoint
    @MainActor
    func ping() async {
        struct HealthResponse: Decodable {
            let ok: Bool
        }

        do {
            let response: HealthResponse = try await api.get(
                url("/health"),
                bearer: nil
            )
            await MainActor.run {
                self.notice = response.ok ? "✅ Health check OK" : "⚠️ Health check failed"
            }
        } catch {
            await MainActor.run {
                self.notice = "❌ Health check failed: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Token Actions
    func performTokenAction(_ token: String, action: String) async {
        struct TokenResponse: Decodable { let ok: Bool }

        do {
            let _: TokenResponse = try await api.get(
                url("/t/\(token)/\(action)"),
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

            // Only set as active plan if the status is actually 'active'
            // Planned trips should not appear as active
            await MainActor.run {
                if response.status == "active" {
                    self.activeTrip = response
                }
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

            // Update local cache with changes
            var cacheUpdates: [String: Any] = [:]
            if let eta = updates.eta { cacheUpdates["eta"] = eta }
            if !cacheUpdates.isEmpty {
                LocalStorage.shared.updateCachedTripFields(tripId: tripId, updates: cacheUpdates)
            }

            await MainActor.run {
                self.notice = "Trip updated (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Update trip queued for offline sync")

            // Return nil but UI should handle gracefully since action is queued
            return nil
        }
    }

    /// Load all initial data needed before showing the main app
    func loadInitialData() async {
        // Load activities, active trip, profile, and contacts in parallel
        async let activitiesTask: Void = loadActivities()
        async let activePlanTask: Void = loadActivePlan()
        async let profileTask: Void = loadUserProfile()
        async let contactsTask: [Contact] = loadContacts()

        // Wait for all to complete
        _ = await (activitiesTask, activePlanTask, profileTask, contactsTask)

        await MainActor.run {
            isInitialDataLoaded = true
        }
    }

    func loadActivePlan() async {
        await MainActor.run {
            self.isLoadingTrip = true
        }

        do {
            let response: Trip? = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/active"),
                    bearer: bearer
                )
            }

            await MainActor.run {
                self.activeTrip = response
                self.isLoadingTrip = false

                // Cache the active plan for offline access
                if let plan = response {
                    LocalStorage.shared.cacheTrip(plan)
                }
            }
        } catch {
            // If active plan endpoint fails, try to load from cache
            // Don't auto-signout - tokens last 30 days and user should stay signed in
            await MainActor.run {
                // Try to load active plan from cache
                let cachedTrips = LocalStorage.shared.getCachedTrips()
                self.activeTrip = cachedTrips.first { $0.status == "active" }
                self.isLoadingTrip = false

                if self.activeTrip != nil {
                    self.notice = "Loaded from cache (offline mode)"
                }
            }
        }
    }

    /// Load all trips with caching for offline access
    func loadAllTrips() async -> [Trip] {
        do {
            let trips: [Trip] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/"),
                    bearer: bearer
                )
            }

            // Cache trips for offline access (keeps last 5)
            LocalStorage.shared.cacheTrips(trips)

            // Sync any pending offline actions
            await syncPendingActions()

            return trips
        } catch {
            // Return cached trips when offline
            let cachedTrips = LocalStorage.shared.getCachedTrips()
            if !cachedTrips.isEmpty {
                await MainActor.run {
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

        for action in pendingActions {
            do {
                switch action.type {
                case "checkin":
                    // Use token-based checkin endpoint (no auth required)
                    if let token = action.payload["token"] as? String {
                        let _: GenericResponse = try await api.get(
                            url("/t/\(token)/checkin"),
                            bearer: nil
                        )
                        debugLog("[Session] ✅ Synced checkin action")
                    }
                case "extend":
                    if let tripId = action.tripId,
                       let minutes = action.payload["minutes"] as? Int {
                        // Construct URL with query parameters properly
                        var urlComponents = URLComponents(url: url("/api/v1/trips/\(tripId)/extend"), resolvingAgainstBaseURL: false)!
                        urlComponents.queryItems = [URLQueryItem(name: "minutes", value: String(minutes))]

                        let _: GenericResponse = try await withAuth { bearer in
                            try await self.api.post(
                                urlComponents.url!,
                                body: API.Empty(),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced extend action for trip #\(tripId)")
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
                    }

                case "update_trip":
                    if let tripId = action.tripId {
                        // Reconstruct TripUpdateRequest from payload
                        var updates = TripUpdateRequest()
                        if let title = action.payload["title"] as? String { updates.title = title }
                        if let activity = action.payload["activity"] as? String { updates.activity = activity }
                        if let startStr = action.payload["start"] as? String,
                           let start = ISO8601DateFormatter().date(from: startStr) { updates.start = start }
                        if let etaStr = action.payload["eta"] as? String,
                           let eta = ISO8601DateFormatter().date(from: etaStr) { updates.eta = eta }
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
                    }

                case "start_trip":
                    if let tripId = action.tripId {
                        let _: Trip = try await withAuth { bearer in
                            try await self.api.post(
                                self.url("/api/v1/trips/\(tripId)/start"),
                                body: API.Empty(),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced start_trip action for trip #\(tripId)")
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
                    }

                case "add_contact":
                    if let name = action.payload["name"] as? String,
                       let email = action.payload["email"] as? String {
                        struct ContactCreate: Codable { let name: String; let email: String }
                        let _: Contact = try await withAuth { bearer in
                            try await self.api.post(
                                self.url("/api/v1/contacts/"),
                                body: ContactCreate(name: name, email: email),
                                bearer: bearer
                            )
                        }
                        debugLog("[Session] ✅ Synced add_contact action")
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
                    }

                default:
                    debugLog("[Session] ⚠️ Unknown action type: \(action.type)")
                }

                // Remove successfully synced action
                LocalStorage.shared.removePendingAction(id: action.id)
            } catch {
                // Keep action in queue for next sync attempt
                debugLog("[Session] ❌ Failed to sync action \(action.type): \(error)")
            }
        }

        // Update pending count after sync
        await MainActor.run {
            self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
        }

        // Refresh active plan data after sync
        await loadActivePlan()
    }

    func checkIn() async -> Bool {
        guard let plan = activeTrip,
              let token = plan.checkin_token else { return false }

        do {
            // Use token-based checkin endpoint (no auth required)
            let _: GenericResponse = try await api.get(
                url("/t/\(token)/checkin"),
                bearer: nil
            )

            await MainActor.run {
                self.notice = "Checked in successfully!"
            }
            return true
        } catch {
            // Queue for later sync when offline
            let timestamp = ISO8601DateFormatter().string(from: Date())
            LocalStorage.shared.queuePendingAction(
                type: "checkin",
                tripId: plan.id,
                payload: ["token": token, "timestamp": timestamp]
            )

            // Update local cache with check-in timestamp
            LocalStorage.shared.updateCachedTripFields(
                tripId: plan.id,
                updates: ["last_checkin": timestamp]
            )

            await MainActor.run {
                self.notice = "Check-in saved (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Check-in queued for offline sync")
            return true // Return true since action is queued, not failed
        }
    }

    func completePlan() async -> Bool {
        guard let plan = activeTrip else { return false }

        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(plan.id)/complete"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            await MainActor.run {
                self.activeTrip = nil
                self.notice = "Welcome back! Trip completed safely."
            }

            // Reload to check for any other active plans
            await loadActivePlan()

            return true
        } catch {
            // Queue for later sync when offline
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

            await MainActor.run {
                self.activeTrip = nil
                self.notice = "Trip completed (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Complete trip queued for offline sync")
            return true // Return true since action is queued, not failed
        }
    }

    func extendPlan(minutes: Int = 30) async -> Bool {
        guard let plan = activeTrip else {
            await MainActor.run {
                self.lastError = "No active plan to extend"
            }
            return false
        }

        // Calculate new ETA locally for offline update
        let newETA = plan.eta_at.addingTimeInterval(Double(minutes) * 60)
        let newETAString = ISO8601DateFormatter().string(from: newETA)

        do {
            struct ExtendResponse: Decodable {
                let ok: Bool
                let message: String
                let new_eta: String
            }

            // Construct URL with query parameters properly
            var urlComponents = URLComponents(url: url("/api/v1/trips/\(plan.id)/extend"), resolvingAgainstBaseURL: false)!
            urlComponents.queryItems = [URLQueryItem(name: "minutes", value: String(minutes))]

            let _: ExtendResponse = try await withAuth { bearer in
                try await self.api.post(
                    urlComponents.url!,
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Reload the active plan to get updated data
            await loadActivePlan()

            await MainActor.run {
                self.notice = "Trip extended by \(minutes) minutes"
            }
            return true
        } catch {
            // Queue for later sync when offline
            LocalStorage.shared.queuePendingAction(
                type: "extend",
                tripId: plan.id,
                payload: ["minutes": minutes, "new_eta": newETAString]
            )

            // Update local cache with new ETA
            LocalStorage.shared.updateCachedTripFields(
                tripId: plan.id,
                updates: ["eta": newETAString]
            )

            // Update in-memory active trip
            await MainActor.run {
                if var updatedTrip = self.activeTrip {
                    updatedTrip = Trip(
                        id: updatedTrip.id,
                        user_id: updatedTrip.user_id,
                        title: updatedTrip.title,
                        activity: updatedTrip.activity,
                        start_at: updatedTrip.start_at,
                        eta_at: newETA,
                        grace_minutes: updatedTrip.grace_minutes,
                        location_text: updatedTrip.location_text,
                        location_lat: updatedTrip.location_lat,
                        location_lng: updatedTrip.location_lng,
                        notes: updatedTrip.notes,
                        status: updatedTrip.status,
                        completed_at: updatedTrip.completed_at,
                        last_checkin: updatedTrip.last_checkin,
                        created_at: updatedTrip.created_at,
                        contact1: updatedTrip.contact1,
                        contact2: updatedTrip.contact2,
                        contact3: updatedTrip.contact3,
                        checkin_token: updatedTrip.checkin_token,
                        checkout_token: updatedTrip.checkout_token
                    )
                    self.activeTrip = updatedTrip
                }
                self.notice = "Trip extended (will sync when online)"
                self.pendingActionsCount = LocalStorage.shared.getPendingActionsCount()
            }

            debugLog("[Session] ℹ️ Extend trip queued for offline sync")
            return true // Return true since action is queued, not failed
        }
    }

    /// Start a planned trip (change status from 'planned' to 'active')
    func startTrip(_ tripId: Int) async -> Bool {
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.post(
                    self.url("/api/v1/trips/\(tripId)/start"),
                    body: API.Empty(),
                    bearer: bearer
                )
            }

            // Reload active plan to update UI
            await loadActivePlan()

            await MainActor.run {
                self.notice = "Trip started!"
            }
            return true
        } catch {
            // Queue for later sync when offline
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
                    self.activeTrip = Trip(
                        id: trip.id,
                        user_id: trip.user_id,
                        title: trip.title,
                        activity: trip.activity,
                        start_at: trip.start_at,
                        eta_at: trip.eta_at,
                        grace_minutes: trip.grace_minutes,
                        location_text: trip.location_text,
                        location_lat: trip.location_lat,
                        location_lng: trip.location_lng,
                        notes: trip.notes,
                        status: "active",
                        completed_at: trip.completed_at,
                        last_checkin: trip.last_checkin,
                        created_at: trip.created_at,
                        contact1: trip.contact1,
                        contact2: trip.contact2,
                        contact3: trip.contact3,
                        checkin_token: trip.checkin_token,
                        checkout_token: trip.checkout_token
                    )
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
    }

    func loadTimeline(planId: Int) async -> [TimelineEvent] {
        do {
            let response: TimelineResponse = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/trips/\(planId)/timeline"),
                    bearer: bearer
                )
            }
            return response.events
        } catch {
            await MainActor.run {
                self.lastError = "Failed to load timeline: \(error.localizedDescription)"
            }
            return []
        }
    }

    // MARK: - Profile Management
    func updateProfile(firstName: String? = nil, lastName: String? = nil, age: Int? = nil, phone: String? = nil) async -> Bool {
        struct UpdateProfileRequest: Encodable {
            let first_name: String?
            let last_name: String?
            let age: Int?
            let phone: String?
        }

        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.patch(
                    self.url("/api/v1/profile"),
                    body: UpdateProfileRequest(first_name: firstName, last_name: lastName, age: age, phone: phone),
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
                if let phone = phone {
                    self.userPhone = phone
                }
                self.notice = "Profile updated successfully"
            }
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to update profile: \(error.localizedDescription)"
            }
            return false
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
        do {
            let _: GenericResponse = try await withAuth { bearer in
                try await self.api.delete(
                    self.url("/api/v1/trips/\(planId)"),
                    bearer: bearer
                )
            }

            await MainActor.run {
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

            await MainActor.run {
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
        }

        do {
            let response: UserProfileResponse = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/profile"),
                    bearer: bearer
                )
            }

            await MainActor.run {
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
    func loadContacts() async -> [Contact] {
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
            let cachedContacts = LocalStorage.shared.getCachedContacts()
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
            // Queue for later sync when offline
            LocalStorage.shared.queuePendingAction(
                type: "add_contact",
                tripId: nil,
                payload: ["name": name, "email": email]
            )

            // Create a temporary contact with a negative ID for local use
            let tempId = -Int(Date().timeIntervalSince1970)
            let tempContact = Contact(id: tempId, name: name, email: email)

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
                    self.contacts[index] = Contact(id: contactId, name: name, email: email)
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

    // MARK: - Activities Management
    @MainActor
    func loadActivities() async {
        debugLog("[Session] 🔄 Loading activities from backend...")
        do {
            let response: [Activity] = try await api.get(
                url("/api/v1/activities/"),
                bearer: nil  // Activities endpoint doesn't require auth
            )

            await MainActor.run {
                self.activities = response.sorted { $0.order < $1.order }
                debugLog("[Session] ✅ Loaded \(response.count) activities from backend")

                // Cache for offline access
                LocalStorage.shared.cacheActivities(response)
                debugLog("[Session] 💾 Activities cached to local storage")
            }
        } catch {
            debugLog("[Session] ❌ Failed to load activities from backend: \(error)")

            // Fall back to cached activities on error
            let cachedActivities = LocalStorage.shared.getCachedActivities()
            await MainActor.run {
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
    }

    @MainActor
    func refreshActivities() async {
        isLoadingActivities = true
        await loadActivities()
        isLoadingActivities = false
    }

    // MARK: - Sign Out
    @MainActor
    func signOut() {
        debugLog("[Session] 🔒 Signing out - clearing all data")

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
        userPhone = nil
        profileCompleted = false
        activeTrip = nil
        activities = []
        contacts = []
        isInitialDataLoaded = false

        debugLog("[Session] ✅ Sign out complete")
    }
}
