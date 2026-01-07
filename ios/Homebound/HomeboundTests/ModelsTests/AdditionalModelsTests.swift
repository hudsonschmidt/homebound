import XCTest
import CoreLocation
@testable import Homebound

final class AdditionalModelsTests: XCTestCase {

    // MARK: - GlobalStats Tests

    func testGlobalStats_Decoding() throws {
        let json = """
        {
            "total_users": 1500,
            "total_completed_trips": 25000
        }
        """.data(using: .utf8)!

        let stats = try JSONDecoder().decode(GlobalStats.self, from: json)

        XCTAssertEqual(stats.total_users, 1500)
        XCTAssertEqual(stats.total_completed_trips, 25000)
    }

    // MARK: - FriendVisibilitySettings Tests

    func testFriendVisibilitySettings_Decoding() throws {
        let json = """
        {
            "friend_share_checkin_locations": true,
            "friend_share_live_location": false,
            "friend_share_notes": true,
            "friend_allow_update_requests": true,
            "friend_share_achievements": true,
            "friend_share_age": false,
            "friend_share_total_trips": true,
            "friend_share_adventure_time": true,
            "friend_share_favorite_activity": true
        }
        """.data(using: .utf8)!

        let settings = try JSONDecoder().decode(FriendVisibilitySettings.self, from: json)

        XCTAssertTrue(settings.friend_share_checkin_locations)
        XCTAssertFalse(settings.friend_share_live_location)
        XCTAssertTrue(settings.friend_share_notes)
        XCTAssertFalse(settings.friend_share_age)
    }

    func testFriendVisibilitySettings_Defaults() {
        let defaults = FriendVisibilitySettings.defaults

        XCTAssertTrue(defaults.friend_share_checkin_locations)
        XCTAssertFalse(defaults.friend_share_live_location) // Default is false for privacy
        XCTAssertTrue(defaults.friend_share_notes)
        XCTAssertTrue(defaults.friend_allow_update_requests)
        XCTAssertTrue(defaults.friend_share_achievements)
        XCTAssertTrue(defaults.friend_share_age)
        XCTAssertTrue(defaults.friend_share_total_trips)
    }

    // MARK: - FriendActiveTrip Tests

    func testFriendActiveTrip_Decoding() throws {
        let json = """
        {
            "id": 42,
            "owner": {
                "user_id": 100,
                "first_name": "Jane",
                "last_name": "Doe",
                "profile_photo_url": null
            },
            "title": "Morning Hike",
            "activity_name": "Hiking",
            "activity_icon": "figure.hiking",
            "activity_colors": {
                "primary": "#4CAF50",
                "secondary": "#81C784",
                "accent": "#2E7D32"
            },
            "status": "active",
            "start": "2025-12-05T08:00:00Z",
            "eta": "2025-12-05T12:00:00Z",
            "grace_min": 30,
            "location_text": "Mt. Tamalpais"
        }
        """.data(using: .utf8)!

        let trip = try JSONDecoder().decode(FriendActiveTrip.self, from: json)

        XCTAssertEqual(trip.id, 42)
        XCTAssertEqual(trip.owner.first_name, "Jane")
        XCTAssertEqual(trip.title, "Morning Hike")
        XCTAssertEqual(trip.activity_name, "Hiking")
        XCTAssertEqual(trip.status, "active")
        XCTAssertTrue(trip.isActive)
        XCTAssertFalse(trip.isOverdue)
    }

    func testFriendActiveTrip_StatusProperties() throws {
        // Active trip
        let activeJSON = makeFriendActiveTripJSON(status: "active")
        let activeTrip = try JSONDecoder().decode(FriendActiveTrip.self, from: activeJSON)
        XCTAssertTrue(activeTrip.isActive)
        XCTAssertFalse(activeTrip.isPlanned)
        XCTAssertFalse(activeTrip.isOverdue)
        XCTAssertTrue(activeTrip.isActiveStatus)

        // Planned trip
        let plannedJSON = makeFriendActiveTripJSON(status: "planned")
        let plannedTrip = try JSONDecoder().decode(FriendActiveTrip.self, from: plannedJSON)
        XCTAssertFalse(plannedTrip.isActive)
        XCTAssertTrue(plannedTrip.isPlanned)
        XCTAssertFalse(plannedTrip.isActiveStatus)

        // Overdue trip
        let overdueJSON = makeFriendActiveTripJSON(status: "overdue_notified")
        let overdueTrip = try JSONDecoder().decode(FriendActiveTrip.self, from: overdueJSON)
        XCTAssertTrue(overdueTrip.isOverdue)
        XCTAssertTrue(overdueTrip.contactsNotified)
    }

    func testFriendActiveTrip_WithLocationData() throws {
        let json = """
        {
            "id": 42,
            "owner": {"user_id": 100, "first_name": "Jane", "last_name": "", "profile_photo_url": null},
            "title": "Test",
            "activity_name": "Hiking",
            "activity_icon": "figure.hiking",
            "activity_colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
            "status": "active",
            "start": "2025-12-05T08:00:00Z",
            "eta": "2025-12-05T12:00:00Z",
            "grace_min": 30,
            "destination_lat": 37.9235,
            "destination_lon": -122.5965,
            "start_lat": 37.7749,
            "start_lon": -122.4194,
            "checkin_locations": [
                {"timestamp": "2025-12-05T10:00:00Z", "latitude": 37.85, "longitude": -122.55, "location_name": "Trail Head"}
            ],
            "live_location": {
                "latitude": 37.88,
                "longitude": -122.58,
                "timestamp": "2025-12-05T11:00:00Z",
                "speed": 2.5
            }
        }
        """.data(using: .utf8)!

        let trip = try JSONDecoder().decode(FriendActiveTrip.self, from: json)

        XCTAssertNotNil(trip.destinationCoordinate)
        XCTAssertNotNil(trip.startCoordinate)
        XCTAssertNotNil(trip.live_location)
        XCTAssertEqual(trip.checkin_locations?.count, 1)
        XCTAssertTrue(trip.hasLocationData)
    }

    // MARK: - CheckinLocation Tests

    func testCheckinLocation_Decoding() throws {
        let json = """
        {
            "timestamp": "2025-12-05T10:30:00.123456Z",
            "latitude": 37.9235,
            "longitude": -122.5965,
            "location_name": "Trail Marker 5"
        }
        """.data(using: .utf8)!

        let location = try JSONDecoder().decode(CheckinLocation.self, from: json)

        XCTAssertNotNil(location.timestampDate)
        XCTAssertNotNil(location.coordinate)
        XCTAssertEqual(location.location_name, "Trail Marker 5")
        XCTAssertEqual(location.coordinate?.latitude, 37.9235)
        XCTAssertEqual(location.coordinate?.longitude, -122.5965)
    }

    func testCheckinLocation_NilCoordinate() throws {
        let json = """
        {
            "timestamp": "2025-12-05T10:30:00Z"
        }
        """.data(using: .utf8)!

        let location = try JSONDecoder().decode(CheckinLocation.self, from: json)

        XCTAssertNil(location.coordinate)
        XCTAssertNil(location.location_name)
    }

    // MARK: - LiveLocationData Tests

    func testLiveLocationData_Decoding() throws {
        let json = """
        {
            "latitude": 37.9235,
            "longitude": -122.5965,
            "timestamp": "2025-12-05T10:30:00Z",
            "speed": 3.5
        }
        """.data(using: .utf8)!

        let location = try JSONDecoder().decode(LiveLocationData.self, from: json)

        XCTAssertEqual(location.latitude, 37.9235)
        XCTAssertEqual(location.longitude, -122.5965)
        XCTAssertEqual(location.speed, 3.5)
        XCTAssertNotNil(location.timestampDate)
        XCTAssertEqual(location.coordinate.latitude, 37.9235)
    }

    // MARK: - TripInvitation Tests

    func testTripInvitation_Decoding() throws {
        let json = """
        {
            "id": 1,
            "trip_id": 42,
            "invited_at": "2025-12-05T08:00:00Z",
            "invited_by": 100,
            "inviter_name": "Jane Doe",
            "trip_title": "Group Hike",
            "trip_start": "2025-12-05T10:00:00Z",
            "trip_eta": "2025-12-05T14:00:00Z",
            "trip_location": "Mt. Tamalpais",
            "activity_name": "Hiking",
            "activity_icon": "figure.hiking",
            "participant_user_ids": [10, 20, 30]
        }
        """.data(using: .utf8)!

        let invitation = try JSONDecoder().decode(TripInvitation.self, from: json)

        XCTAssertEqual(invitation.id, 1)
        XCTAssertEqual(invitation.trip_id, 42)
        XCTAssertEqual(invitation.inviter_name, "Jane Doe")
        XCTAssertEqual(invitation.trip_title, "Group Hike")
        XCTAssertNotNil(invitation.invitedAtDate)
        XCTAssertNotNil(invitation.tripStartDate)
        XCTAssertNotNil(invitation.tripEtaDate)
        XCTAssertEqual(invitation.participant_user_ids, [10, 20, 30])
    }

    // MARK: - UpdateRequestResponse Tests

    func testUpdateRequestResponse_Success() throws {
        let json = """
        {
            "ok": true,
            "message": "Update request sent successfully"
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(UpdateRequestResponse.self, from: json)

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.message, "Update request sent successfully")
        XCTAssertNil(response.cooldown_remaining_seconds)
    }

    func testUpdateRequestResponse_Cooldown() throws {
        let json = """
        {
            "ok": false,
            "message": "Please wait before requesting another update",
            "cooldown_remaining_seconds": 120
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(UpdateRequestResponse.self, from: json)

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.cooldown_remaining_seconds, 120)
    }

    // MARK: - CheckoutVoteResponse Tests

    func testCheckoutVoteResponse_Decoding() throws {
        let json = """
        {
            "ok": true,
            "message": "Vote recorded",
            "votes_cast": 2,
            "votes_needed": 3,
            "trip_completed": false,
            "user_has_voted": true
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(CheckoutVoteResponse.self, from: json)

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.votes_cast, 2)
        XCTAssertEqual(response.votes_needed, 3)
        XCTAssertFalse(response.trip_completed)
        XCTAssertTrue(response.user_has_voted ?? false)
    }

    func testCheckoutVoteResponse_TripCompleted() throws {
        let json = """
        {
            "ok": true,
            "message": "Trip completed!",
            "votes_cast": 3,
            "votes_needed": 3,
            "trip_completed": true
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(CheckoutVoteResponse.self, from: json)

        XCTAssertTrue(response.trip_completed)
    }

    // MARK: - ParticipantListResponse Tests

    func testParticipantListResponse_Decoding() throws {
        let json = """
        {
            "participants": [
                {
                    "id": 1,
                    "user_id": 100,
                    "role": "owner",
                    "status": "accepted",
                    "invited_at": "2025-12-05T08:00:00Z"
                },
                {
                    "id": 2,
                    "user_id": 101,
                    "role": "participant",
                    "status": "accepted",
                    "invited_at": "2025-12-05T08:01:00Z"
                }
            ],
            "checkout_votes": 1,
            "checkout_votes_needed": 2,
            "group_settings": {
                "checkout_mode": "vote",
                "vote_threshold": 0.5,
                "allow_participant_invites": true,
                "share_locations_between_participants": true
            },
            "user_has_voted": true
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(ParticipantListResponse.self, from: json)

        XCTAssertEqual(response.participants.count, 2)
        XCTAssertEqual(response.checkout_votes, 1)
        XCTAssertEqual(response.checkout_votes_needed, 2)
        XCTAssertEqual(response.group_settings.checkout_mode, "vote")
        XCTAssertTrue(response.user_has_voted ?? false)
    }

    // MARK: - ParticipantLocation Tests

    func testParticipantLocation_Decoding() throws {
        let json = """
        {
            "user_id": 100,
            "user_name": "Jane",
            "last_checkin_at": "2025-12-05T10:00:00Z",
            "last_lat": 37.9235,
            "last_lon": -122.5965,
            "live_lat": 37.93,
            "live_lon": -122.60,
            "live_timestamp": "2025-12-05T11:00:00Z"
        }
        """.data(using: .utf8)!

        let location = try JSONDecoder().decode(ParticipantLocation.self, from: json)

        XCTAssertEqual(location.user_id, 100)
        XCTAssertEqual(location.user_name, "Jane")
        XCTAssertNotNil(location.lastCheckinCoordinate)
        XCTAssertNotNil(location.liveCoordinate)
        XCTAssertNotNil(location.bestCoordinate) // Should prefer live coordinate
    }

    func testParticipantLocation_BestCoordinate_PreferLive() throws {
        let json = """
        {
            "user_id": 100,
            "last_lat": 37.9235,
            "last_lon": -122.5965,
            "live_lat": 37.93,
            "live_lon": -122.60
        }
        """.data(using: .utf8)!

        let location = try JSONDecoder().decode(ParticipantLocation.self, from: json)

        // bestCoordinate should return live coordinate when available
        XCTAssertEqual(location.bestCoordinate?.latitude, 37.93)
    }

    func testParticipantLocation_BestCoordinate_FallbackToLastCheckin() throws {
        let json = """
        {
            "user_id": 100,
            "last_lat": 37.9235,
            "last_lon": -122.5965
        }
        """.data(using: .utf8)!

        let location = try JSONDecoder().decode(ParticipantLocation.self, from: json)

        // bestCoordinate should return last checkin when no live data
        XCTAssertEqual(location.bestCoordinate?.latitude, 37.9235)
    }

    // MARK: - TripContact Tests

    func testTripContact_EmailType() throws {
        let json = """
        {
            "type": "email",
            "contact_id": 1,
            "name": "Emergency Contact",
            "email": "emergency@example.com"
        }
        """.data(using: .utf8)!

        let contact = try JSONDecoder().decode(TripContact.self, from: json)

        XCTAssertTrue(contact.isEmailContact)
        XCTAssertFalse(contact.isFriendContact)
        XCTAssertEqual(contact.displayName, "Emergency Contact")
        XCTAssertTrue(contact.id.starts(with: "email-"))
    }

    func testTripContact_FriendType() throws {
        let json = """
        {
            "type": "friend",
            "friend_user_id": 42,
            "friend_name": "Jane Doe",
            "profile_photo_url": "https://example.com/photo.jpg"
        }
        """.data(using: .utf8)!

        let contact = try JSONDecoder().decode(TripContact.self, from: json)

        XCTAssertFalse(contact.isEmailContact)
        XCTAssertTrue(contact.isFriendContact)
        XCTAssertEqual(contact.displayName, "Jane Doe")
        XCTAssertTrue(contact.id.starts(with: "friend-"))
    }

    // MARK: - FriendInvitePreview Tests

    func testFriendInvitePreview_Decoding() throws {
        let json = """
        {
            "inviter_first_name": "Jane",
            "inviter_profile_photo_url": null,
            "inviter_member_since": "2024-01-15T00:00:00Z",
            "expires_at": "2025-12-31T23:59:59Z",
            "is_valid": true
        }
        """.data(using: .utf8)!

        let preview = try JSONDecoder().decode(FriendInvitePreview.self, from: json)

        XCTAssertEqual(preview.inviter_first_name, "Jane")
        XCTAssertTrue(preview.is_valid)
        XCTAssertNotNil(preview.inviterMemberSinceDate)
        XCTAssertNotNil(preview.expiresAtDate)
    }

    func testFriendInvitePreview_InvalidInvite() throws {
        let json = """
        {
            "inviter_first_name": "Jane",
            "inviter_profile_photo_url": null,
            "inviter_member_since": "2024-01-15T00:00:00Z",
            "expires_at": null,
            "is_valid": false
        }
        """.data(using: .utf8)!

        let preview = try JSONDecoder().decode(FriendInvitePreview.self, from: json)

        XCTAssertFalse(preview.is_valid)
        XCTAssertNil(preview.expiresAtDate)
    }

    // MARK: - FriendAchievement Tests

    func testFriendAchievement_Earned() throws {
        let json = """
        {
            "id": "first_trip",
            "title": "First Steps",
            "description": "Complete 1 trip",
            "category": "totalTrips",
            "sf_symbol": "flag.fill",
            "threshold": 1,
            "unit": "trips",
            "is_earned": true,
            "earned_date": "2024-06-15T00:00:00Z",
            "current_value": 5
        }
        """.data(using: .utf8)!

        let achievement = try JSONDecoder().decode(FriendAchievement.self, from: json)

        XCTAssertEqual(achievement.id, "first_trip")
        XCTAssertTrue(achievement.is_earned)
        XCTAssertNotNil(achievement.earnedDateValue)
        XCTAssertEqual(achievement.current_value, 5)
        XCTAssertEqual(achievement.categoryEnum, .totalTrips)
    }

    func testFriendAchievement_NotEarned() throws {
        let json = """
        {
            "id": "century",
            "title": "Century",
            "description": "Complete 100 trips",
            "category": "totalTrips",
            "sf_symbol": "trophy.fill",
            "threshold": 100,
            "unit": "trips",
            "is_earned": false,
            "earned_date": null,
            "current_value": 25
        }
        """.data(using: .utf8)!

        let achievement = try JSONDecoder().decode(FriendAchievement.self, from: json)

        XCTAssertFalse(achievement.is_earned)
        XCTAssertNil(achievement.earnedDateValue)
        XCTAssertEqual(achievement.current_value, 25)
    }

    // MARK: - FriendAchievementsResponse Tests

    func testFriendAchievementsResponse_Decoding() throws {
        let json = """
        {
            "user_id": 42,
            "friend_name": "Jane Doe",
            "achievements": [],
            "earned_count": 15,
            "total_count": 40
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(FriendAchievementsResponse.self, from: json)

        XCTAssertEqual(response.user_id, 42)
        XCTAssertEqual(response.friend_name, "Jane Doe")
        XCTAssertEqual(response.earned_count, 15)
        XCTAssertEqual(response.total_count, 40)
    }

    // MARK: - Helper Methods

    private func makeFriendActiveTripJSON(status: String) -> Data {
        """
        {
            "id": 1,
            "owner": {"user_id": 100, "first_name": "Jane", "last_name": "", "profile_photo_url": null},
            "title": "Test",
            "activity_name": "Hiking",
            "activity_icon": "figure.hiking",
            "activity_colors": {"primary": "#000", "secondary": "#111", "accent": "#222"},
            "status": "\(status)",
            "start": "2025-12-05T08:00:00Z",
            "eta": "2025-12-05T12:00:00Z",
            "grace_min": 30
        }
        """.data(using: .utf8)!
    }
}
