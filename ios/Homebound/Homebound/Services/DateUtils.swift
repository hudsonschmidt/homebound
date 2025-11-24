import Foundation

/// Centralized date parsing and formatting utilities
enum DateUtils {
    /// Shared ISO8601 formatter for parsing backend timestamps
    private static let iso8601Formatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601FormatterNoFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let customFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Parse a date string from the backend (ISO8601 or custom format)
    /// - Parameter dateString: The date string to parse
    /// - Returns: A Date object if parsing succeeds, nil otherwise
    static func parseDate(_ dateString: String) -> Date? {
        // Try ISO8601 with fractional seconds first
        if let date = iso8601Formatter.date(from: dateString) {
            return date
        }

        // Try ISO8601 without fractional seconds
        if let date = iso8601FormatterNoFractional.date(from: dateString) {
            return date
        }

        // Try custom format for backend timestamps
        if let date = customFormatter.date(from: dateString) {
            return date
        }

        return nil
    }

    /// Format a duration between two dates as a human-readable string (e.g., "2h 30m")
    /// - Parameters:
    ///   - start: The start date
    ///   - end: The end date
    /// - Returns: A formatted duration string, or nil if invalid
    static func formatDuration(from start: Date, to end: Date) -> String? {
        let interval = end.timeIntervalSince(start)
        guard interval >= 0 else { return nil }

        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m"
        }
        return nil
    }
}
