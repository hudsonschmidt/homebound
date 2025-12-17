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
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
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

        return try JSONDecoder().decode(TokenResponse.self, from: data)
    }

    enum LiveActivityAPIError: Error, LocalizedError {
        case invalidURL
        case badResponse
        case httpError(statusCode: Int)

        var errorDescription: String? {
            switch self {
            case .invalidURL:
                return "Invalid URL"
            case .badResponse:
                return "Invalid server response"
            case .httpError(let code):
                return "Server error (\(code))"
            }
        }
    }
}
