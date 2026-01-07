import XCTest
@testable import Homebound

final class RequestModelsTests: XCTestCase {

    // MARK: - TripCreateRequest Tests

    func testTripCreateRequest_EncodesToJSON() throws {
        let api = API()
        let request = TripCreateRequest(
            title: "Morning Hike",
            activity: "hiking",
            start: Date(timeIntervalSince1970: 1000000),
            eta: Date(timeIntervalSince1970: 1000000 + 14400),
            grace_min: 30,
            location_text: "Mt. Tamalpais",
            gen_lat: 37.9235,
            gen_lon: -122.5965
        )

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["title"] as? String, "Morning Hike")
        XCTAssertEqual(json["activity"] as? String, "hiking")
        XCTAssertEqual(json["grace_min"] as? Int, 30)
        XCTAssertEqual(json["location_text"] as? String, "Mt. Tamalpais")
        XCTAssertEqual(json["gen_lat"] as? Double, 37.9235)
        XCTAssertEqual(json["gen_lon"] as? Double, -122.5965)
    }

    func testTripCreateRequest_DefaultValues() {
        let request = TripCreateRequest(
            title: "Test",
            start: Date(),
            eta: Date().addingTimeInterval(3600)
        )

        XCTAssertEqual(request.activity, "other")
        XCTAssertEqual(request.grace_min, 30)
        XCTAssertFalse(request.has_separate_locations)
        XCTAssertEqual(request.checkin_interval_min, 30)
        XCTAssertFalse(request.notify_self)
        XCTAssertFalse(request.share_live_location)
        XCTAssertFalse(request.is_group_trip)
        XCTAssertNil(request.group_settings)
    }

    func testTripCreateRequest_WithSeparateLocations() throws {
        let api = API()
        let request = TripCreateRequest(
            title: "Road Trip",
            activity: "driving",
            start: Date(timeIntervalSince1970: 1000000),
            eta: Date(timeIntervalSince1970: 1000000 + 28800),
            location_text: "Destination City",
            gen_lat: 34.0522,
            gen_lon: -118.2437,
            start_location_text: "Start City",
            start_lat: 37.7749,
            start_lon: -122.4194,
            has_separate_locations: true
        )

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["location_text"] as? String, "Destination City")
        XCTAssertEqual(json["start_location_text"] as? String, "Start City")
        XCTAssertEqual(json["has_separate_locations"] as? Bool, true)
        XCTAssertNotNil(json["start_lat"])
        XCTAssertNotNil(json["start_lon"])
    }

    func testTripCreateRequest_WithContacts() throws {
        let api = API()
        let request = TripCreateRequest(
            title: "Test",
            start: Date(timeIntervalSince1970: 1000000),
            eta: Date(timeIntervalSince1970: 1000000 + 3600),
            contact1: 1,
            contact2: 2,
            contact3: nil,
            friend_contact1: 100,
            friend_contact2: nil,
            friend_contact3: nil
        )

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["contact1"] as? Int, 1)
        XCTAssertEqual(json["contact2"] as? Int, 2)
        XCTAssertEqual(json["friend_contact1"] as? Int, 100)
    }

    func testTripCreateRequest_WithTimezones() throws {
        let api = API()
        let request = TripCreateRequest(
            title: "Cross-Timezone Trip",
            start: Date(timeIntervalSince1970: 1000000),
            eta: Date(timeIntervalSince1970: 1000000 + 36000),
            timezone: "America/New_York",
            start_timezone: "America/Los_Angeles",
            eta_timezone: "America/New_York"
        )

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["timezone"] as? String, "America/New_York")
        XCTAssertEqual(json["start_timezone"] as? String, "America/Los_Angeles")
        XCTAssertEqual(json["eta_timezone"] as? String, "America/New_York")
    }

    func testTripCreateRequest_WithNotificationSettings() throws {
        let api = API()
        let request = TripCreateRequest(
            title: "Night Hike",
            start: Date(timeIntervalSince1970: 1000000),
            eta: Date(timeIntervalSince1970: 1000000 + 7200),
            checkin_interval_min: 15,
            notify_start_hour: 8,
            notify_end_hour: 22,
            notify_self: true
        )

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["checkin_interval_min"] as? Int, 15)
        XCTAssertEqual(json["notify_start_hour"] as? Int, 8)
        XCTAssertEqual(json["notify_end_hour"] as? Int, 22)
        XCTAssertEqual(json["notify_self"] as? Bool, true)
    }

    func testTripCreateRequest_GroupTrip() throws {
        let api = API()
        let groupSettings = GroupSettings(
            checkout_mode: "vote",
            vote_threshold: 0.75,
            allow_participant_invites: true,
            share_locations_between_participants: true
        )

        let request = TripCreateRequest(
            title: "Group Hike",
            start: Date(timeIntervalSince1970: 1000000),
            eta: Date(timeIntervalSince1970: 1000000 + 14400),
            is_group_trip: true,
            group_settings: groupSettings,
            participant_ids: [10, 20, 30]
        )

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["is_group_trip"] as? Bool, true)
        XCTAssertNotNil(json["group_settings"])
        XCTAssertEqual(json["participant_ids"] as? [Int], [10, 20, 30])
    }

    // MARK: - TripUpdateRequest Tests

    func testTripUpdateRequest_PartialUpdate() throws {
        let api = API()
        var request = TripUpdateRequest()
        request.title = "Updated Title"
        request.grace_min = 45

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["title"] as? String, "Updated Title")
        XCTAssertEqual(json["grace_min"] as? Int, 45)
        // Other fields should be nil/not present or null
    }

    func testTripUpdateRequest_UpdateETA() throws {
        let api = API()
        var request = TripUpdateRequest()
        request.eta = Date(timeIntervalSince1970: 2000000)

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertNotNil(json["eta"])
    }

    func testTripUpdateRequest_UpdateLocation() throws {
        let api = API()
        var request = TripUpdateRequest()
        request.location_text = "New Location"
        request.gen_lat = 40.7128
        request.gen_lon = -74.0060

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["location_text"] as? String, "New Location")
        XCTAssertEqual(json["gen_lat"] as? Double, 40.7128)
        XCTAssertEqual(json["gen_lon"] as? Double, -74.0060)
    }

    func testTripUpdateRequest_UpdateContacts() throws {
        let api = API()
        var request = TripUpdateRequest()
        request.contact1 = 5
        request.friend_contact1 = 50

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["contact1"] as? Int, 5)
        XCTAssertEqual(json["friend_contact1"] as? Int, 50)
    }

    func testTripUpdateRequest_UpdateLiveLocationSharing() throws {
        let api = API()
        var request = TripUpdateRequest()
        request.share_live_location = true

        let data = try api.encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["share_live_location"] as? Bool, true)
    }

    // MARK: - ContactCreateRequest Tests

    func testContactCreateRequest_Encoding() throws {
        let request = ContactCreateRequest(name: "John Doe", email: "john@example.com")

        let data = try JSONEncoder().encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["name"] as? String, "John Doe")
        XCTAssertEqual(json["email"] as? String, "john@example.com")
    }

    // MARK: - AcceptInvitationRequest Tests

    func testAcceptInvitationRequest_Encoding() throws {
        let request = AcceptInvitationRequest(
            safety_contact_ids: [1, 2],
            safety_friend_ids: [10, 20],
            checkin_interval_min: 20,
            notify_start_hour: 9,
            notify_end_hour: 21
        )

        let data = try JSONEncoder().encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["safety_contact_ids"] as? [Int], [1, 2])
        XCTAssertEqual(json["safety_friend_ids"] as? [Int], [10, 20])
        XCTAssertEqual(json["checkin_interval_min"] as? Int, 20)
        XCTAssertEqual(json["notify_start_hour"] as? Int, 9)
        XCTAssertEqual(json["notify_end_hour"] as? Int, 21)
    }

    func testAcceptInvitationRequest_NoQuietHours() throws {
        let request = AcceptInvitationRequest(
            safety_contact_ids: [],
            safety_friend_ids: [10],
            checkin_interval_min: 30,
            notify_start_hour: nil,
            notify_end_hour: nil
        )

        let data = try JSONEncoder().encode(request)
        let decoded = try JSONDecoder().decode(AcceptInvitationRequest.self, from: data)

        XCTAssertNil(decoded.notify_start_hour)
        XCTAssertNil(decoded.notify_end_hour)
    }

    // MARK: - ParticipantInviteRequest Tests

    func testParticipantInviteRequest_Encoding() throws {
        let request = ParticipantInviteRequest(friend_user_ids: [10, 20, 30])

        let data = try JSONEncoder().encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["friend_user_ids"] as? [Int], [10, 20, 30])
    }
}
