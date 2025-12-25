import Foundation
import Security

/// Thread-safe keychain helper using internal locking.
/// Uses NSLock to prevent race conditions during save operations.
final class KeychainHelper {
    static let shared = KeychainHelper()

    private let service = "com.hudsonschmidt.Homebound"
    private let accessTokenKey = "accessToken"
    private let refreshTokenKey = "refreshToken"
    private let userNameKey = "userName"
    private let userEmailKey = "userEmail"
    private let userAgeKey = "userAge"
    private let profileCompletedKey = "profileCompleted"

    /// Lock for thread-safe keychain operations
    private let lock = NSLock()

    private init() {}

    // MARK: - Save Methods

    func saveAccessToken(_ token: String) {
        save(token, for: accessTokenKey)
    }

    func saveRefreshToken(_ token: String) {
        save(token, for: refreshTokenKey)
    }

    func saveUserData(name: String?, email: String?, age: Int?, profileCompleted: Bool) {
        lock.lock()
        defer { lock.unlock() }

        if let name = name {
            saveUnlocked(name, for: userNameKey)
        }
        if let email = email {
            saveUnlocked(email, for: userEmailKey)
        }
        if let age = age {
            saveUnlocked("\(age)", for: userAgeKey)
        }
        saveUnlocked(profileCompleted ? "true" : "false", for: profileCompletedKey)
    }

    // MARK: - Load Methods

    func getAccessToken() -> String? {
        return load(for: accessTokenKey)
    }

    func getRefreshToken() -> String? {
        return load(for: refreshTokenKey)
    }

    func getUserName() -> String? {
        return load(for: userNameKey)
    }

    func getUserEmail() -> String? {
        return load(for: userEmailKey)
    }

    func getUserAge() -> Int? {
        guard let ageString = load(for: userAgeKey) else { return nil }
        return Int(ageString)
    }

    func getProfileCompleted() -> Bool {
        guard let value = load(for: profileCompletedKey) else { return false }
        return value == "true"
    }

    // MARK: - Clear All

    func clearAll() {
        lock.lock()
        defer { lock.unlock() }

        deleteUnlocked(for: accessTokenKey)
        deleteUnlocked(for: refreshTokenKey)
        deleteUnlocked(for: userNameKey)
        deleteUnlocked(for: userEmailKey)
        deleteUnlocked(for: userAgeKey)
        deleteUnlocked(for: profileCompletedKey)
    }

    // MARK: - Private Helper Methods (Thread-Safe)

    /// Save a value to the keychain with thread safety.
    /// Uses atomic update pattern with retry logic to handle race conditions.
    @discardableResult
    private func save(_ value: String, for key: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return saveUnlocked(value, for: key)
    }

    /// Internal save without locking - caller must hold lock
    @discardableResult
    private func saveUnlocked(_ value: String, for key: String) -> Bool {
        guard let data = value.data(using: .utf8) else {
            debugLog("[Keychain] Failed to encode value for key: \(key)")
            return false
        }

        // Query to find existing item
        let searchQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        // Attributes to update
        let updateAttributes: [String: Any] = [
            kSecValueData as String: data
        ]

        // Try to update existing item first (atomic operation)
        var status = SecItemUpdate(searchQuery as CFDictionary, updateAttributes as CFDictionary)

        if status == errSecItemNotFound {
            // Item doesn't exist, add it
            let addQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: key,
                kSecValueData as String: data
            ]
            status = SecItemAdd(addQuery as CFDictionary, nil)

            // Handle race condition: if another thread added the item between our
            // SecItemUpdate check and SecItemAdd, retry the update
            if status == errSecDuplicateItem {
                status = SecItemUpdate(searchQuery as CFDictionary, updateAttributes as CFDictionary)
            }
        }

        if status != errSecSuccess {
            debugLog("[Keychain] Error saving to keychain for key '\(key)': \(status)")
            return false
        }

        return true
    }

    private func load(for key: String) -> String? {
        lock.lock()
        defer { lock.unlock() }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var dataTypeRef: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &dataTypeRef)

        if status == errSecSuccess,
           let data = dataTypeRef as? Data,
           let value = String(data: data, encoding: .utf8) {
            return value
        }

        return nil
    }

    private func delete(for key: String) {
        lock.lock()
        defer { lock.unlock() }
        deleteUnlocked(for: key)
    }

    /// Internal delete without locking - caller must hold lock
    private func deleteUnlocked(for key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        SecItemDelete(query as CFDictionary)
    }
}
