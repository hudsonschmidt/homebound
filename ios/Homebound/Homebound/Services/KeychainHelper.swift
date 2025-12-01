import Foundation
import Security

class KeychainHelper {
    static let shared = KeychainHelper()

    private let service = "com.hudsonschmidt.Homebound"
    private let accessTokenKey = "accessToken"
    private let refreshTokenKey = "refreshToken"
    private let userNameKey = "userName"
    private let userEmailKey = "userEmail"
    private let userAgeKey = "userAge"
    private let profileCompletedKey = "profileCompleted"

    private init() {}

    // MARK: - Save Methods

    func saveAccessToken(_ token: String) {
        save(token, for: accessTokenKey)
    }

    func saveRefreshToken(_ token: String) {
        save(token, for: refreshTokenKey)
    }

    func saveUserData(name: String?, email: String?, age: Int?, profileCompleted: Bool) {
        if let name = name {
            save(name, for: userNameKey)
        }
        if let email = email {
            save(email, for: userEmailKey)
        }
        if let age = age {
            save("\(age)", for: userAgeKey)
        }
        save(profileCompleted ? "true" : "false", for: profileCompletedKey)
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
        delete(for: accessTokenKey)
        delete(for: refreshTokenKey)
        delete(for: userNameKey)
        delete(for: userEmailKey)
        delete(for: userAgeKey)
        delete(for: profileCompletedKey)
    }

    // MARK: - Private Helper Methods

    private func save(_ value: String, for key: String) {
        let data = value.data(using: .utf8)!

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data
        ]

        // Delete any existing item
        SecItemDelete(query as CFDictionary)

        // Add new item
        let status = SecItemAdd(query as CFDictionary, nil)

        if status != errSecSuccess {
            debugLog("Error saving to keychain: \(status)")
        }
    }

    private func load(for key: String) -> String? {
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
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        SecItemDelete(query as CFDictionary)
    }
}