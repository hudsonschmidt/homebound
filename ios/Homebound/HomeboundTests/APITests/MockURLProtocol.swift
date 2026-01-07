import Foundation

/// Mock URL Protocol for testing network requests without actual network calls
class MockURLProtocol: URLProtocol {

    /// Handler to provide mock responses
    static var requestHandler: ((URLRequest) throws -> (Data, HTTPURLResponse))?

    /// Captured requests for verification
    static var capturedRequests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool {
        return true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        return request
    }

    override func startLoading() {
        MockURLProtocol.capturedRequests.append(request)

        guard let handler = MockURLProtocol.requestHandler else {
            let error = NSError(domain: "MockURLProtocol", code: -1, userInfo: [NSLocalizedDescriptionKey: "No handler set"])
            client?.urlProtocol(self, didFailWithError: error)
            return
        }

        do {
            let (data, response) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {
        // Required but nothing to do here
    }

    /// Reset state between tests
    static func reset() {
        requestHandler = nil
        capturedRequests = []
    }

    /// Create a mock URLSession configured to use this protocol
    static func mockURLSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return URLSession(configuration: config)
    }
}
