import XCTest
@testable import Homebound

final class TripStatusTests: XCTestCase {

    // MARK: - TripStatus Enum Tests

    func testTripStatus_AllCases() {
        let allCases = TripStatus.allCases

        XCTAssertEqual(allCases.count, 7)
        XCTAssertTrue(allCases.contains(.active))
        XCTAssertTrue(allCases.contains(.overdue))
        XCTAssertTrue(allCases.contains(.overdueNotified))
        XCTAssertTrue(allCases.contains(.completed))
        XCTAssertTrue(allCases.contains(.planned))
        XCTAssertTrue(allCases.contains(.scheduled))
        XCTAssertTrue(allCases.contains(.cancelled))
    }

    func testTripStatus_RawValues() {
        XCTAssertEqual(TripStatus.active.rawValue, "active")
        XCTAssertEqual(TripStatus.overdue.rawValue, "overdue")
        XCTAssertEqual(TripStatus.overdueNotified.rawValue, "overdue_notified")
        XCTAssertEqual(TripStatus.completed.rawValue, "completed")
        XCTAssertEqual(TripStatus.planned.rawValue, "planned")
        XCTAssertEqual(TripStatus.scheduled.rawValue, "scheduled")
        XCTAssertEqual(TripStatus.cancelled.rawValue, "cancelled")
    }

    func testTripStatus_IsInProgress_True() {
        XCTAssertTrue(TripStatus.active.isInProgress)
        XCTAssertTrue(TripStatus.overdue.isInProgress)
        XCTAssertTrue(TripStatus.overdueNotified.isInProgress)
    }

    func testTripStatus_IsInProgress_False() {
        XCTAssertFalse(TripStatus.completed.isInProgress)
        XCTAssertFalse(TripStatus.planned.isInProgress)
        XCTAssertFalse(TripStatus.scheduled.isInProgress)
        XCTAssertFalse(TripStatus.cancelled.isInProgress)
    }

    func testTripStatus_ContactsNotified() {
        XCTAssertTrue(TripStatus.overdueNotified.contactsNotified)
        XCTAssertFalse(TripStatus.active.contactsNotified)
        XCTAssertFalse(TripStatus.overdue.contactsNotified)
        XCTAssertFalse(TripStatus.completed.contactsNotified)
    }

    func testTripStatus_DisplayText() {
        XCTAssertEqual(TripStatus.active.displayText, "ACTIVE")
        XCTAssertEqual(TripStatus.overdue.displayText, "CHECK IN NOW")
        XCTAssertEqual(TripStatus.overdueNotified.displayText, "OVERDUE")
        XCTAssertEqual(TripStatus.completed.displayText, "COMPLETED")
        XCTAssertEqual(TripStatus.planned.displayText, "PLANNED")
        XCTAssertEqual(TripStatus.scheduled.displayText, "SCHEDULED")
        XCTAssertEqual(TripStatus.cancelled.displayText, "CANCELLED")
    }

    // MARK: - Trip Extension Tests

    func testTrip_TripStatus_ValidStatus() {
        let activeTrip = TestFixtures.makeTrip(status: "active")
        let overdueTrip = TestFixtures.makeTrip(status: "overdue")
        let completedTrip = TestFixtures.makeTrip(status: "completed")

        XCTAssertEqual(activeTrip.tripStatus, .active)
        XCTAssertEqual(overdueTrip.tripStatus, .overdue)
        XCTAssertEqual(completedTrip.tripStatus, .completed)
    }

    func testTrip_TripStatus_UnknownStatus_DefaultsToActive() {
        let trip = TestFixtures.makeTrip(status: "unknown_status")
        XCTAssertEqual(trip.tripStatus, .active)
    }

    func testTrip_IsInProgress() {
        let activeTrip = TestFixtures.makeTrip(status: "active")
        let overdueTrip = TestFixtures.makeTrip(status: "overdue")
        let completedTrip = TestFixtures.makeTrip(status: "completed")
        let plannedTrip = TestFixtures.makeTrip(status: "planned")

        XCTAssertTrue(activeTrip.isInProgress)
        XCTAssertTrue(overdueTrip.isInProgress)
        XCTAssertFalse(completedTrip.isInProgress)
        XCTAssertFalse(plannedTrip.isInProgress)
    }

    func testTrip_ContactsNotified() {
        let overdueNotifiedTrip = TestFixtures.makeTrip(status: "overdue_notified")
        let activeTrip = TestFixtures.makeTrip(status: "active")

        XCTAssertTrue(overdueNotifiedTrip.contactsNotified)
        XCTAssertFalse(activeTrip.contactsNotified)
    }

    func testTrip_Deadline() {
        let start = Date()
        let eta = start.addingTimeInterval(3600) // 1 hour
        let trip = TestFixtures.makeTrip(startAt: start, etaAt: eta, graceMinutes: 30)

        let expectedDeadline = eta.addingTimeInterval(30 * 60)
        XCTAssertEqual(trip.deadline.timeIntervalSince1970, expectedDeadline.timeIntervalSince1970, accuracy: 1)
    }

    func testTrip_IsPastETA_True() {
        let pastEta = Date().addingTimeInterval(-3600) // 1 hour ago
        let trip = TestFixtures.makeTrip(startAt: pastEta.addingTimeInterval(-7200), etaAt: pastEta)

        XCTAssertTrue(trip.isPastETA)
    }

    func testTrip_IsPastETA_False() {
        let futureEta = Date().addingTimeInterval(3600) // 1 hour from now
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta)

        XCTAssertFalse(trip.isPastETA)
    }

    func testTrip_IsPastDeadline_True() {
        let pastEta = Date().addingTimeInterval(-7200) // 2 hours ago (grace period passed)
        let trip = TestFixtures.makeTrip(startAt: pastEta.addingTimeInterval(-7200), etaAt: pastEta, graceMinutes: 30)

        XCTAssertTrue(trip.isPastDeadline)
    }

    func testTrip_IsPastDeadline_False() {
        let futureEta = Date().addingTimeInterval(3600) // 1 hour from now
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta, graceMinutes: 30)

        XCTAssertFalse(trip.isPastDeadline)
    }

    func testTrip_TimeRemaining_Future() {
        let futureEta = Date().addingTimeInterval(3600) // 1 hour from now
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta)

        XCTAssertGreaterThan(trip.timeRemaining, 0)
        XCTAssertEqual(trip.timeRemaining, 3600, accuracy: 5)
    }

    func testTrip_TimeRemaining_Past() {
        let pastEta = Date().addingTimeInterval(-3600) // 1 hour ago
        let trip = TestFixtures.makeTrip(startAt: pastEta.addingTimeInterval(-7200), etaAt: pastEta)

        XCTAssertLessThan(trip.timeRemaining, 0)
    }

    func testTrip_TimeRemainingUntilDeadline() {
        let futureEta = Date().addingTimeInterval(3600) // 1 hour from now
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta, graceMinutes: 30)

        // Deadline is ETA + 30 minutes = 1.5 hours from now
        XCTAssertEqual(trip.timeRemainingUntilDeadline, 3600 + 1800, accuracy: 5)
    }

    func testTrip_FormattedTimeRemaining() {
        let futureEta = Date().addingTimeInterval(3600) // 1 hour from now
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta)

        let formatted = trip.formattedTimeRemaining
        XCTAssertFalse(formatted.isEmpty)
        // Should be approximately "1h" or "59m" depending on timing
    }

    func testTrip_StatusDisplayText_Active() {
        let futureEta = Date().addingTimeInterval(3600)
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta, status: "active")

        XCTAssertEqual(trip.statusDisplayText, "ACTIVE")
    }

    func testTrip_StatusDisplayText_ActivePastETA() {
        let pastEta = Date().addingTimeInterval(-600) // 10 minutes ago (in grace period)
        let trip = TestFixtures.makeTrip(startAt: pastEta.addingTimeInterval(-3600), etaAt: pastEta, graceMinutes: 30, status: "active")

        XCTAssertEqual(trip.statusDisplayText, "CHECK IN NOW")
    }

    func testTrip_IsUrgent_PastETA() {
        let pastEta = Date().addingTimeInterval(-600)
        let trip = TestFixtures.makeTrip(startAt: pastEta.addingTimeInterval(-3600), etaAt: pastEta, status: "active")

        XCTAssertTrue(trip.isUrgent)
    }

    func testTrip_IsUrgent_Overdue() {
        let futureEta = Date().addingTimeInterval(3600)
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta, status: "overdue")

        XCTAssertTrue(trip.isUrgent)
    }

    func testTrip_IsUrgent_NotUrgent() {
        let futureEta = Date().addingTimeInterval(3600)
        let trip = TestFixtures.makeTrip(startAt: Date(), etaAt: futureEta, status: "active")

        XCTAssertFalse(trip.isUrgent)
    }

    func testTrip_CanCheckIn_True() {
        let trip = makeTripWithTokens(status: "active", checkinToken: "token123", checkoutToken: nil)
        XCTAssertTrue(trip.canCheckIn)
    }

    func testTrip_CanCheckIn_False_NoToken() {
        let trip = makeTripWithTokens(status: "active", checkinToken: nil, checkoutToken: nil)
        XCTAssertFalse(trip.canCheckIn)
    }

    func testTrip_CanCheckIn_False_NotInProgress() {
        let trip = makeTripWithTokens(status: "completed", checkinToken: "token123", checkoutToken: nil)
        XCTAssertFalse(trip.canCheckIn)
    }

    func testTrip_CanCheckOut_True() {
        let trip = makeTripWithTokens(status: "active", checkinToken: nil, checkoutToken: "token456")
        XCTAssertTrue(trip.canCheckOut)
    }

    func testTrip_CanCheckOut_False_NoToken() {
        let trip = makeTripWithTokens(status: "active", checkinToken: nil, checkoutToken: nil)
        XCTAssertFalse(trip.canCheckOut)
    }

    func testTrip_ContactCount_None() {
        let trip = TestFixtures.makeTrip()
        XCTAssertEqual(trip.contactCount, 0)
    }

    func testTrip_ContactCount_All() {
        let trip = makeTripWithContacts(contact1: 1, contact2: 2, contact3: 3)
        XCTAssertEqual(trip.contactCount, 3)
    }

    func testTrip_ContactCount_Partial() {
        let trip = makeTripWithContacts(contact1: 1, contact2: nil, contact3: 3)
        XCTAssertEqual(trip.contactCount, 2)
    }

    func testTrip_FriendContactCount() {
        let trip = makeTripWithFriendContacts(friend1: 10, friend2: 20, friend3: nil)
        XCTAssertEqual(trip.friendContactCount, 2)
    }

    func testTrip_TotalContactCount() {
        let trip = makeTripWithAllContacts(
            contact1: 1, contact2: 2, contact3: nil,
            friend1: 10, friend2: nil, friend3: 30
        )
        XCTAssertEqual(trip.totalContactCount, 4) // 2 regular + 2 friend
    }

    // MARK: - Helper Methods

    private func makeTripWithTokens(status: String, checkinToken: String?, checkoutToken: String?) -> Trip {
        Trip(
            id: 1, user_id: 100, title: "Test",
            activity: TestFixtures.makeActivity(),
            start_at: Date(), eta_at: Date().addingTimeInterval(3600),
            grace_minutes: 30, location_text: nil,
            location_lat: nil, location_lng: nil, notes: nil,
            status: status, completed_at: nil,
            last_checkin: nil, created_at: "",
            contact1: nil, contact2: nil, contact3: nil,
            checkin_token: checkinToken, checkout_token: checkoutToken
        )
    }

    private func makeTripWithContacts(contact1: Int?, contact2: Int?, contact3: Int?) -> Trip {
        Trip(
            id: 1, user_id: 100, title: "Test",
            activity: TestFixtures.makeActivity(),
            start_at: Date(), eta_at: Date().addingTimeInterval(3600),
            grace_minutes: 30, location_text: nil,
            location_lat: nil, location_lng: nil, notes: nil,
            status: "active", completed_at: nil,
            last_checkin: nil, created_at: "",
            contact1: contact1, contact2: contact2, contact3: contact3,
            checkin_token: nil, checkout_token: nil
        )
    }

    private func makeTripWithFriendContacts(friend1: Int?, friend2: Int?, friend3: Int?) -> Trip {
        Trip(
            id: 1, user_id: 100, title: "Test",
            activity: TestFixtures.makeActivity(),
            start_at: Date(), eta_at: Date().addingTimeInterval(3600),
            grace_minutes: 30, location_text: nil,
            location_lat: nil, location_lng: nil, notes: nil,
            status: "active", completed_at: nil,
            last_checkin: nil, created_at: "",
            contact1: nil, contact2: nil, contact3: nil,
            friend_contact1: friend1, friend_contact2: friend2, friend_contact3: friend3,
            checkin_token: nil, checkout_token: nil
        )
    }

    private func makeTripWithAllContacts(
        contact1: Int?, contact2: Int?, contact3: Int?,
        friend1: Int?, friend2: Int?, friend3: Int?
    ) -> Trip {
        Trip(
            id: 1, user_id: 100, title: "Test",
            activity: TestFixtures.makeActivity(),
            start_at: Date(), eta_at: Date().addingTimeInterval(3600),
            grace_minutes: 30, location_text: nil,
            location_lat: nil, location_lng: nil, notes: nil,
            status: "active", completed_at: nil,
            last_checkin: nil, created_at: "",
            contact1: contact1, contact2: contact2, contact3: contact3,
            friend_contact1: friend1, friend_contact2: friend2, friend_contact3: friend3,
            checkin_token: nil, checkout_token: nil
        )
    }
}
