import XCTest
@testable import Homebound

final class DateUtilsTests: XCTestCase {

    // MARK: - parseISO8601 Tests

    func testParseISO8601_WithFractionalSeconds() {
        let dateString = "2025-12-05T10:30:00.123Z"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)

        let calendar = Calendar(identifier: .iso8601)
        let components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: date!)

        XCTAssertEqual(components.year, 2025)
        XCTAssertEqual(components.month, 12)
        XCTAssertEqual(components.day, 5)
        XCTAssertEqual(components.hour, 10)
        XCTAssertEqual(components.minute, 30)
        XCTAssertEqual(components.second, 0)
    }

    func testParseISO8601_WithoutFractionalSeconds() {
        let dateString = "2025-12-05T10:30:00Z"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)

        let calendar = Calendar(identifier: .iso8601)
        let components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: date!)

        XCTAssertEqual(components.year, 2025)
        XCTAssertEqual(components.month, 12)
        XCTAssertEqual(components.day, 5)
        XCTAssertEqual(components.hour, 10)
        XCTAssertEqual(components.minute, 30)
    }

    func testParseISO8601_PythonMicroseconds() {
        let dateString = "2025-12-05T10:30:00.123456"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)
    }

    func testParseISO8601_PythonMilliseconds() {
        let dateString = "2025-12-05T10:30:00.123"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)
    }

    func testParseISO8601_BackendFormat() {
        let dateString = "2025-12-05T10:30:00"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)

        let calendar = Calendar(identifier: .iso8601)
        let components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: date!)

        XCTAssertEqual(components.year, 2025)
        XCTAssertEqual(components.month, 12)
        XCTAssertEqual(components.day, 5)
    }

    func testParseISO8601_PythonStrWithSpace() {
        // Python str(datetime) uses space instead of T
        let dateString = "2025-12-05 10:30:00"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)
    }

    func testParseISO8601_PythonStrWithMicroseconds() {
        let dateString = "2025-12-05 10:30:00.123456"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)
    }

    func testParseISO8601_InvalidFormat() {
        let dateString = "not-a-date"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNil(date)
    }

    func testParseISO8601_EmptyString() {
        let dateString = ""
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNil(date)
    }

    func testParseISO8601_WithTimezoneOffset() {
        let dateString = "2025-12-05T10:30:00+05:00"
        let date = DateUtils.parseISO8601(dateString)

        XCTAssertNotNil(date)
    }

    // MARK: - formatForAPI Tests

    func testFormatForAPI_ReturnsISO8601Format() {
        // Create a known date in UTC
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

        let formatted = DateUtils.formatForAPI(date)

        // Should be ISO8601 format with Z suffix
        XCTAssertTrue(formatted.contains("2025-12-05"))
        XCTAssertTrue(formatted.contains("10:30:00"))
        XCTAssertTrue(formatted.hasSuffix("Z"))
    }

    // MARK: - formatForBackend Tests

    func testFormatForBackend_ReturnsBackendFormat() {
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

        let formatted = DateUtils.formatForBackend(date)

        XCTAssertEqual(formatted, "2025-12-05T10:30:00")
    }

    func testFormatForBackend_NoTimezoneIndicator() {
        let date = Date()
        let formatted = DateUtils.formatForBackend(date)

        // Should not have Z or timezone offset
        XCTAssertFalse(formatted.hasSuffix("Z"))
        XCTAssertFalse(formatted.contains("+"))
    }

    // MARK: - formatTimeRemaining Tests

    func testFormatTimeRemaining_LessThan60Seconds() {
        let result = DateUtils.formatTimeRemaining(30)
        XCTAssertEqual(result, "<1m")
    }

    func testFormatTimeRemaining_ExactlyOneMinute() {
        let result = DateUtils.formatTimeRemaining(60)
        XCTAssertEqual(result, "1m")
    }

    func testFormatTimeRemaining_MinutesOnly() {
        let result = DateUtils.formatTimeRemaining(2700) // 45 minutes
        XCTAssertEqual(result, "45m")
    }

    func testFormatTimeRemaining_HoursAndMinutes() {
        let result = DateUtils.formatTimeRemaining(9000) // 2h 30m
        XCTAssertEqual(result, "2h 30m")
    }

    func testFormatTimeRemaining_ExactHours() {
        let result = DateUtils.formatTimeRemaining(7200) // 2h
        XCTAssertEqual(result, "2h")
    }

    func testFormatTimeRemaining_NegativeNow() {
        let result = DateUtils.formatTimeRemaining(-30)
        XCTAssertEqual(result, "Now")
    }

    func testFormatTimeRemaining_NegativeMinutes() {
        let result = DateUtils.formatTimeRemaining(-300) // -5 minutes
        XCTAssertEqual(result, "5m overdue")
    }

    func testFormatTimeRemaining_NegativeHours() {
        let result = DateUtils.formatTimeRemaining(-5400) // -1h 30m
        XCTAssertEqual(result, "1h 30m overdue")
    }

    // MARK: - formatDuration Tests

    func testFormatDuration_Days() {
        let start = Date()
        let end = start.addingTimeInterval(26 * 3600) // 26 hours = 1d 2h

        let result = DateUtils.formatDuration(from: start, to: end)

        XCTAssertEqual(result, "1d 2h")
    }

    func testFormatDuration_Hours() {
        let start = Date()
        let end = start.addingTimeInterval(2.5 * 3600) // 2h 30m

        let result = DateUtils.formatDuration(from: start, to: end)

        XCTAssertEqual(result, "2h 30m")
    }

    func testFormatDuration_Minutes() {
        let start = Date()
        let end = start.addingTimeInterval(45 * 60) // 45 minutes

        let result = DateUtils.formatDuration(from: start, to: end)

        XCTAssertEqual(result, "45m")
    }

    func testFormatDuration_Zero() {
        let start = Date()
        let end = start // Same date

        let result = DateUtils.formatDuration(from: start, to: end)

        XCTAssertNil(result)
    }

    func testFormatDuration_NegativeInterval() {
        let start = Date()
        let end = start.addingTimeInterval(-3600) // End before start

        let result = DateUtils.formatDuration(from: start, to: end)

        XCTAssertNil(result)
    }

    // MARK: - formatForDisplay Tests

    func testFormatForDisplay_Today() {
        let calendar = Calendar.current
        var components = calendar.dateComponents([.year, .month, .day], from: Date())
        components.hour = 14
        components.minute = 0
        let todayDate = calendar.date(from: components)!

        let result = DateUtils.formatForDisplay(todayDate)

        XCTAssertTrue(result.contains("Today"))
    }

    func testFormatForDisplay_Yesterday() {
        let calendar = Calendar.current
        let yesterday = calendar.date(byAdding: .day, value: -1, to: Date())!

        let result = DateUtils.formatForDisplay(yesterday)

        XCTAssertTrue(result.contains("Yesterday"))
    }

    func testFormatForDisplay_Tomorrow() {
        let calendar = Calendar.current
        let tomorrow = calendar.date(byAdding: .day, value: 1, to: Date())!

        let result = DateUtils.formatForDisplay(tomorrow)

        XCTAssertTrue(result.contains("Tomorrow"))
    }

    func testFormatForDisplay_WithinWeek() {
        let calendar = Calendar.current
        let threeDaysAgo = calendar.date(byAdding: .day, value: -3, to: Date())!

        let result = DateUtils.formatForDisplay(threeDaysAgo)

        // Should return relative format like "3 days ago"
        XCTAssertFalse(result.contains("Today"))
        XCTAssertFalse(result.contains("Yesterday"))
    }

    func testFormatForDisplay_OlderDates() {
        let calendar = Calendar.current
        let twoWeeksAgo = calendar.date(byAdding: .day, value: -14, to: Date())!

        let result = DateUtils.formatForDisplay(twoWeeksAgo)

        // Should return full date format
        XCTAssertFalse(result.contains("Today"))
        XCTAssertFalse(result.contains("ago"))
    }

    // MARK: - Timezone-Aware Methods Tests

    func testFormatTime_InSpecificTimezone() {
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

        // Format in Pacific time (should be different from UTC)
        let result = DateUtils.formatTime(date, inTimezone: "America/Los_Angeles")

        // The time should be formatted (we can't assert exact value due to DST)
        XCTAssertFalse(result.isEmpty)
    }

    func testFormatTime_NilTimezone_UsesDevice() {
        let date = Date()
        let result = DateUtils.formatTime(date, inTimezone: nil)

        // Should return something
        XCTAssertFalse(result.isEmpty)
    }

    func testTimezoneAbbreviation_ValidTimezone() {
        let abbreviation = DateUtils.timezoneAbbreviation("America/Los_Angeles")

        XCTAssertNotNil(abbreviation)
        // Could be PST or PDT depending on time of year
        XCTAssertTrue(abbreviation == "PST" || abbreviation == "PDT")
    }

    func testTimezoneAbbreviation_InvalidTimezone() {
        let abbreviation = DateUtils.timezoneAbbreviation("Invalid/Timezone")

        XCTAssertNil(abbreviation)
    }

    func testTimezoneAbbreviation_NilTimezone() {
        let abbreviation = DateUtils.timezoneAbbreviation(nil)

        XCTAssertNil(abbreviation)
    }

    // MARK: - Static Formatter Tests

    func testTimeFormatter_ReturnsShortTimeStyle() {
        let formatter = DateUtils.timeFormatter
        XCTAssertEqual(formatter.timeStyle, .short)
        XCTAssertEqual(formatter.dateStyle, .none)
    }

    func testShortDateFormatter_ReturnsExpectedFormat() {
        var components = DateComponents()
        components.year = 2025
        components.month = 1
        components.day = 15
        components.hour = 12
        components.minute = 0
        components.timeZone = TimeZone.current

        let calendar = Calendar(identifier: .gregorian)
        let date = calendar.date(from: components)!

        let result = DateUtils.shortDateFormatter.string(from: date)

        XCTAssertEqual(result, "Jan 15")
    }

    func testFullDateTimeFormatter_IncludesDateAndTime() {
        let formatter = DateUtils.fullDateTimeFormatter
        XCTAssertEqual(formatter.dateStyle, .medium)
        XCTAssertEqual(formatter.timeStyle, .short)
    }
}
