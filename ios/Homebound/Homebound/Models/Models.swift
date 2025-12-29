import CoreLocation
import Foundation
import SwiftUI

// MARK: - Contact Model (for user's saved contacts)
struct Contact: Identifiable, Codable, Hashable {
    let id: Int
    let user_id: Int
    let name: String
    let email: String
}

struct ContactCreateRequest: Codable {
    var name: String
    var email: String
}

// MARK: - Friend Models

/// A friend (another Homebound user)
struct Friend: Codable, Identifiable, Hashable {
    let user_id: Int
    let first_name: String
    let last_name: String
    let profile_photo_url: String?
    let member_since: String
    let friendship_since: String

    // Mini profile stats
    let age: Int?
    let achievements_count: Int?
    let total_trips: Int?
    let total_adventure_hours: Int?
    let favorite_activity_name: String?
    let favorite_activity_icon: String?

    var id: Int { user_id }

    var fullName: String {
        if last_name.isEmpty {
            return first_name
        }
        return "\(first_name) \(last_name)"
    }

    var memberSinceDate: Date? {
        DateUtils.parseISO8601(member_since)
    }

    var friendshipSinceDate: Date? {
        DateUtils.parseISO8601(friendship_since)
    }

    /// Formatted adventure time (e.g., "5d 3h", "2d", or "12h")
    /// Returns nil if hours is 0 or nil
    var formattedAdventureTime: String? {
        guard let hours = total_adventure_hours, hours > 0 else { return nil }
        if hours >= 24 {
            let days = hours / 24
            let remainingHours = hours % 24
            if remainingHours == 0 {
                return "\(days)d"
            }
            return "\(days)d \(remainingHours)h"
        }
        return "\(hours)h"
    }
}

/// Response when creating a friend invite
struct FriendInvite: Codable {
    let token: String
    let invite_url: String
    let expires_at: String

    var expiresAtDate: Date? {
        DateUtils.parseISO8601(expires_at)
    }
}

/// Preview of a friend invite (for accepting)
struct FriendInvitePreview: Codable {
    let inviter_first_name: String
    let inviter_profile_photo_url: String?
    let inviter_member_since: String
    let expires_at: String
    let is_valid: Bool

    var inviterMemberSinceDate: Date? {
        DateUtils.parseISO8601(inviter_member_since)
    }

    var expiresAtDate: Date? {
        DateUtils.parseISO8601(expires_at)
    }
}

/// A pending invite the user has sent
struct PendingInvite: Codable, Identifiable {
    let id: Int
    let token: String
    let created_at: String
    let expires_at: String
    let status: String  // "pending", "accepted", "expired"
    let accepted_by_name: String?

    var createdAtDate: Date? {
        DateUtils.parseISO8601(created_at)
    }

    var expiresAtDate: Date? {
        DateUtils.parseISO8601(expires_at)
    }

    var isPending: Bool { status == "pending" }
    var isAccepted: Bool { status == "accepted" }
    var isExpired: Bool { status == "expired" }
}

// MARK: - Friend Active Trips

/// Activity colors for friend trips
struct FriendTripActivityColors: Codable {
    let primary: String
    let secondary: String
    let accent: String
}

/// Owner info for a friend's active trip
struct FriendActiveTripOwner: Codable {
    let user_id: Int
    let first_name: String
    let last_name: String
    let profile_photo_url: String?

    var fullName: String {
        if last_name.isEmpty { return first_name }
        return "\(first_name) \(last_name)"
    }
}

/// A check-in event with location data for friends to see on a map
struct CheckinLocation: Codable, Identifiable {
    let timestamp: String
    let latitude: Double?
    let longitude: Double?
    let location_name: String?

    var id: String { timestamp }

    var timestampDate: Date? {
        DateUtils.parseISO8601(timestamp)
    }

    var coordinate: CLLocationCoordinate2D? {
        guard let lat = latitude, let lon = longitude else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}

/// Real-time location data for friends to track during a trip
struct LiveLocationData: Codable {
    let latitude: Double
    let longitude: Double
    let timestamp: String
    let speed: Double?

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var timestampDate: Date? {
        DateUtils.parseISO8601(timestamp)
    }
}

/// A trip where the current user is a friend safety contact
struct FriendActiveTrip: Codable, Identifiable {
    let id: Int
    let owner: FriendActiveTripOwner
    let title: String
    let activity_name: String
    let activity_icon: String
    let activity_colors: FriendTripActivityColors
    let status: String
    let start: String
    let eta: String
    let grace_min: Int
    let location_text: String?
    let start_location_text: String?
    let notes: String?
    let timezone: String?
    let last_checkin_at: String?

    // Enhanced friend visibility fields
    let checkin_locations: [CheckinLocation]?
    let live_location: LiveLocationData?
    let destination_lat: Double?
    let destination_lon: Double?
    let start_lat: Double?
    let start_lon: Double?
    let has_pending_update_request: Bool?

    var startDate: Date? { DateUtils.parseISO8601(start) }
    var etaDate: Date? { DateUtils.parseISO8601(eta) }
    var lastCheckinDate: Date? {
        guard let checkin = last_checkin_at else { return nil }
        return DateUtils.parseISO8601(checkin)
    }

    var isActive: Bool { status == "active" }
    var isPlanned: Bool { status == "planned" }
    var isOverdue: Bool { status == "overdue" || status == "overdue_notified" }
    var contactsNotified: Bool { status == "overdue_notified" }

    /// True if trip has an active status (not planned)
    var isActiveStatus: Bool {
        status == "active" || status == "overdue" || status == "overdue_notified"
    }

    /// Primary color from activity
    var primaryColor: Color {
        Color(hex: activity_colors.primary) ?? .hbBrand
    }

    /// Most recent check-in location
    var lastCheckinLocation: CheckinLocation? {
        checkin_locations?.first
    }

    /// Destination coordinate for map display
    var destinationCoordinate: CLLocationCoordinate2D? {
        guard let lat = destination_lat, let lon = destination_lon else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    /// Start location coordinate for map display
    var startCoordinate: CLLocationCoordinate2D? {
        guard let lat = start_lat, let lon = start_lon else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    /// True if trip has any location data to display on a map
    var hasLocationData: Bool {
        destinationCoordinate != nil || startCoordinate != nil ||
        (checkin_locations?.contains { $0.coordinate != nil } ?? false) ||
        live_location != nil
    }
}

/// Response from requesting an update from a trip owner
struct UpdateRequestResponse: Codable {
    let ok: Bool
    let message: String
    let cooldown_remaining_seconds: Int?
}

/// Friend visibility settings (global per-user)
struct FriendVisibilitySettings: Codable {
    var friend_share_checkin_locations: Bool
    var friend_share_live_location: Bool
    var friend_share_notes: Bool
    var friend_allow_update_requests: Bool
    var friend_share_achievements: Bool

    /// Default settings for new users
    static var defaults: FriendVisibilitySettings {
        FriendVisibilitySettings(
            friend_share_checkin_locations: true,
            friend_share_live_location: false,
            friend_share_notes: true,
            friend_allow_update_requests: true,
            friend_share_achievements: true
        )
    }
}

/// A single achievement from a friend's profile
struct FriendAchievement: Codable, Identifiable {
    let id: String
    let title: String
    let description: String
    let category: String
    let sf_symbol: String
    let threshold: Int
    let unit: String
    let is_earned: Bool
    let earned_date: String?
    let current_value: Int

    /// Parse earned_date string to Date
    var earnedDateValue: Date? {
        guard let dateStr = earned_date else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: dateStr) {
            return date
        }
        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: dateStr)
    }

    /// Map category string to AchievementCategory enum
    var categoryEnum: AchievementCategory? {
        switch category {
        case "totalTrips": return .totalTrips
        case "adventureTime": return .adventureTime
        case "activitiesTried": return .activitiesTried
        case "locations": return .locations
        case "timeBased": return .timeBased
        default: return nil
        }
    }
}

/// Full achievements response for a friend
struct FriendAchievementsResponse: Codable {
    let user_id: Int
    let friend_name: String
    let achievements: [FriendAchievement]
    let earned_count: Int
    let total_count: Int
}

/// Unified safety contact - can be either an email contact or a friend
enum SafetyContact: Identifiable, Hashable {
    case emailContact(Contact)
    case friend(Friend)

    var id: String {
        switch self {
        case .emailContact(let contact):
            return "contact-\(contact.id)"
        case .friend(let friend):
            return "friend-\(friend.user_id)"
        }
    }

    var displayName: String {
        switch self {
        case .emailContact(let contact):
            return contact.name
        case .friend(let friend):
            return friend.fullName
        }
    }

    var isEmailContact: Bool {
        if case .emailContact = self { return true }
        return false
    }

    var isFriend: Bool {
        if case .friend = self { return true }
        return false
    }

    /// Icon name for this contact type
    var iconName: String {
        switch self {
        case .emailContact:
            return "envelope.fill"  // Email contacts get email notifications
        case .friend:
            return "bell.fill"  // Friends get push notifications
        }
    }
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
    var start_location_text: String?  // Optional start location for trips with separate start/end
    var start_lat: Double?
    var start_lon: Double?
    var has_separate_locations: Bool = false  // True if trip has separate start and destination
    var notes: String?
    var contact1: Int?
    var contact2: Int?
    var contact3: Int?
    var friend_contact1: Int?  // Friend user ID for push notifications
    var friend_contact2: Int?
    var friend_contact3: Int?
    var timezone: String?  // User's timezone (e.g., "America/New_York") - used for notifications
    var start_timezone: String?  // Timezone for start time (e.g., "America/Los_Angeles")
    var eta_timezone: String?    // Timezone for return time (e.g., "America/New_York")
    var checkin_interval_min: Int = 30  // Minutes between check-in reminders
    var notify_start_hour: Int?  // Hour (0-23) when notifications start (nil = no restriction)
    var notify_end_hour: Int?    // Hour (0-23) when notifications end (nil = no restriction)
    var notify_self: Bool = false  // Send copy of all emails to trip owner
    var share_live_location: Bool = false  // Share live location with friends during trip
}

struct TripUpdateRequest: Codable {
    var title: String?
    var activity: String?
    var start: Date?
    var eta: Date?
    var grace_min: Int?
    var location_text: String?
    var gen_lat: Double?
    var gen_lon: Double?
    var start_location_text: String?
    var start_lat: Double?
    var start_lon: Double?
    var has_separate_locations: Bool?
    var notes: String?
    var contact1: Int?
    var contact2: Int?
    var contact3: Int?
    var friend_contact1: Int?  // Friend user ID for push notifications
    var friend_contact2: Int?
    var friend_contact3: Int?
    var timezone: String?
    var start_timezone: String?
    var eta_timezone: String?
    var checkin_interval_min: Int?
    var notify_start_hour: Int?
    var notify_end_hour: Int?
    var notify_self: Bool?  // Send copy of all emails to trip owner
    var share_live_location: Bool?  // Share live location with friends during trip
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
    var start_location_text: String?  // Optional start location for trips with separate start/end
    var start_lat: Double?
    var start_lng: Double?  // Maps from backend 'start_lon'
    var has_separate_locations: Bool  // True if trip has separate start and destination
    var notes: String?
    var status: String
    var completed_at: Date?
    var last_checkin: String?
    var created_at: String
    var contact1: Int?
    var contact2: Int?
    var contact3: Int?
    var friend_contact1: Int?  // Friend user ID for push notifications
    var friend_contact2: Int?
    var friend_contact3: Int?
    var checkin_token: String?
    var checkout_token: String?
    var checkin_interval_min: Int?  // Minutes between check-in reminders (nil = default 30)
    var notify_start_hour: Int?     // Hour (0-23) when notifications start (nil = no restriction)
    var notify_end_hour: Int?       // Hour (0-23) when notifications end (nil = no restriction)
    var timezone: String?           // User's timezone for notifications
    var start_timezone: String?     // Timezone for start time
    var eta_timezone: String?       // Timezone for return time
    var notify_self: Bool           // Send copy of all emails to trip owner
    var share_live_location: Bool   // Share live location with friends during trip

    // Legacy field name for backward compatibility
    var activity_type: String { activity.name }

    enum CodingKeys: String, CodingKey {
        case id, user_id, title, activity, status, notes
        case start, eta
        case grace_min
        case location_text
        case gen_lat, gen_lon
        case start_location_text, start_lat, start_lon, has_separate_locations
        case completed_at, last_checkin, created_at
        case contact1, contact2, contact3
        case friend_contact1, friend_contact2, friend_contact3
        case checkin_token, checkout_token
        case checkin_interval_min, notify_start_hour, notify_end_hour
        case timezone, start_timezone, eta_timezone, notify_self, share_live_location
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

        guard let parsedStart = DateUtils.parseISO8601(startString) else {
            throw DecodingError.dataCorruptedError(
                forKey: .start,
                in: container,
                debugDescription: "Failed to parse start date: '\(startString)'"
            )
        }
        guard let parsedEta = DateUtils.parseISO8601(etaString) else {
            throw DecodingError.dataCorruptedError(
                forKey: .eta,
                in: container,
                debugDescription: "Failed to parse eta date: '\(etaString)'"
            )
        }
        start_at = parsedStart
        eta_at = parsedEta

        grace_minutes = try container.decode(Int.self, forKey: .grace_min)
        location_text = try container.decodeIfPresent(String.self, forKey: .location_text)
        location_lat = try container.decodeIfPresent(Double.self, forKey: .gen_lat)
        location_lng = try container.decodeIfPresent(Double.self, forKey: .gen_lon)
        start_location_text = try container.decodeIfPresent(String.self, forKey: .start_location_text)
        start_lat = try container.decodeIfPresent(Double.self, forKey: .start_lat)
        start_lng = try container.decodeIfPresent(Double.self, forKey: .start_lon)
        has_separate_locations = try container.decodeIfPresent(Bool.self, forKey: .has_separate_locations) ?? false
        notes = try container.decodeIfPresent(String.self, forKey: .notes)
        status = try container.decode(String.self, forKey: .status)

        // Parse completed_at date string if present
        if let completedAtString = try container.decodeIfPresent(String.self, forKey: .completed_at) {
            debugLog("[Trip Decoder] ✅ completed_at string received: '\(completedAtString)' for trip id=\(id)")
            completed_at = DateUtils.parseISO8601(completedAtString)
            if let parsedDate = completed_at {
                debugLog("[Trip Decoder] ✅ completed_at parsed successfully: \(parsedDate)")
            } else {
                debugLog("[Trip Decoder] ❌ completed_at parsing FAILED for string: '\(completedAtString)'")
            }
        } else {
            debugLog("[Trip Decoder] ⚠️ completed_at is nil/missing from API for trip id=\(id), status=\(status)")
            completed_at = nil
        }

        last_checkin = try container.decodeIfPresent(String.self, forKey: .last_checkin)
        created_at = try container.decode(String.self, forKey: .created_at)
        contact1 = try container.decodeIfPresent(Int.self, forKey: .contact1)
        contact2 = try container.decodeIfPresent(Int.self, forKey: .contact2)
        contact3 = try container.decodeIfPresent(Int.self, forKey: .contact3)
        friend_contact1 = try container.decodeIfPresent(Int.self, forKey: .friend_contact1)
        friend_contact2 = try container.decodeIfPresent(Int.self, forKey: .friend_contact2)
        friend_contact3 = try container.decodeIfPresent(Int.self, forKey: .friend_contact3)
        checkin_token = try container.decodeIfPresent(String.self, forKey: .checkin_token)
        checkout_token = try container.decodeIfPresent(String.self, forKey: .checkout_token)
        checkin_interval_min = try container.decodeIfPresent(Int.self, forKey: .checkin_interval_min)
        notify_start_hour = try container.decodeIfPresent(Int.self, forKey: .notify_start_hour)
        notify_end_hour = try container.decodeIfPresent(Int.self, forKey: .notify_end_hour)
        timezone = try container.decodeIfPresent(String.self, forKey: .timezone)
        start_timezone = try container.decodeIfPresent(String.self, forKey: .start_timezone)
        eta_timezone = try container.decodeIfPresent(String.self, forKey: .eta_timezone)
        notify_self = try container.decodeIfPresent(Bool.self, forKey: .notify_self) ?? false
        share_live_location = try container.decodeIfPresent(Bool.self, forKey: .share_live_location) ?? false
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
        try container.encodeIfPresent(start_location_text, forKey: .start_location_text)
        try container.encodeIfPresent(start_lat, forKey: .start_lat)
        try container.encodeIfPresent(start_lng, forKey: .start_lon)
        try container.encode(has_separate_locations, forKey: .has_separate_locations)
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
        try container.encodeIfPresent(friend_contact1, forKey: .friend_contact1)
        try container.encodeIfPresent(friend_contact2, forKey: .friend_contact2)
        try container.encodeIfPresent(friend_contact3, forKey: .friend_contact3)
        try container.encodeIfPresent(checkin_token, forKey: .checkin_token)
        try container.encodeIfPresent(checkout_token, forKey: .checkout_token)
        try container.encodeIfPresent(checkin_interval_min, forKey: .checkin_interval_min)
        try container.encodeIfPresent(notify_start_hour, forKey: .notify_start_hour)
        try container.encodeIfPresent(notify_end_hour, forKey: .notify_end_hour)
        try container.encodeIfPresent(timezone, forKey: .timezone)
        try container.encodeIfPresent(start_timezone, forKey: .start_timezone)
        try container.encodeIfPresent(eta_timezone, forKey: .eta_timezone)
        try container.encode(notify_self, forKey: .notify_self)
        try container.encode(share_live_location, forKey: .share_live_location)
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
        start_location_text: String? = nil,
        start_lat: Double? = nil,
        start_lng: Double? = nil,
        has_separate_locations: Bool = false,
        notes: String?,
        status: String,
        completed_at: Date?,
        last_checkin: String?,
        created_at: String,
        contact1: Int?,
        contact2: Int?,
        contact3: Int?,
        friend_contact1: Int? = nil,
        friend_contact2: Int? = nil,
        friend_contact3: Int? = nil,
        checkin_token: String?,
        checkout_token: String?,
        checkin_interval_min: Int? = nil,
        notify_start_hour: Int? = nil,
        notify_end_hour: Int? = nil,
        timezone: String? = nil,
        start_timezone: String? = nil,
        eta_timezone: String? = nil,
        notify_self: Bool = false,
        share_live_location: Bool = false
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
        self.start_location_text = start_location_text
        self.start_lat = start_lat
        self.start_lng = start_lng
        self.has_separate_locations = has_separate_locations
        self.notes = notes
        self.status = status
        self.completed_at = completed_at
        self.last_checkin = last_checkin
        self.created_at = created_at
        self.contact1 = contact1
        self.contact2 = contact2
        self.contact3 = contact3
        self.friend_contact1 = friend_contact1
        self.friend_contact2 = friend_contact2
        self.friend_contact3 = friend_contact3
        self.checkin_token = checkin_token
        self.checkout_token = checkout_token
        self.checkin_interval_min = checkin_interval_min
        self.notify_start_hour = notify_start_hour
        self.notify_end_hour = notify_end_hour
        self.timezone = timezone
        self.start_timezone = start_timezone
        self.eta_timezone = eta_timezone
        self.notify_self = notify_self
        self.share_live_location = share_live_location
    }
}

// MARK: - Trip Mutation Helper

extension Trip {
    /// Creates a copy of the Trip with specified fields updated.
    /// All other fields are preserved from the original Trip.
    /// Use this instead of the memberwise initializer to avoid losing field values.
    func with(
        status: String? = nil,
        eta_at: Date? = nil,
        completed_at: Date?? = nil,
        last_checkin: String?? = nil,
        checkin_token: String?? = nil,
        checkout_token: String?? = nil
    ) -> Trip {
        var copy = self
        if let status = status { copy.status = status }
        if let eta_at = eta_at { copy.eta_at = eta_at }
        if let completed_at = completed_at { copy.completed_at = completed_at }
        if let last_checkin = last_checkin { copy.last_checkin = last_checkin }
        if let checkin_token = checkin_token { copy.checkin_token = checkin_token }
        if let checkout_token = checkout_token { copy.checkout_token = checkout_token }
        return copy
    }
}

struct TimelineResponse: Codable {
    var plan_id: Int
    var events: [TimelineEvent]
}

struct TimelineEvent: Codable, Identifiable {
    // Use the full ISO8601 string for better uniqueness (includes fractional seconds)
    var id: String { "\(kind)-\(at)" }
    var kind: String
    var at: String  // ISO8601 string from backend
    var lat: Double?
    var lon: Double?
    var extended_by: Int?

    // Computed property to get Date - uses DateUtils for robust parsing
    var atDate: Date? {
        DateUtils.parseISO8601(at)
    }

    // Memberwise initializer for LocalStorage
    init(kind: String, at: String, lat: Double?, lon: Double?, extended_by: Int?) {
        self.kind = kind
        self.at = at
        self.lat = lat
        self.lon = lon
        self.extended_by = extended_by
    }
}

// MARK: - Saved Trip Template (local-only)

/// A saved trip template for quick trip creation
/// Stores all trip data EXCEPT times/dates
struct SavedTripTemplate: Codable, Identifiable {
    let id: UUID
    var name: String                    // Template display name (can differ from title)
    var title: String                   // Pre-filled trip title
    var activityId: Int                 // Activity ID (references Activity.id)
    var locationText: String?           // Destination location text
    var locationLat: Double?
    var locationLng: Double?
    var startLocationText: String?      // Start location for separate start/destination
    var startLat: Double?
    var startLng: Double?
    var hasSeparateLocations: Bool
    var graceMinutes: Int
    var notes: String?
    var contact1Id: Int?                // Saved contact IDs (email contacts)
    var contact2Id: Int?
    var contact3Id: Int?
    var friendContact1Id: Int?          // Friend user IDs (push notification contacts)
    var friendContact2Id: Int?
    var friendContact3Id: Int?
    var checkinIntervalMinutes: Int
    var useNotificationHours: Bool
    var notifyStartHour: Int?
    var notifyEndHour: Int?
    var notifySelf: Bool
    var createdAt: Date
    var lastUsedAt: Date?

    init(
        id: UUID = UUID(),
        name: String,
        title: String,
        activityId: Int,
        locationText: String? = nil,
        locationLat: Double? = nil,
        locationLng: Double? = nil,
        startLocationText: String? = nil,
        startLat: Double? = nil,
        startLng: Double? = nil,
        hasSeparateLocations: Bool = false,
        graceMinutes: Int = 30,
        notes: String? = nil,
        contact1Id: Int? = nil,
        contact2Id: Int? = nil,
        contact3Id: Int? = nil,
        friendContact1Id: Int? = nil,
        friendContact2Id: Int? = nil,
        friendContact3Id: Int? = nil,
        checkinIntervalMinutes: Int = 30,
        useNotificationHours: Bool = false,
        notifyStartHour: Int? = nil,
        notifyEndHour: Int? = nil,
        notifySelf: Bool = false,
        createdAt: Date = Date(),
        lastUsedAt: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.title = title
        self.activityId = activityId
        self.locationText = locationText
        self.locationLat = locationLat
        self.locationLng = locationLng
        self.startLocationText = startLocationText
        self.startLat = startLat
        self.startLng = startLng
        self.hasSeparateLocations = hasSeparateLocations
        self.graceMinutes = graceMinutes
        self.notes = notes
        self.contact1Id = contact1Id
        self.contact2Id = contact2Id
        self.contact3Id = contact3Id
        self.friendContact1Id = friendContact1Id
        self.friendContact2Id = friendContact2Id
        self.friendContact3Id = friendContact3Id
        self.checkinIntervalMinutes = checkinIntervalMinutes
        self.useNotificationHours = useNotificationHours
        self.notifyStartHour = notifyStartHour
        self.notifyEndHour = notifyEndHour
        self.notifySelf = notifySelf
        self.createdAt = createdAt
        self.lastUsedAt = lastUsedAt
    }
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
        Color(hex: activity.colors.primary) ?? .hbBrand
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
