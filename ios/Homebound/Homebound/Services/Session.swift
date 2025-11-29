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
    static let localURL = URL(string: "http://192.168.6.108:3001")!
    // static let localURL = URL(string: "http://Hudsons-MacBook-Pro-337.local:3001")!

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
                print("[Session] ✅ Access token saved to keychain and local storage")
            } else {
                print("[Session] ⚠️ Access token set to nil")
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

    // Activities
    @Published var activities: [Activity] = []
    @Published var isLoadingActivities: Bool = false

    init() {
        // Load saved tokens and user data on init
        loadFromKeychain()

        // Load activities on app launch
        Task {
            await loadActivities()
        }
    }

    private func loadFromKeychain() {
        // Try loading from keychain first
        accessToken = keychain.getAccessToken()

        // If keychain fails, try LocalStorage as backup
        if accessToken == nil {
            let tokens = LocalStorage.shared.getAuthTokens()
            if let access = tokens.access {
                print("[Session] ℹ️ Loaded access token from LocalStorage backup")
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
            print("[Session] ✅ Loaded auth token - user authenticated")
        } else {
            print("[Session] ℹ️ No auth token found - user not authenticated")
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

        // Register device token with backend once signed-in.
        guard let bearer = self.accessToken else { return }
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
            } catch {
                // Non-fatal; just surface a notice in your dev UI.
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
                print("[Session] ✅ Refresh token saved to keychain and local storage")
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
                print("[Session] ⚠️  Account exists with email \(resp.email) - prompting for linking")
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
            print("[Session] ✅ Apple Sign In successful")

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

            print("[Session] ✅ Apple account linked successfully")

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
                print("[Session] ℹ️ Using refresh token from LocalStorage backup")
            }
        }

        guard let refreshToken = refreshToken else {
            print("[Session] ❌ No refresh token available - user needs to re-authenticate")
            // No refresh token available, user needs to re-authenticate
            isAuthenticated = false
            accessToken = nil
            return false
        }

        print("[Session] ℹ️ Attempting to refresh access token...")

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
                print("[Session] ✅ Token refreshed successfully - saved to keychain and local storage")
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

            print("[Session] ✅ Access token refresh successful")
            return true
        } catch {
            print("[Session] ❌ Token refresh failed: \(error)")
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
            print("[Session] ❌ No access token available - unauthorized")
            throw API.APIError.unauthorized
        }

        do {
            return try await operation(bearer)
        } catch API.APIError.unauthorized {
            print("[Session] ⚠️ Got 401 Unauthorized - attempting token refresh...")

            // Try to refresh the token
            let refreshed = await refreshAccessToken()
            guard refreshed, let newBearer = accessToken else {
                print("[Session] ❌ Token refresh failed - user needs to re-authenticate")
                throw API.APIError.unauthorized
            }

            print("[Session] ✅ Token refreshed - retrying request with new token")
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
    private func syncPendingActions() async {
        let pendingActions = LocalStorage.shared.getPendingActions()

        for action in pendingActions {
            do {
                switch action.type {
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
                    }
                default:
                    break
                }

                // Remove successfully synced action
                LocalStorage.shared.removePendingAction(id: action.id)
            } catch {
                // Keep action in queue for next sync attempt
                print("[Session] Failed to sync action \(action.type): \(error)")
            }
        }
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
            await MainActor.run {
                self.lastError = "Failed to check in: \(error.localizedDescription)"
            }
            return false
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
            await MainActor.run {
                self.lastError = "Failed to complete plan: \(error.localizedDescription)"
            }
            return false
        }
    }

    func extendPlan(minutes: Int = 30) async -> Bool {
        guard let plan = activeTrip else {
            await MainActor.run {
                self.lastError = "No active plan to extend"
            }
            return false
        }

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
            await MainActor.run {
                self.lastError = "Failed to extend plan: \(error.localizedDescription)"
            }
            return false
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
            await MainActor.run {
                self.lastError = "Failed to start trip: \(error.localizedDescription)"
            }
            return false
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
            await MainActor.run {
                self.lastError = "Failed to delete trip: \(error.localizedDescription)"
            }
            return false
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
            print("Failed to load user profile: \(error.localizedDescription)")
        }
    }

    // MARK: - Saved Contacts Management
    func loadContacts() async -> [Contact] {
        do {
            let contacts: [Contact] = try await withAuth { bearer in
                try await self.api.get(
                    self.url("/api/v1/contacts/"),
                    bearer: bearer
                )
            }
            return contacts
        } catch {
            print("Failed to load saved contacts: \(error.localizedDescription)")
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
            return response
        } catch {
            await MainActor.run {
                self.lastError = "Failed to add contact: \(error.localizedDescription)"
            }
            return nil
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
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to update contact: \(error.localizedDescription)"
            }
            return false
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
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to delete contact: \(error.localizedDescription)"
            }
            return false
        }
    }

    // MARK: - Activities Management
    @MainActor
    func loadActivities() async {
        print("[Session] 🔄 Loading activities from backend...")
        do {
            let response: [Activity] = try await api.get(
                url("/api/v1/activities/"),
                bearer: nil  // Activities endpoint doesn't require auth
            )

            await MainActor.run {
                self.activities = response.sorted { $0.order < $1.order }
                print("[Session] ✅ Loaded \(response.count) activities from backend")

                // Cache for offline access
                LocalStorage.shared.cacheActivities(response)
                print("[Session] 💾 Activities cached to local storage")
            }
        } catch {
            print("[Session] ❌ Failed to load activities from backend: \(error)")

            // Fall back to cached activities on error
            let cachedActivities = LocalStorage.shared.getCachedActivities()
            await MainActor.run {
                if !cachedActivities.isEmpty {
                    self.activities = cachedActivities
                    self.notice = "Showing cached activities (offline mode)"
                    print("[Session] 📦 Using \(cachedActivities.count) cached activities")
                } else {
                    // No activities available - user needs internet connection
                    self.activities = []
                    self.lastError = "Unable to load activities. Please check your internet connection."
                    print("[Session] ❌ No activities available (no backend or cache)")
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
        print("[Session] 🔒 Signing out - clearing all data")

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

        print("[Session] ✅ Sign out complete")
    }
}
