import Foundation
import SwiftUI

// MARK: - Contact Model (for user's saved contacts)
struct Contact: Identifiable, Codable {
    let id: Int
    let user_id: Int
    let name: String
    let phone: String?
    let email: String?
}

struct ContactCreateRequest: Codable {
    var name: String
    var phone: String?
    var email: String?
}

struct TripCreateRequest: Codable {
    var title: String
    var activity: String = "other"
    var start: Date
    var eta: Date
    var grace_min: Int = 30
    var location_text: String?
    var gen_lat: Double?
    var gen_lon: Double?
    var notes: String?
    var contact1: Int?
    var contact2: Int?
    var contact3: Int?
}

struct Trip: Codable, Identifiable, Equatable {
    var id: Int
    var user_id: Int
    var title: String
    var activity: Activity  // Full activity object with colors, safety tips, messages
    var start_at: Date  // Computed from backend 'start'
    var eta_at: Date    // Computed from backend 'eta'
    var grace_minutes: Int  // Maps from backend 'grace_min'
    var location_text: String?
    var location_lat: Double?  // Maps from backend 'gen_lat'
    var location_lng: Double?  // Maps from backend 'gen_lon'
    var notes: String?
    var status: String
    var completed_at: Date?
    var last_checkin: String?
    var created_at: String
    var contact1: Int?
    var contact2: Int?
    var contact3: Int?
    var checkin_token: String?
    var checkout_token: String?

    // Legacy field name for backward compatibility
    var activity_type: String { activity.name }

    enum CodingKeys: String, CodingKey {
        case id, user_id, title, activity, status, notes
        case start, eta
        case grace_min
        case location_text
        case gen_lat, gen_lon
        case completed_at, last_checkin, created_at
        case contact1, contact2, contact3
        case checkin_token, checkout_token
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        user_id = try container.decode(Int.self, forKey: .user_id)
        title = try container.decode(String.self, forKey: .title)
        activity = try container.decode(Activity.self, forKey: .activity)

        // Parse date strings with fallback for different ISO8601 formats
        let startString = try container.decode(String.self, forKey: .start)
        let etaString = try container.decode(String.self, forKey: .eta)

        start_at = Self.parseISO8601Date(startString) ?? Date()
        eta_at = Self.parseISO8601Date(etaString) ?? Date()

        grace_minutes = try container.decode(Int.self, forKey: .grace_min)
        location_text = try container.decodeIfPresent(String.self, forKey: .location_text)
        location_lat = try container.decodeIfPresent(Double.self, forKey: .gen_lat)
        location_lng = try container.decodeIfPresent(Double.self, forKey: .gen_lon)
        notes = try container.decodeIfPresent(String.self, forKey: .notes)
        status = try container.decode(String.self, forKey: .status)

        // Parse completed_at date string if present
        if let completedAtString = try container.decodeIfPresent(String.self, forKey: .completed_at) {
            print("[Trip Decoder] ✅ completed_at string received: '\(completedAtString)' for trip id=\(id)")
            completed_at = Self.parseISO8601Date(completedAtString)
            if let parsedDate = completed_at {
                print("[Trip Decoder] ✅ completed_at parsed successfully: \(parsedDate)")
            } else {
                print("[Trip Decoder] ❌ completed_at parsing FAILED for string: '\(completedAtString)'")
            }
        } else {
            print("[Trip Decoder] ⚠️ completed_at is nil/missing from API for trip id=\(id), status=\(status)")
            completed_at = nil
        }

        last_checkin = try container.decodeIfPresent(String.self, forKey: .last_checkin)
        created_at = try container.decode(String.self, forKey: .created_at)
        contact1 = try container.decodeIfPresent(Int.self, forKey: .contact1)
        contact2 = try container.decodeIfPresent(Int.self, forKey: .contact2)
        contact3 = try container.decodeIfPresent(Int.self, forKey: .contact3)
        checkin_token = try container.decodeIfPresent(String.self, forKey: .checkin_token)
        checkout_token = try container.decodeIfPresent(String.self, forKey: .checkout_token)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(user_id, forKey: .user_id)
        try container.encode(title, forKey: .title)
        try container.encode(activity, forKey: .activity)
        try container.encode(start_at.ISO8601Format(), forKey: .start)
        try container.encode(eta_at.ISO8601Format(), forKey: .eta)
        try container.encode(grace_minutes, forKey: .grace_min)
        try container.encodeIfPresent(location_text, forKey: .location_text)
        try container.encodeIfPresent(location_lat, forKey: .gen_lat)
        try container.encodeIfPresent(location_lng, forKey: .gen_lon)
        try container.encodeIfPresent(notes, forKey: .notes)
        try container.encode(status, forKey: .status)
        // Encode completed_at as ISO8601 string
        if let completedAt = completed_at {
            try container.encode(completedAt.ISO8601Format(), forKey: .completed_at)
        }
        try container.encodeIfPresent(last_checkin, forKey: .last_checkin)
        try container.encode(created_at, forKey: .created_at)
        try container.encodeIfPresent(contact1, forKey: .contact1)
        try container.encodeIfPresent(contact2, forKey: .contact2)
        try container.encodeIfPresent(contact3, forKey: .contact3)
        try container.encodeIfPresent(checkin_token, forKey: .checkin_token)
        try container.encodeIfPresent(checkout_token, forKey: .checkout_token)
    }

    /// Parse ISO8601 date string with fallback for different formats
    private static func parseISO8601Date(_ dateString: String) -> Date? {
        // First, normalize the string - replace space with 'T' if needed (backend uses str() which produces space)
        let normalizedString = dateString.replacingOccurrences(of: " ", with: "T")

        // Try with fractional seconds first
        let formatterWithFractional = ISO8601DateFormatter()
        formatterWithFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatterWithFractional.date(from: normalizedString) {
            return date
        }

        // Try without fractional seconds
        let formatterWithoutFractional = ISO8601DateFormatter()
        formatterWithoutFractional.formatOptions = [.withInternetDateTime]
        if let date = formatterWithoutFractional.date(from: normalizedString) {
            return date
        }

        // Try with timezone
        let formatterWithTimezone = ISO8601DateFormatter()
        formatterWithTimezone.formatOptions = [.withInternetDateTime, .withTimeZone]
        if let date = formatterWithTimezone.date(from: normalizedString) {
            return date
        }

        // Try custom DateFormatter for format: "yyyy-MM-dd HH:mm:ss" (Python str() format)
        let customFormatter = DateFormatter()
        customFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        customFormatter.timeZone = TimeZone(identifier: "UTC")
        if let date = customFormatter.date(from: dateString) {
            return date
        }

        // Try with milliseconds: "yyyy-MM-dd HH:mm:ss.SSSSSS"
        customFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSSSSS"
        if let date = customFormatter.date(from: dateString) {
            return date
        }

        // Try with T separator and microseconds (no timezone): "2025-11-24T07:26:43.111442"
        customFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        if let date = customFormatter.date(from: normalizedString) {
            return date
        }

        // Try with T separator and milliseconds (no timezone): "2025-11-24T07:26:43.111"
        customFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        if let date = customFormatter.date(from: normalizedString) {
            return date
        }

        // Last resort: try basic ISO8601 format
        let formatterBasic = ISO8601DateFormatter()
        return formatterBasic.date(from: normalizedString)
    }

    /// Memberwise initializer for local storage
    init(
        id: Int,
        user_id: Int,
        title: String,
        activity: Activity,
        start_at: Date,
        eta_at: Date,
        grace_minutes: Int,
        location_text: String?,
        location_lat: Double?,
        location_lng: Double?,
        notes: String?,
        status: String,
        completed_at: Date?,
        last_checkin: String?,
        created_at: String,
        contact1: Int?,
        contact2: Int?,
        contact3: Int?,
        checkin_token: String?,
        checkout_token: String?
    ) {
        self.id = id
        self.user_id = user_id
        self.title = title
        self.activity = activity
        self.start_at = start_at
        self.eta_at = eta_at
        self.grace_minutes = grace_minutes
        self.location_text = location_text
        self.location_lat = location_lat
        self.location_lng = location_lng
        self.notes = notes
        self.status = status
        self.completed_at = completed_at
        self.last_checkin = last_checkin
        self.created_at = created_at
        self.contact1 = contact1
        self.contact2 = contact2
        self.contact3 = contact3
        self.checkin_token = checkin_token
        self.checkout_token = checkout_token
    }
}

struct TimelineResponse: Codable {
    var plan_id: Int
    var events: [TimelineEvent]
}

struct TimelineEvent: Codable, Identifiable {
    var id: String { "\(kind)-\(at.timeIntervalSince1970)" }
    var kind: String
    var at: Date
    var meta: String?
}

// MARK: - Activity Models (from database)

struct Activity: Codable, Identifiable, Equatable {
    let id: Int
    let name: String
    let icon: String
    let default_grace_minutes: Int
    let colors: ActivityColors
    let messages: ActivityMessages
    let safety_tips: [String]
    let order: Int

    struct ActivityColors: Codable, Equatable {
        let primary: String
        let secondary: String
        let accent: String
    }

    struct ActivityMessages: Codable, Equatable {
        let start: String
        let checkin: String
        let checkout: String
        let overdue: String
        let encouragement: [String]
    }
}

// MARK: - ActivityTypeAdapter (backward compatibility wrapper)

/// Adapter to make database Activity compatible with existing ActivityType enum usage
struct ActivityTypeAdapter: Identifiable, Hashable {
    let activity: Activity

    var id: Int { activity.id }
    var rawValue: String { activity.name.lowercased().replacingOccurrences(of: " ", with: "_") }
    var displayName: String { activity.name }
    var icon: String { activity.icon }
    var defaultGraceMinutes: Int { activity.default_grace_minutes }

    var primaryColor: Color {
        Color(hex: activity.colors.primary) ?? .purple
    }

    var secondaryColor: Color {
        Color(hex: activity.colors.secondary) ?? .gray
    }

    var accentColor: Color {
        Color(hex: activity.colors.accent) ?? .blue
    }

    var startMessage: String { activity.messages.start }
    var checkinMessage: String { activity.messages.checkin }
    var checkoutMessage: String { activity.messages.checkout }
    var overdueMessage: String { activity.messages.overdue }
    var encouragementMessages: [String] { activity.messages.encouragement }
    var safetyTips: [String] { activity.safety_tips }

    func hash(into hasher: inout Hasher) {
        hasher.combine(activity.id)
    }

    static func == (lhs: ActivityTypeAdapter, rhs: ActivityTypeAdapter) -> Bool {
        lhs.activity.id == rhs.activity.id
    }
}

// Extension for easy conversion
extension Array where Element == Activity {
    func toAdapters() -> [ActivityTypeAdapter] {
        map { ActivityTypeAdapter(activity: $0) }
    }
}
