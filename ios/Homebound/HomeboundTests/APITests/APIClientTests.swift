import XCTest
@testable import Homebound

final class APIClientTests: XCTestCase {

    private var api: API!

    override func setUp() {
        super.setUp()
        api = API()
    }

    override func tearDown() {
        api = nil
        super.tearDown()
    }

    // MARK: - Encoder Tests

    func testEncoder_DateFormat_MatchesBackendExpectation() throws {
        var components = DateComponents()
        components.year = 2025
        components.month = 12
        components.day = 5
        components.hour = 10
        components.minute = 30
        components.second = 0
        components.timeZone = TimeZone(identifier: "UTC")

        let calendar = Calendar(identifier: .gregorian)
        let date = calendar.date(from: components)!

        struct TestStruct: Encodable {
            let date: Date
        }

        let testObj = TestStruct(date: date)
        let data = try api.encoder.encode(testObj)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["date"] as? String, "2025-12-05T10:30:00")
    }

    func testEncoder_UTCTimezone() throws {
        // Create a date in a non-UTC timezone
        var components = DateComponents()
        components.year = 2025
        components.month = 12
        components.day = 5
        components.hour = 10
        components.minute = 30
        components.second = 0
        components.timeZone = TimeZone(identifier: "America/Los_Angeles") // PST/PDT

        let calendar = Calendar(identifier: .gregorian)
        let date = calendar.date(from: components)!

        struct TestStruct: Encodable {
            let date: Date
        }

        let testObj = TestStruct(date: date)
        let data = try api.encoder.encode(testObj)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let dateString = json["date"] as! String

        // Should be converted to UTC (PST is UTC-8, PDT is UTC-7)
        // The exact offset depends on DST, but it should NOT be "10:30:00"
        XCTAssertFalse(dateString.contains("10:30:00"))
    }

    // MARK: - Decoder Tests

    func testDecoder_ISO8601WithFractionalSeconds() throws {
        let json = """
        {"date": "2025-12-05T10:30:00.123456Z"}
        """.data(using: .utf8)!

        struct TestStruct: Decodable {
            let date: Date
        }

        let result = try api.decoder.decode(TestStruct.self, from: json)
        XCTAssertNotNil(result.date)
    }

    func testDecoder_ISO8601WithoutFractionalSeconds() throws {
        let json = """
        {"date": "2025-12-05T10:30:00Z"}
        """.data(using: .utf8)!

        struct TestStruct: Decodable {
            let date: Date
        }

        let result = try api.decoder.decode(TestStruct.self, from: json)
        XCTAssertNotNil(result.date)
    }

    func testDecoder_BackendFormat() throws {
        let json = """
        {"date": "2025-12-05T10:30:00"}
        """.data(using: .utf8)!

        struct TestStruct: Decodable {
            let date: Date
        }

        let result = try api.decoder.decode(TestStruct.self, from: json)
        XCTAssertNotNil(result.date)
    }

    func testDecoder_ThrowsOnInvalidDate() {
        let json = """
        {"date": "not-a-date"}
        """.data(using: .utf8)!

        struct TestStruct: Decodable {
            let date: Date
        }

        XCTAssertThrowsError(try api.decoder.decode(TestStruct.self, from: json))
    }

    // MARK: - APIError Tests

    func testAPIError_Unauthorized() {
        let error = API.APIError.unauthorized

        switch error {
        case .unauthorized:
            XCTAssertTrue(true)
        default:
            XCTFail("Expected unauthorized error")
        }
    }

    func testAPIError_HTTPError_ContainsStatusCode() {
        let error = API.APIError.httpError(statusCode: 500, message: "Internal Server Error")

        switch error {
        case .httpError(let statusCode, let message):
            XCTAssertEqual(statusCode, 500)
            XCTAssertEqual(message, "Internal Server Error")
        default:
            XCTFail("Expected httpError")
        }
    }

    func testAPIError_BadResponse() {
        let error = API.APIError.badResponse

        switch error {
        case .badResponse:
            XCTAssertTrue(true)
        default:
            XCTFail("Expected badResponse error")
        }
    }

    // MARK: - Empty Response Tests

    func testEmpty_Codable() throws {
        let empty = API.Empty()

        let data = try JSONEncoder().encode(empty)
        let decoded = try JSONDecoder().decode(API.Empty.self, from: data)

        XCTAssertNotNil(decoded)
    }

    // MARK: - Request Building Tests

    /// Tests that verify request structure without making actual network calls

    func testRequestStructure_GET_Headers() {
        // We can't easily test the actual request building without refactoring,
        // but we can verify the API struct exists and has the expected methods
        let api = API()
        XCTAssertNotNil(api.encoder)
        XCTAssertNotNil(api.decoder)
    }

    // MARK: - Decoder Date Strategy Tests

    func testDecoder_HandlesPythonDateFormats() throws {
        // Python format with timezone (API decoder handles this)
        let json1 = """
        {"date": "2025-12-05T10:30:00.123456Z"}
        """.data(using: .utf8)!

        // Python format with timezone (milliseconds)
        let json2 = """
        {"date": "2025-12-05T10:30:00.123Z"}
        """.data(using: .utf8)!

        struct TestStruct: Decodable {
            let date: Date
        }

        let result1 = try api.decoder.decode(TestStruct.self, from: json1)
        let result2 = try api.decoder.decode(TestStruct.self, from: json2)

        XCTAssertNotNil(result1.date)
        XCTAssertNotNil(result2.date)
    }

    func testDecoder_DateComponents_AreCorrect() throws {
        let json = """
        {"date": "2025-12-05T10:30:00Z"}
        """.data(using: .utf8)!

        struct TestStruct: Decodable {
            let date: Date
        }

        let result = try api.decoder.decode(TestStruct.self, from: json)

        let calendar = Calendar(identifier: .iso8601)
        let components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: result.date)

        XCTAssertEqual(components.year, 2025)
        XCTAssertEqual(components.month, 12)
        XCTAssertEqual(components.day, 5)
        XCTAssertEqual(components.hour, 10)
        XCTAssertEqual(components.minute, 30)
    }

    // MARK: - Encoder/Decoder Roundtrip Tests

    func testEncoderDecoder_Roundtrip_Date() throws {
        let originalDate = Date()

        struct TestStruct: Codable {
            let date: Date
        }

        let original = TestStruct(date: originalDate)
        let encoded = try api.encoder.encode(original)
        let decoded = try api.decoder.decode(TestStruct.self, from: encoded)

        // Allow 1 second tolerance due to fractional seconds being lost
        XCTAssertEqual(decoded.date.timeIntervalSince1970, originalDate.timeIntervalSince1970, accuracy: 1)
    }

    func testEncoderDecoder_Roundtrip_ContactCreateRequest() throws {
        let request = ContactCreateRequest(name: "Test Contact", email: "test@example.com")

        let encoded = try api.encoder.encode(request)
        let decoded = try api.decoder.decode(ContactCreateRequest.self, from: encoded)

        XCTAssertEqual(decoded.name, request.name)
        XCTAssertEqual(decoded.email, request.email)
    }
}
