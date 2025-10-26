import Foundation

struct API {
    let encoder: JSONEncoder = {
        let e = JSONEncoder()
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        e.dateEncodingStrategy = .formatted(f)
        return e
    }()

    let decoder: JSONDecoder = {
        let d = JSONDecoder()
        // Use custom decoding to handle both ISO8601 and backend format
        d.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            // Try ISO8601 first (backend .isoformat() format)
            let iso8601Formatter = ISO8601DateFormatter()
            iso8601Formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso8601Formatter.date(from: dateString) {
                return date
            }

            // Fallback to ISO8601 without fractional seconds
            iso8601Formatter.formatOptions = [.withInternetDateTime]
            if let date = iso8601Formatter.date(from: dateString) {
                return date
            }

            // Fallback to custom format
            let f = DateFormatter()
            f.calendar = Calendar(identifier: .iso8601)
            f.locale = Locale(identifier: "en_US_POSIX")
            f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = f.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode date string: \(dateString)")
        }
        return d
    }()

    func get<T: Decodable>(_ url: URL, bearer: String?) async throws -> T {
        var req = URLRequest(url: url); req.httpMethod = "GET"
        if let b = bearer { req.addValue("Bearer \(b)", forHTTPHeaderField: "Authorization") }
        let (data, resp) = try await URLSession.shared.data(for: req)
        try check(resp: resp, data: data)
        return try decoder.decode(T.self, from: data)
    }

    func post<T: Decodable, B: Encodable>(_ url: URL, body: B, bearer: String?) async throws -> T {
        var req = URLRequest(url: url); req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        if let b = bearer { req.addValue("Bearer \(b)", forHTTPHeaderField: "Authorization") }
        req.httpBody = try encoder.encode(body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        try check(resp: resp, data: data)
        if T.self == Empty.self { return Empty() as! T }
        return try decoder.decode(T.self, from: data)
    }

    func post<B: Encodable>(_ url: URL, body: B, bearer: String?) async throws {
        let _: Empty = try await post(url, body: body, bearer: bearer)
    }

    private func check(resp: URLResponse, data: Data) throws {
        guard let http = resp as? HTTPURLResponse else { throw APIError.badResponse }
        if (200..<300).contains(http.statusCode) { return }
        let msg = String(data: data, encoding: .utf8) ?? "HTTP \(http.statusCode)"
        throw APIError.server(msg)
    }

    struct Empty: Decodable {}
    enum APIError: Error { case badResponse, server(String) }
}
