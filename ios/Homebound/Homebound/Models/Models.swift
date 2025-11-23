import Foundation

struct ContactIn: Codable {
    var name: String
    var phone: String?
    var email: String?
    var notify_on_overdue: Bool = true
}

// MARK: - Saved Contact Model (for user's saved contacts)
struct SavedContact: Identifiable, Codable {
    let id: Int
    let user_id: Int
    let name: String
    let phone: String?
    let email: String?
}

struct ContactCreate: Codable {
    var name: String
    var phone: String?
    var email: String?
}

struct PlanCreate: Codable {
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

struct PlanOut: Codable, Identifiable, Equatable {
    var id: Int
    var user_id: Int
    var title: String
    var activity: String
    var start_at: Date  // Computed from backend 'start'
    var eta_at: Date    // Computed from backend 'eta'
    var grace_minutes: Int  // Maps from backend 'grace_min'
    var location_text: String?
    var location_lat: Double?  // Maps from backend 'gen_lat'
    var location_lng: Double?  // Maps from backend 'gen_lon'
    var notes: String?
    var status: String
    var completed_at: String?
    var last_checkin: String?
    var created_at: String
    var contact1: Int?
    var contact2: Int?
    var contact3: Int?
    var checkin_token: String?
    var checkout_token: String?

    // Legacy field name for backward compatibility
    var activity_type: String { activity }

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
        activity = try container.decode(String.self, forKey: .activity)

        // Parse date strings
        let startString = try container.decode(String.self, forKey: .start)
        let etaString = try container.decode(String.self, forKey: .eta)

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        start_at = formatter.date(from: startString) ?? Date()
        eta_at = formatter.date(from: etaString) ?? Date()

        grace_minutes = try container.decode(Int.self, forKey: .grace_min)
        location_text = try container.decodeIfPresent(String.self, forKey: .location_text)
        location_lat = try container.decodeIfPresent(Double.self, forKey: .gen_lat)
        location_lng = try container.decodeIfPresent(Double.self, forKey: .gen_lon)
        notes = try container.decodeIfPresent(String.self, forKey: .notes)
        status = try container.decode(String.self, forKey: .status)
        completed_at = try container.decodeIfPresent(String.self, forKey: .completed_at)
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
        try container.encodeIfPresent(completed_at, forKey: .completed_at)
        try container.encodeIfPresent(last_checkin, forKey: .last_checkin)
        try container.encode(created_at, forKey: .created_at)
        try container.encodeIfPresent(contact1, forKey: .contact1)
        try container.encodeIfPresent(contact2, forKey: .contact2)
        try container.encodeIfPresent(contact3, forKey: .contact3)
        try container.encodeIfPresent(checkin_token, forKey: .checkin_token)
        try container.encodeIfPresent(checkout_token, forKey: .checkout_token)
    }

    /// Memberwise initializer for local storage
    init(
        id: Int,
        user_id: Int,
        title: String,
        activity: String,
        start_at: Date,
        eta_at: Date,
        grace_minutes: Int,
        location_text: String?,
        location_lat: Double?,
        location_lng: Double?,
        notes: String?,
        status: String,
        completed_at: String?,
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
