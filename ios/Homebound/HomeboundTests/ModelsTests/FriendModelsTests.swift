import XCTest
@testable import Homebound

final class FriendModelsTests: XCTestCase {

    // MARK: - Friend Decoding Tests

    func testFriend_DecodesFromJSON() throws {
        let decoder = JSONDecoder()
        let friend = try decoder.decode(Friend.self, from: TestFixtures.friendJSON)

        XCTAssertEqual(friend.user_id, 42)
        XCTAssertEqual(friend.first_name, "Jane")
        XCTAssertEqual(friend.last_name, "Doe")
        XCTAssertEqual(friend.age, 28)
        XCTAssertEqual(friend.achievements_count, 15)
        XCTAssertEqual(friend.total_achievements, 40)
        XCTAssertEqual(friend.total_trips, 25)
        XCTAssertEqual(friend.total_adventure_hours, 50)
        XCTAssertEqual(friend.favorite_activity_name, "Hiking")
    }

    // MARK: - Friend Computed Properties Tests

    func testFriend_FullName_WithLastName() {
        let friend = TestFixtures.makeFriend(firstName: "Jane", lastName: "Doe")
        XCTAssertEqual(friend.fullName, "Jane Doe")
    }

    func testFriend_FullName_WithoutLastName() {
        let json = """
        {
            "user_id": 42,
            "first_name": "Jane",
            "last_name": "",
            "profile_photo_url": null,
            "member_since": "2024-01-15T00:00:00Z",
            "friendship_since": "2024-06-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let friend = try! decoder.decode(Friend.self, from: json)

        XCTAssertEqual(friend.fullName, "Jane")
    }

    func testFriend_Initial_ValidFirstName() {
        let friend = TestFixtures.makeFriend(firstName: "Jane")
        XCTAssertEqual(friend.initial, "J")
    }

    func testFriend_Initial_EmptyFirstName() {
        let json = """
        {
            "user_id": 42,
            "first_name": "",
            "last_name": "Doe",
            "profile_photo_url": null,
            "member_since": "2024-01-15T00:00:00Z",
            "friendship_since": "2024-06-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let friend = try! decoder.decode(Friend.self, from: json)

        XCTAssertEqual(friend.initial, "?")
    }

    func testFriend_FormattedAchievementsCount_WithTotal() {
        let friend = TestFixtures.makeFriend(achievementsCount: 15, totalAchievements: 40)
        XCTAssertEqual(friend.formattedAchievementsCount, "15/40")
    }

    func testFriend_FormattedAchievementsCount_WithoutTotal() {
        let json = """
        {
            "user_id": 42,
            "first_name": "Jane",
            "last_name": "Doe",
            "profile_photo_url": null,
            "member_since": "2024-01-15T00:00:00Z",
            "friendship_since": "2024-06-01T00:00:00Z",
            "achievements_count": 15
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let friend = try! decoder.decode(Friend.self, from: json)

        XCTAssertEqual(friend.formattedAchievementsCount, "15")
    }

    func testFriend_FormattedAchievementsCount_Zero() {
        let friend = TestFixtures.makeFriend(achievementsCount: 0, totalAchievements: 40)
        XCTAssertNil(friend.formattedAchievementsCount)
    }

    func testFriend_FormattedAdventureTime_Days() {
        let friend = TestFixtures.makeFriend(totalAdventureHours: 50) // 2d 2h
        XCTAssertEqual(friend.formattedAdventureTime, "2d 2h")
    }

    func testFriend_FormattedAdventureTime_ExactDays() {
        let friend = TestFixtures.makeFriend(totalAdventureHours: 48) // 2d
        XCTAssertEqual(friend.formattedAdventureTime, "2d")
    }

    func testFriend_FormattedAdventureTime_Hours() {
        let friend = TestFixtures.makeFriend(totalAdventureHours: 12)
        XCTAssertEqual(friend.formattedAdventureTime, "12h")
    }

    func testFriend_FormattedAdventureTime_Zero() {
        let friend = TestFixtures.makeFriend(totalAdventureHours: 0)
        XCTAssertNil(friend.formattedAdventureTime)
    }

    func testFriend_MemberSinceDate_ParsesISO8601() {
        let friend = TestFixtures.makeFriend()
        XCTAssertNotNil(friend.memberSinceDate)
    }

    func testFriend_FriendshipSinceDate_ParsesISO8601() {
        let friend = TestFixtures.makeFriend()
        XCTAssertNotNil(friend.friendshipSinceDate)
    }

    func testFriend_ID_ReturnsUserID() {
        let friend = TestFixtures.makeFriend(userId: 42)
        XCTAssertEqual(friend.id, 42)
    }

    // MARK: - FriendInvite Tests

    func testFriendInvite_DecodesFromJSON() throws {
        let json = """
        {
            "token": "abc123",
            "invite_url": "https://example.com/invite/abc123",
            "expires_at": "2025-12-31T23:59:59Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let invite = try decoder.decode(FriendInvite.self, from: json)

        XCTAssertEqual(invite.token, "abc123")
        XCTAssertEqual(invite.invite_url, "https://example.com/invite/abc123")
        XCTAssertNotNil(invite.expiresAtDate)
        XCTAssertFalse(invite.isPermanent)
    }

    func testFriendInvite_IsPermanent_WhenExpiresAtNull() throws {
        let json = """
        {
            "token": "abc123",
            "invite_url": "https://example.com/invite/abc123",
            "expires_at": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let invite = try decoder.decode(FriendInvite.self, from: json)

        XCTAssertTrue(invite.isPermanent)
        XCTAssertNil(invite.expiresAtDate)
    }

    // MARK: - PendingInvite Tests

    func testPendingInvite_DecodesFromJSON() throws {
        let json = """
        {
            "id": 1,
            "token": "abc123",
            "created_at": "2025-12-01T00:00:00Z",
            "expires_at": "2025-12-31T23:59:59Z",
            "status": "pending",
            "accepted_by_name": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let invite = try decoder.decode(PendingInvite.self, from: json)

        XCTAssertEqual(invite.id, 1)
        XCTAssertEqual(invite.token, "abc123")
        XCTAssertEqual(invite.status, "pending")
        XCTAssertTrue(invite.isPending)
        XCTAssertFalse(invite.isAccepted)
    }

    func testPendingInvite_StatusProperties() {
        let pending = PendingInvite(
            id: 1, token: "abc", created_at: "2025-12-01T00:00:00Z",
            expires_at: nil, status: "pending", accepted_by_name: nil
        )
        XCTAssertTrue(pending.isPending)
        XCTAssertFalse(pending.isAccepted)
        XCTAssertFalse(pending.isExpired)
        XCTAssertFalse(pending.isActive)

        let accepted = PendingInvite(
            id: 2, token: "def", created_at: "2025-12-01T00:00:00Z",
            expires_at: nil, status: "accepted", accepted_by_name: "Jane"
        )
        XCTAssertFalse(accepted.isPending)
        XCTAssertTrue(accepted.isAccepted)

        let active = PendingInvite(
            id: 3, token: "ghi", created_at: "2025-12-01T00:00:00Z",
            expires_at: nil, status: "active", accepted_by_name: nil
        )
        XCTAssertTrue(active.isActive)
    }

    // MARK: - TripParticipant Tests

    func testTripParticipant_DecodesFromJSON() throws {
        let json = """
        {
            "id": 1,
            "user_id": 42,
            "role": "participant",
            "status": "accepted",
            "invited_at": "2025-12-01T00:00:00Z",
            "invited_by": 100,
            "joined_at": "2025-12-01T12:00:00Z",
            "left_at": null,
            "last_checkin_at": "2025-12-05T10:00:00Z",
            "last_lat": 37.9235,
            "last_lon": -122.5965,
            "user_name": "Jane Doe",
            "user_email": "jane@example.com",
            "profile_photo_url": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let participant = try decoder.decode(TripParticipant.self, from: json)

        XCTAssertEqual(participant.id, 1)
        XCTAssertEqual(participant.user_id, 42)
        XCTAssertEqual(participant.role, "participant")
        XCTAssertEqual(participant.status, "accepted")
        XCTAssertFalse(participant.isOwner)
        XCTAssertTrue(participant.isAccepted)
        XCTAssertTrue(participant.hasCheckedIn)
        XCTAssertEqual(participant.displayName, "Jane Doe")
        XCTAssertNotNil(participant.coordinate)
    }

    func testTripParticipant_IsOwner() throws {
        let json = """
        {
            "id": 1,
            "user_id": 100,
            "role": "owner",
            "status": "accepted",
            "invited_at": "2025-12-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let participant = try decoder.decode(TripParticipant.self, from: json)

        XCTAssertTrue(participant.isOwner)
    }

    func testTripParticipant_DisplayName_FallbackToEmail() throws {
        let json = """
        {
            "id": 1,
            "user_id": 42,
            "role": "participant",
            "status": "invited",
            "invited_at": "2025-12-01T00:00:00Z",
            "user_email": "jane@example.com"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let participant = try decoder.decode(TripParticipant.self, from: json)

        XCTAssertEqual(participant.displayName, "jane@example.com")
    }

    func testTripParticipant_DisplayName_Unknown() throws {
        let json = """
        {
            "id": 1,
            "user_id": 42,
            "role": "participant",
            "status": "invited",
            "invited_at": "2025-12-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let participant = try decoder.decode(TripParticipant.self, from: json)

        XCTAssertEqual(participant.displayName, "Unknown")
    }

    func testTripParticipant_Initial() throws {
        let json = """
        {
            "id": 1,
            "user_id": 42,
            "role": "participant",
            "status": "accepted",
            "invited_at": "2025-12-01T00:00:00Z",
            "user_name": "Jane"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let participant = try decoder.decode(TripParticipant.self, from: json)

        XCTAssertEqual(participant.initial, "J")
    }
}
