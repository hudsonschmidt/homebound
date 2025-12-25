//
//  LiveActivityAPI.swift
//  HomeboundWidgets
//
//  Lightweight HTTP client for Live Activity intents
//

import Foundation

struct LiveActivityAPI {
    static let shared = LiveActivityAPI()

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        // Reduced timeouts to leave more margin for widget execution time (~30s limit)
        config.timeoutIntervalForRequest = 8
        config.timeoutIntervalForResource = 10
        return URLSession(configuration: config)
    }()

    struct TokenResponse: Decodable {
        let ok: Bool
        let message: String?
    }

    /// Perform check-in action
    func checkIn(token: String) async throws -> TokenResponse {
        guard let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(token)/checkin") else {
            throw LiveActivityAPIError.invalidURL
        }
        return try await performRequest(url: url)
    }

    /// Perform check-out/complete action
    func checkOut(token: String) async throws -> TokenResponse {
        guard let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(token)/checkout") else {
            throw LiveActivityAPIError.invalidURL
        }
        return try await performRequest(url: url)
    }

    private func performRequest(url: URL) async throws -> TokenResponse {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw LiveActivityAPIError.badResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            throw LiveActivityAPIError.httpError(statusCode: httpResponse.statusCode)
        }

        do {
            return try JSONDecoder().decode(TokenResponse.self, from: data)
        } catch {
            // Provide better error context for decode failures
            let responseString = String(data: data, encoding: .utf8) ?? "Unable to read response"
            debugLog("[LiveActivityAPI] Decode error: \(error). Response: \(responseString.prefix(200))")
            throw LiveActivityAPIError.decodeError(underlying: error)
        }
    }

    enum LiveActivityAPIError: Error, LocalizedError {
        case invalidURL
        case badResponse
        case httpError(statusCode: Int)
        case decodeError(underlying: Error)

        var errorDescription: String? {
            switch self {
            case .invalidURL:
                return "Invalid URL configuration"
            case .badResponse:
                return "Invalid server response - expected HTTPURLResponse"
            case .httpError(let code):
                switch code {
                case 400: return "Bad request (400) - check token format"
                case 401: return "Unauthorized (401) - token may be expired"
                case 403: return "Forbidden (403) - action not allowed"
                case 404: return "Not found (404) - trip may have been deleted"
                case 409: return "Conflict (409) - action already performed"
                case 500...599: return "Server error (\(code)) - try again later"
                default: return "HTTP error (\(code))"
                }
            case .decodeError(let underlying):
                return "Failed to parse response: \(underlying.localizedDescription)"
            }
        }
    }
}

/// Debug log helper for widget extension (internal so other widget files can use it)
func debugLog(_ message: String) {
    #if DEBUG
    print(message)
    #endif
}
