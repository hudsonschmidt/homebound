import Foundation
import SwiftUI
import Combine

@MainActor
final class Session: ObservableObject {
    @Published var accessToken: String? {
        didSet { if accessToken != nil { Task { await registerPendingDeviceTokenIfAny() } } }
    }

    // TEMP for Debug: hardcode the Mac IP that worked in Safari
    @Published var baseURL: URL = URL(string: "https://homebound.onrender.com")!

    @Published var notice: String?

    private var pendingAPNsToken: String?
    let api = API()

    // --- URL join helper (prevents / being %2F-encoded) ---
    func url(_ path: String) -> URL {
        var base = baseURL.absoluteString
        if base.hasSuffix("/") { base.removeLast() }
        let suffix = path.hasPrefix("/") ? path : "/\(path)"
        // Force-unwrap is fine here during dev; crash surfaces misconfig early.
        return URL(string: base + suffix)!
    }

    // MARK: - Auth (dev)
    func requestMagicLink(email: String) async throws {
        try await api.post(url("/api/v1/auth/request-magic-link"),
                           body: ["email": email], bearer: Optional<String>.none)
        notice = "Link requested (see server log for 6-digit code)"
    }

    func verifyMagic(code: String, email: String) async throws {
        struct VerifyResp: Decodable { let access: String; let refresh: String }
        let r: VerifyResp = try await api.post(
            url("/api/v1/auth/verify"),
            body: ["email": email, "code": code],
            bearer: Optional<String>.none
        )
        accessToken = r.access
        notice = "Logged in ✅"
    }

    // Dev helper: peek current code (server must be APP_ENV=dev)
    func devPeekCode(email: String) async -> String? {
        struct Peek: Decodable { let code: String? }
        do {
            var comps = URLComponents(url: url("/api/v1/auth/_dev/peek-code"), resolvingAgainstBaseURL: false)!
            comps.queryItems = [URLQueryItem(name: "email", value: email)]
            let peek: Peek = try await api.get(comps.url!, bearer: Optional<String>.none)
            return peek.code
        } catch { return nil }
    }

    // MARK: - Device registration
    func handleAPNsToken(_ token: String) {
        if accessToken == nil { pendingAPNsToken = token; return }
        Task { await registerDevice(token: token) }
    }

    private func registerPendingDeviceTokenIfAny() async {
        guard let t = pendingAPNsToken else { return }
        pendingAPNsToken = nil
        await registerDevice(token: t)
    }

    private func registerDevice(token: String) async {
        guard let bearer = accessToken else { return }
        struct In: Encodable { let token: String; let platform: String; let bundle_id: String; let env: String }
        let payload = In(
            token: token,
            platform: "ios",
            bundle_id: Bundle.main.bundleIdentifier ?? "com.example.homebound",
            env: _isDebugAssertConfiguration() ? "sandbox" : "prod"
        )
        do {
            try await api.post(url("/api/v1/devices"), body: payload, bearer: bearer)
            notice = "Device registered"
        } catch {
            notice = "Device register failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Universal Links (/t/<token>/checkin|checkout)
    func handleUniversalLink(_ urlIn: URL) async {
        let comps = urlIn.pathComponents.filter { $0 != "/" }
        guard comps.count >= 3, comps[0] == "t" else { return }
        let token = comps[1], action = comps[2]
        do {
            struct Resp: Decodable { let ok: Bool }
            let _: Resp = try await api.get(url("/t/\(token)/\(action)"), bearer: Optional<String>.none)
            notice = "Action \(action) OK"
        } catch {
            notice = "UL action failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Debug ping
    struct Health: Decodable { let ok: Bool }
    func ping() async {
        do {
            let h: Health = try await api.get(url("/health"), bearer: Optional<String>.none)
            notice = "Ping ok=\(h.ok)"
        } catch {
            notice = "Ping error: \(error.localizedDescription)"
        }
    }
}
