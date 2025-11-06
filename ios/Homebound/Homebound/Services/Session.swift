import Foundation
import Combine

/// Routes: adjust these to match your backend if different.
private enum Routes {
    static let sendCode  = "/api/v1/auth/request-magic-link"
    static let verify    = "/api/v1/auth/verify"
    // add more here as you build out
}

// MARK: - DTOs (keep fields optional to be decoding-tolerant)

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
        let name: String?
        let age: Int?
        let phone: String?
        let profile_completed: Bool?
    }
}

private struct GenericResponse: Decodable {
    let ok: Bool?
    let message: String?
}

private struct EmptyBody: Encodable {}

final class Session: ObservableObject {

    // MARK: API & Base URL

    static let baseURL = URL(string: "https://homebound.onrender.com")!
    var baseURL: URL { Self.baseURL }

    /// Use your real API client from `API.swift`
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
            // Save to keychain when set
            if let token = accessToken {
                keychain.saveAccessToken(token)
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

    // Active plan
    @Published var activePlan: PlanOut? = nil
    @Published var isLoadingPlan: Bool = false

    init() {
        // Load saved tokens and user data on init
        loadFromKeychain()
    }

    private func loadFromKeychain() {
        accessToken = keychain.getAccessToken()
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
        return Self.baseURL.appending(path: path)
    }

    // MARK: Auth flows
    @MainActor
    func handleAPNsToken(_ token: String) {
        self.apnsToken = token

        // Optional: register device token with your backend once signed-in.
        guard let bearer = self.accessToken else { return }
        struct RegisterReq: Encodable { let apns_token: String }
        Task {
            do {
                try await api.post(
                    url("/api/v1/devices/apns"),
                    body: RegisterReq(apns_token: token),
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

            // Store user profile data
            if let user = resp.user {
                userName = user.name
                userAge = user.age
                userEmail = user.email ?? email
                profileCompleted = user.profile_completed ?? false
            } else {
                userEmail = email
                profileCompleted = false
            }

            isAuthenticated = true
            showCodeSheet = false
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
                url("/api/v1/auth/_dev/peek-code?email=\(email)"),
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
    func createPlan(_ plan: PlanCreate) async -> PlanOut? {
        guard let bearer = accessToken else { return nil }

        do {
            let response: PlanOut = try await api.post(
                url("/api/v1/trips/"),
                body: plan,
                bearer: bearer
            )

            // After creating a plan, immediately set it as active
            await MainActor.run {
                self.activePlan = response
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
        guard let bearer = accessToken else { return }

        await MainActor.run {
            self.isLoadingPlan = true
        }

        do {
            let response: PlanOut? = try await api.get(
                url("/api/v1/trips/active"),
                bearer: bearer
            )

            await MainActor.run {
                self.activePlan = response
                self.isLoadingPlan = false
            }
        } catch {
            // If active plan endpoint fails, just set to nil
            // Don't auto-signout - tokens last 30 days and user should stay signed in
            await MainActor.run {
                self.activePlan = nil
                self.isLoadingPlan = false
            }
        }
    }

    func checkIn() async -> Bool {
        guard let plan = activePlan else { return false }

        do {
            // Use token-based checkin endpoint (no auth required)
            let _: GenericResponse = try await api.get(
                url("/t/\(plan.checkin_token)/checkin"),
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
        guard let bearer = accessToken, let plan = activePlan else { return false }

        do {
            let _: GenericResponse = try await api.post(
                url("/api/v1/trips/\(plan.id)/complete"),
                body: EmptyBody(),
                bearer: bearer
            )

            await MainActor.run {
                self.activePlan = nil
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

    // NOTE: Backend does not currently have an extend endpoint
    // This functionality may need to be implemented in the backend first
    func extendPlan(minutes: Int = 30) async -> Bool {
        await MainActor.run {
            self.lastError = "Extend functionality is not yet available"
        }
        return false
    }

    func loadTimeline(planId: Int) async -> [TimelineEvent] {
        guard let bearer = accessToken else { return [] }

        do {
            let response: TimelineResponse = try await api.get(
                url("/api/v1/trips/\(planId)/timeline"),
                bearer: bearer
            )
            return response.events
        } catch {
            await MainActor.run {
                self.lastError = "Failed to load timeline: \(error.localizedDescription)"
            }
            return []
        }
    }

    // MARK: - Profile Management
    func updateProfile(firstName: String, lastName: String, age: Int) async -> Bool {
        guard let bearer = accessToken else { return false }

        struct ProfileUpdateRequest: Encodable {
            let first_name: String
            let last_name: String
            let age: Int
        }

        struct ProfileUpdateResponse: Decodable {
            let ok: Bool
            let user: UserInfo?

            struct UserInfo: Decodable {
                let first_name: String?
                let last_name: String?
                let age: Int?
                let profile_completed: Bool?
            }
        }

        do {
            let response: ProfileUpdateResponse = try await api.put(
                url("/api/v1/profile"),
                body: ProfileUpdateRequest(first_name: firstName, last_name: lastName, age: age),
                bearer: bearer
            )

            if response.ok, let user = response.user {
                await MainActor.run {
                    if let first = user.first_name, let last = user.last_name {
                        self.userName = "\(first) \(last)"
                    }
                    self.userAge = user.age
                    self.profileCompleted = user.profile_completed ?? true
                }
                return true
            }
            return false
        } catch {
            await MainActor.run {
                self.lastError = "Failed to update profile: \(error.localizedDescription)"
            }
            return false
        }
    }

    // MARK: - Update Profile
    func updateProfile(firstName: String? = nil, lastName: String? = nil, age: Int? = nil, phone: String? = nil) async -> Bool {
        guard let bearer = accessToken else { return false }

        struct UpdateProfileRequest: Encodable {
            let first_name: String?
            let last_name: String?
            let age: Int?
            let phone: String?
        }

        do {
            let _: GenericResponse = try await api.patch(
                url("/api/v1/profile"),
                body: UpdateProfileRequest(first_name: firstName, last_name: lastName, age: age, phone: phone),
                bearer: bearer
            )

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
        guard let bearer = accessToken else { return false }

        do {
            let _: GenericResponse = try await api.delete(
                url("/api/v1/profile/account"),
                bearer: bearer
            )

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
        guard let bearer = accessToken else { return false }

        do {
            let _: GenericResponse = try await api.delete(
                url("/api/v1/trips/\(planId)"),
                bearer: bearer
            )

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
        guard let bearer = accessToken else { return }

        struct UserProfileResponse: Decodable {
            let id: Int?
            let email: String?
            let first_name: String?
            let last_name: String?
            let age: Int?
            let profile_completed: Bool?
        }

        do {
            let response: UserProfileResponse = try await api.get(
                url("/api/v1/profile"),
                bearer: bearer
            )

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
    func loadSavedContacts() async -> [SavedContact] {
        guard let bearer = accessToken else { return [] }

        do {
            let contacts: [SavedContact] = try await api.get(
                url("/api/v1/contacts/"),
                bearer: bearer
            )
            return contacts
        } catch {
            print("Failed to load saved contacts: \(error.localizedDescription)")
            return []
        }
    }

    func addSavedContact(_ contact: SavedContact) async -> SavedContact? {
        print("DEBUG Session: addSavedContact called")
        print("DEBUG Session: Contact to add: \(contact)")

        guard let bearer = accessToken else {
            print("DEBUG Session: No access token available")
            await MainActor.run {
                self.lastError = "Not authenticated. Please sign in again."
            }
            return nil
        }

        print("DEBUG Session: Access token exists")

        struct AddContactRequest: Encodable {
            let name: String
            let phone: String
            let email: String?
        }

        let requestBody = AddContactRequest(
            name: contact.name,
            phone: contact.phone,
            email: contact.email
        )

        print("DEBUG Session: Request body: \(requestBody)")
        print("DEBUG Session: URL: \(url("/api/v1/contacts/"))")

        do {
            print("DEBUG Session: Making API call...")
            let response: SavedContact = try await api.post(
                url("/api/v1/contacts/"),
                body: requestBody,
                bearer: bearer
            )
            print("DEBUG Session: API call successful. Response: \(response)")
            // Return the saved contact from the server (with server-generated ID)
            return response
        } catch {
            print("DEBUG Session: API call failed - Error: \(error)")
            await MainActor.run {
                self.lastError = "Failed to add contact: \(error.localizedDescription)"
            }
            return nil
        }
    }

    func deleteSavedContact(_ contactId: String) async -> Bool {
        guard let bearer = accessToken else { return false }

        do {
            let _: GenericResponse = try await api.delete(
                url("/api/v1/contacts/\(contactId)"),
                bearer: bearer
            )
            return true
        } catch {
            await MainActor.run {
                self.lastError = "Failed to delete contact: \(error.localizedDescription)"
            }
            return false
        }
    }

    // MARK: - Sign Out
    @MainActor
    func signOut() {
        // Clear keychain
        keychain.clearAll()

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
        activePlan = nil
    }
}
