import XCTest
@testable import Homebound

final class TripModelsTests: XCTestCase {

    // MARK: - Trip Decoding Tests

    func testTrip_DecodesFromFullJSON() throws {
        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: TestFixtures.tripJSON)

        XCTAssertEqual(trip.id, 1)
        XCTAssertEqual(trip.user_id, 100)
        XCTAssertEqual(trip.title, "Morning Hike")
        XCTAssertEqual(trip.activity.name, "Hiking")
        XCTAssertEqual(trip.grace_minutes, 30)
        XCTAssertEqual(trip.status, "active")
        XCTAssertEqual(trip.location_text, "Mt. Tamalpais")
        XCTAssertEqual(trip.location_lat, 37.9235)
        XCTAssertEqual(trip.location_lng, -122.5965)
        XCTAssertEqual(trip.notes, "Taking the Dipsea trail")
        XCTAssertFalse(trip.has_separate_locations)
        XCTAssertFalse(trip.notify_self)
        XCTAssertFalse(trip.share_live_location)
        XCTAssertFalse(trip.is_group_trip)
    }

    func testTrip_DecodesFromMinimalJSON() throws {
        let minimalJSON = """
        {
            "id": 1,
            "user_id": 100,
            "title": "Test",
            "activity": {
                "id": 1,
                "name": "Other",
                "icon": "figure.walk",
                "default_grace_minutes": 30,
                "colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
                "messages": {"start": "", "checkin": "", "checkout": "", "overdue": "", "encouragement": []},
                "safety_tips": [],
                "order": 1
            },
            "start": "2025-12-05T10:30:00Z",
            "eta": "2025-12-05T14:30:00Z",
            "grace_min": 30,
            "status": "planned",
            "created_at": "2025-12-05T08:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: minimalJSON)

        XCTAssertEqual(trip.id, 1)
        XCTAssertEqual(trip.status, "planned")
        XCTAssertNil(trip.location_text)
        XCTAssertNil(trip.notes)
        XCTAssertFalse(trip.has_separate_locations) // Defaults to false
        XCTAssertFalse(trip.notify_self) // Defaults to false
        XCTAssertFalse(trip.is_group_trip) // Defaults to false
        XCTAssertEqual(trip.participant_count, 0) // Defaults to 0
    }

    func testTrip_DecodesStart_ISO8601WithFractionalSeconds() throws {
        let json = """
        {
            "id": 1,
            "user_id": 100,
            "title": "Test",
            "activity": {
                "id": 1,
                "name": "Other",
                "icon": "figure.walk",
                "default_grace_minutes": 30,
                "colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
                "messages": {"start": "", "checkin": "", "checkout": "", "overdue": "", "encouragement": []},
                "safety_tips": [],
                "order": 1
            },
            "start": "2025-12-05T10:30:00.123456Z",
            "eta": "2025-12-05T14:30:00.123456Z",
            "grace_min": 30,
            "status": "active",
            "created_at": "2025-12-05T08:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: json)

        XCTAssertNotNil(trip.start_at)
    }

    func testTrip_DecodesStart_PythonFormat() throws {
        let json = """
        {
            "id": 1,
            "user_id": 100,
            "title": "Test",
            "activity": {
                "id": 1,
                "name": "Other",
                "icon": "figure.walk",
                "default_grace_minutes": 30,
                "colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
                "messages": {"start": "", "checkin": "", "checkout": "", "overdue": "", "encouragement": []},
                "safety_tips": [],
                "order": 1
            },
            "start": "2025-12-05T10:30:00",
            "eta": "2025-12-05T14:30:00",
            "grace_min": 30,
            "status": "active",
            "created_at": "2025-12-05T08:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: json)

        XCTAssertNotNil(trip.start_at)
    }

    func testTrip_DecodesFails_InvalidStartDate() {
        let json = """
        {
            "id": 1,
            "user_id": 100,
            "title": "Test",
            "activity": {
                "id": 1,
                "name": "Other",
                "icon": "figure.walk",
                "default_grace_minutes": 30,
                "colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
                "messages": {"start": "", "checkin": "", "checkout": "", "overdue": "", "encouragement": []},
                "safety_tips": [],
                "order": 1
            },
            "start": "not-a-date",
            "eta": "2025-12-05T14:30:00Z",
            "grace_min": 30,
            "status": "active",
            "created_at": "2025-12-05T08:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()

        XCTAssertThrowsError(try decoder.decode(Trip.self, from: json))
    }

    func testTrip_DecodesCompletedAt_WhenPresent() throws {
        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: TestFixtures.tripJSONWithCompletedAt)

        XCTAssertNotNil(trip.completed_at)
        XCTAssertEqual(trip.status, "completed")
    }

    func testTrip_DecodesCompletedAt_WhenNull() throws {
        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: TestFixtures.tripJSON)

        XCTAssertNil(trip.completed_at)
    }

    func testTrip_DecodesGroupSettings_WhenPresent() throws {
        let json = """
        {
            "id": 1,
            "user_id": 100,
            "title": "Group Trip",
            "activity": {
                "id": 1,
                "name": "Hiking",
                "icon": "figure.hiking",
                "default_grace_minutes": 30,
                "colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
                "messages": {"start": "", "checkin": "", "checkout": "", "overdue": "", "encouragement": []},
                "safety_tips": [],
                "order": 1
            },
            "start": "2025-12-05T10:30:00Z",
            "eta": "2025-12-05T14:30:00Z",
            "grace_min": 30,
            "status": "active",
            "created_at": "2025-12-05T08:00:00Z",
            "is_group_trip": true,
            "group_settings": {
                "checkout_mode": "vote",
                "vote_threshold": 0.75,
                "allow_participant_invites": true,
                "share_locations_between_participants": true
            },
            "participant_count": 3
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: json)

        XCTAssertTrue(trip.is_group_trip)
        XCTAssertNotNil(trip.group_settings)
        XCTAssertEqual(trip.group_settings?.checkout_mode, "vote")
        XCTAssertEqual(trip.group_settings?.vote_threshold, 0.75)
        XCTAssertEqual(trip.participant_count, 3)
    }

    // MARK: - Trip.with() Mutation Helper Tests

    func testTrip_With_UpdatesStatus() {
        let trip = TestFixtures.makeTrip(status: "active")
        let updated = trip.with(status: "completed")

        XCTAssertEqual(updated.status, "completed")
        XCTAssertEqual(updated.title, trip.title) // Other fields preserved
    }

    func testTrip_With_UpdatesEtaAt() {
        let trip = TestFixtures.makeTrip()
        let newEta = Date().addingTimeInterval(7200)
        let updated = trip.with(eta_at: newEta)

        XCTAssertEqual(updated.eta_at, newEta)
        XCTAssertEqual(updated.status, trip.status) // Other fields preserved
    }

    func testTrip_With_PreservesOtherFields() {
        let trip = TestFixtures.makeTrip(
            title: "Original Title",
            status: "active",
            locationText: "Original Location"
        )

        let updated = trip.with(status: "completed")

        XCTAssertEqual(updated.title, "Original Title")
        XCTAssertEqual(updated.location_text, "Original Location")
        XCTAssertEqual(updated.status, "completed")
    }

    func testTrip_With_HandlesOptionalOptional_CompletedAt() {
        let trip = TestFixtures.makeTrip(completedAt: nil)
        let now = Date()

        // Set completed_at
        let updated1 = trip.with(completed_at: now)
        XCTAssertEqual(updated1.completed_at, now)

        // Set completed_at to nil
        let updated2 = updated1.with(completed_at: .some(nil))
        XCTAssertNil(updated2.completed_at)
    }

    func testTrip_With_EtaAtCreatesDistinctStruct() {
        // This test verifies that Trip.with(eta_at:) creates a new struct
        // that is not equal to the original - critical for UI update detection
        let originalEta = Date()
        let trip = TestFixtures.makeTrip(etaAt: originalEta)
        let newEta = originalEta.addingTimeInterval(1800) // 30 minutes later

        let updated = trip.with(eta_at: newEta)

        // The updated trip should be a new struct, not the same reference
        XCTAssertNotEqual(trip.eta_at, updated.eta_at)
        XCTAssertEqual(updated.eta_at, newEta)

        // The original should be unchanged (value type semantics)
        XCTAssertEqual(trip.eta_at, originalEta)
    }

    func testTrip_With_EtaAtChangeMakesTripsNotEqual() {
        // This test ensures Equatable detects eta_at changes
        // Important for SwiftUI change detection
        let fixedStart = Date(timeIntervalSince1970: 1000000)
        let originalEta = Date(timeIntervalSince1970: 1000000 + 3600)
        let newEta = Date(timeIntervalSince1970: 1000000 + 7200)

        let trip1 = TestFixtures.makeTrip(id: 1, startAt: fixedStart, etaAt: originalEta)
        let trip2 = trip1.with(eta_at: newEta)

        // Same ID but different eta_at should NOT be equal
        XCTAssertEqual(trip1.id, trip2.id)
        XCTAssertNotEqual(trip1, trip2)
    }

    // MARK: - Trip Computed Properties Tests

    func testTrip_ActivityType_ReturnsActivityName() throws {
        let decoder = JSONDecoder()
        let trip = try decoder.decode(Trip.self, from: TestFixtures.tripJSON)

        XCTAssertEqual(trip.activity_type, "Hiking")
    }

    func testTrip_IsGroupTrip_ComputedProperty() {
        let trip = TestFixtures.makeTrip()
        XCTAssertEqual(trip.isGroupTrip, trip.is_group_trip)
    }

    func testTrip_HasParticipants_True() {
        let trip = Trip(
            id: 1, user_id: 100, title: "Test", activity: TestFixtures.makeActivity(),
            start_at: Date(), eta_at: Date().addingTimeInterval(3600), grace_minutes: 30,
            location_text: nil, location_lat: nil, location_lng: nil, notes: nil,
            status: "active", completed_at: nil, last_checkin: nil, created_at: "",
            contact1: nil, contact2: nil, contact3: nil, checkin_token: nil, checkout_token: nil,
            is_group_trip: true, participant_count: 3
        )

        XCTAssertTrue(trip.hasParticipants)
    }

    func testTrip_HasParticipants_False() {
        let trip = TestFixtures.makeTrip()
        XCTAssertFalse(trip.hasParticipants)
    }

    // MARK: - Trip Equatable Tests

    func testTrip_Equatable() {
        // Use fixed dates so both trips are identical
        let fixedStart = Date(timeIntervalSince1970: 1000000)
        let fixedEta = Date(timeIntervalSince1970: 1000000 + 3600)

        let trip1 = TestFixtures.makeTrip(id: 1, startAt: fixedStart, etaAt: fixedEta)
        let trip2 = TestFixtures.makeTrip(id: 1, startAt: fixedStart, etaAt: fixedEta)
        let trip3 = TestFixtures.makeTrip(id: 2, startAt: fixedStart, etaAt: fixedEta)

        XCTAssertEqual(trip1, trip2)
        XCTAssertNotEqual(trip1, trip3)
    }

    // MARK: - Activity Model Tests

    func testActivity_DecodesFromJSON() throws {
        let decoder = JSONDecoder()
        let activity = try decoder.decode(Activity.self, from: TestFixtures.activityJSON)

        XCTAssertEqual(activity.id, 1)
        XCTAssertEqual(activity.name, "Hiking")
        XCTAssertEqual(activity.icon, "figure.hiking")
        XCTAssertEqual(activity.default_grace_minutes, 30)
        XCTAssertEqual(activity.colors.primary, "#4CAF50")
        XCTAssertEqual(activity.messages.start, "Have a great hike!")
        XCTAssertEqual(activity.safety_tips.count, 2)
    }

    // MARK: - Contact Model Tests

    func testContact_DecodesFromJSON() throws {
        let decoder = JSONDecoder()
        let contact = try decoder.decode(Contact.self, from: TestFixtures.contactJSON)

        XCTAssertEqual(contact.id, 1)
        XCTAssertEqual(contact.user_id, 100)
        XCTAssertEqual(contact.name, "Emergency Contact")
        XCTAssertEqual(contact.email, "emergency@example.com")
    }

    func testContactCreateRequest_EncodesToJSON() throws {
        let request = ContactCreateRequest(name: "Test Contact", email: "test@example.com")

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["name"] as? String, "Test Contact")
        XCTAssertEqual(json["email"] as? String, "test@example.com")
    }

    // MARK: - TimelineEvent Tests

    func testTimelineEvent_DecodesFromJSON() throws {
        let decoder = JSONDecoder()
        let event = try decoder.decode(TimelineEvent.self, from: TestFixtures.timelineEventJSON)

        XCTAssertEqual(event.kind, "checkin")
        XCTAssertEqual(event.lat, 37.9235)
        XCTAssertEqual(event.lon, -122.5965)
    }

    func testTimelineEvent_AtDateProperty_ParsesISO8601() throws {
        let decoder = JSONDecoder()
        let event = try decoder.decode(TimelineEvent.self, from: TestFixtures.timelineEventJSON)

        XCTAssertNotNil(event.atDate)
    }

    func testTimelineEvent_ID_UniqueByKindAndAt() throws {
        let event1 = TimelineEvent(kind: "checkin", at: "2025-12-05T12:30:00Z", lat: nil, lon: nil, extended_by: nil)
        let event2 = TimelineEvent(kind: "checkin", at: "2025-12-05T12:30:00Z", lat: nil, lon: nil, extended_by: nil)
        let event3 = TimelineEvent(kind: "checkout", at: "2025-12-05T12:30:00Z", lat: nil, lon: nil, extended_by: nil)

        XCTAssertEqual(event1.id, event2.id)
        XCTAssertNotEqual(event1.id, event3.id)
    }

    // MARK: - GroupSettings Tests

    func testGroupSettings_DecodesFromJSON() throws {
        let decoder = JSONDecoder()
        let settings = try decoder.decode(GroupSettings.self, from: TestFixtures.groupSettingsJSON)

        XCTAssertEqual(settings.checkout_mode, "anyone")
        XCTAssertEqual(settings.vote_threshold, 0.5)
        XCTAssertFalse(settings.allow_participant_invites)
        XCTAssertTrue(settings.share_locations_between_participants)
    }

    func testGroupSettings_Defaults() {
        let defaults = GroupSettings.defaults

        XCTAssertEqual(defaults.checkout_mode, "anyone")
        XCTAssertEqual(defaults.vote_threshold, 0.5)
        XCTAssertFalse(defaults.allow_participant_invites)
        XCTAssertTrue(defaults.share_locations_between_participants)
    }

    func testGroupSettings_Equatable() {
        let settings1 = GroupSettings.defaults
        let settings2 = GroupSettings.defaults

        XCTAssertEqual(settings1, settings2)
    }
}
