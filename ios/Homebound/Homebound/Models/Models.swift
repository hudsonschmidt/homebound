import Foundation

struct ContactIn: Codable {
    var name: String
    var phone: String?
    var email: String?
    var notify_on_overdue: Bool = true
}

// MARK: - Saved Contact Model (for user's saved contacts)
struct SavedContact: Identifiable, Codable {
    let id: String
    let name: String
    let phone: String
    let email: String?
}

struct ContactCreate: Codable {
    var name: String
    var phone: String
    var email: String?
}

struct PlanCreate: Codable {
    var title: String
    var activity_type: String = "other"
    var start_at: Date
    var eta_at: Date
    var grace_minutes: Int = 30
    var location_text: String?
    var location_lat: Double?
    var location_lng: Double?
    var notes: String?
    var contacts: [ContactIn] = []
}

struct PlanOut: Codable, Identifiable, Equatable {
    var id: Int
    var title: String
    var activity_type: String
    var start_at: Date
    var eta_at: Date
    var grace_minutes: Int
    var location_text: String?
    var notes: String?
    var status: String
    var checkin_token: String
    var checkout_token: String
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
