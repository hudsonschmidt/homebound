//
//  DateUtils.swift
//  Homebound
//
//  Shared date formatting utilities.
//  Add this file to BOTH the main app target AND the widget extension target.
//

import Foundation

/// Centralized date formatting utilities to ensure consistency across the app
enum DateUtils {

    // MARK: - ISO 8601 Formatters

    /// Standard ISO 8601 formatter for API communication
    static let iso8601Formatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    /// ISO 8601 formatter with fractional seconds support
    static let iso8601WithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    /// Custom formatter matching backend format (yyyy-MM-dd'T'HH:mm:ss)
    static let backendFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter
    }()

    // MARK: - Display Formatters

    /// Time only formatter (e.g., "2:30 PM")
    static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .short
        return formatter
    }()

    /// Short date formatter (e.g., "Jan 15")
    static let shortDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"
        return formatter
    }()

    /// Full date and time formatter (e.g., "Jan 15, 2024 at 2:30 PM")
    static let fullDateTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()

    /// Relative date formatter (e.g., "Today", "Yesterday", "2 days ago")
    static let relativeDateFormatter: RelativeDateTimeFormatter = {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter
    }()

    // MARK: - Additional Formatters for Python Output

    /// Python microseconds format (yyyy-MM-dd'T'HH:mm:ss.SSSSSS)
    private static let pythonMicrosecondsFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        return formatter
    }()

    /// Python milliseconds format (yyyy-MM-dd'T'HH:mm:ss.SSS)
    private static let pythonMillisecondsFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        return formatter
    }()

    /// Python str() with microseconds (yyyy-MM-dd HH:mm:ss.SSSSSS)
    private static let pythonStrMicrosecondsFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSSSSS"
        return formatter
    }()

    /// Python str() without fractional (yyyy-MM-dd HH:mm:ss)
    private static let pythonStrFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return formatter
    }()

    /// ISO8601 with explicit timezone option
    private static let iso8601WithTimezone: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withTimeZone]
        return formatter
    }()

    // MARK: - Parsing Methods

    /// Parse an ISO 8601 date string with comprehensive fallback strategies
    /// Handles Python's isoformat() output and various ISO8601 formats
    /// - Parameter string: The date string to parse
    /// - Returns: The parsed Date, or nil if parsing fails
    static func parseISO8601(_ string: String) -> Date? {
        // Normalize: replace space with 'T' if needed (Python str() uses space)
        let normalizedString = string.replacingOccurrences(of: " ", with: "T")

        // Try with fractional seconds first (ISO8601 with timezone)
        if let date = iso8601WithFractionalSeconds.date(from: normalizedString) {
            return date
        }

        // Try without fractional seconds (ISO8601 with timezone)
        if let date = iso8601Formatter.date(from: normalizedString) {
            return date
        }

        // Try with explicit timezone option
        if let date = iso8601WithTimezone.date(from: normalizedString) {
            return date
        }

        // Python isoformat with microseconds: "2025-12-05T10:30:00.123456"
        if let date = pythonMicrosecondsFormatter.date(from: normalizedString) {
            return date
        }

        // Python isoformat with milliseconds: "2025-12-05T10:30:00.123"
        if let date = pythonMillisecondsFormatter.date(from: normalizedString) {
            return date
        }

        // Python isoformat without fractional: "2025-12-05T10:30:00"
        if let date = backendFormatter.date(from: normalizedString) {
            return date
        }

        // Python str() with microseconds: "2025-12-05 10:30:00.123456"
        if let date = pythonStrMicrosecondsFormatter.date(from: string) {
            return date
        }

        // Python str() without fractional: "2025-12-05 10:30:00"
        if let date = pythonStrFormatter.date(from: string) {
            return date
        }

        // Last resort: basic ISO8601
        let formatterBasic = ISO8601DateFormatter()
        return formatterBasic.date(from: normalizedString)
    }

    /// Format a date for API communication (ISO 8601)
    /// - Parameter date: The date to format
    /// - Returns: ISO 8601 formatted string
    static func formatForAPI(_ date: Date) -> String {
        return iso8601Formatter.string(from: date)
    }

    /// Format a date for backend communication (custom format)
    /// - Parameter date: The date to format
    /// - Returns: Backend-compatible formatted string
    static func formatForBackend(_ date: Date) -> String {
        return backendFormatter.string(from: date)
    }

    // MARK: - Display Methods

    /// Format time remaining as a human-readable string
    /// - Parameter interval: Time interval in seconds
    /// - Returns: Formatted string (e.g., "2h 30m", "45m", "<1m")
    static func formatTimeRemaining(_ interval: TimeInterval) -> String {
        let absInterval = abs(interval)
        let isOverdue = interval < 0

        if absInterval < 60 {
            return isOverdue ? "Now" : "<1m"
        } else if absInterval < 3600 {
            let minutes = Int(absInterval / 60)
            return isOverdue ? "\(minutes)m overdue" : "\(minutes)m"
        } else {
            let hours = Int(absInterval / 3600)
            let minutes = Int((absInterval.truncatingRemainder(dividingBy: 3600)) / 60)
            if minutes > 0 {
                return isOverdue ? "\(hours)h \(minutes)m overdue" : "\(hours)h \(minutes)m"
            }
            return isOverdue ? "\(hours)h overdue" : "\(hours)h"
        }
    }

    /// Format a date for display with smart relative formatting
    /// - Parameter date: The date to format
    /// - Returns: Human-readable date string
    static func formatForDisplay(_ date: Date) -> String {
        let calendar = Calendar.current
        let now = Date()

        if calendar.isDateInToday(date) {
            return "Today at \(timeFormatter.string(from: date))"
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday at \(timeFormatter.string(from: date))"
        } else if calendar.isDateInTomorrow(date) {
            return "Tomorrow at \(timeFormatter.string(from: date))"
        } else if let daysAgo = calendar.dateComponents([.day], from: date, to: now).day, daysAgo < 7 && daysAgo >= 0 {
            return relativeDateFormatter.localizedString(for: date, relativeTo: now)
        } else {
            return fullDateTimeFormatter.string(from: date)
        }
    }

    /// Format a duration between two dates as a human-readable string (e.g., "2h 30m" or "1d 2h")
    /// - Parameters:
    ///   - start: The start date
    ///   - end: The end date
    /// - Returns: A formatted duration string, or nil if invalid
    static func formatDuration(from start: Date, to end: Date) -> String? {
        let interval = end.timeIntervalSince(start)
        guard interval >= 0 else { return nil }

        let days = Int(interval) / 86400
        let hours = (Int(interval) % 86400) / 3600
        let minutes = (Int(interval) % 3600) / 60

        if days > 0 {
            return "\(days)d \(hours)h"
        } else if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m"
        }
        return nil
    }
}
