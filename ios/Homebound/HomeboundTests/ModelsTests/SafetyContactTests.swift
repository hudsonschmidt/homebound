import XCTest
@testable import Homebound

final class SafetyContactTests: XCTestCase {

    // MARK: - SafetyContact ID Tests

    func testSafetyContact_EmailContact_ID() {
        let contact = Contact(id: 42, user_id: 100, name: "Test", email: "test@example.com")
        let safetyContact = SafetyContact.emailContact(contact)

        XCTAssertEqual(safetyContact.id, "contact-42")
    }

    func testSafetyContact_Friend_ID() {
        let friend = TestFixtures.makeFriend(userId: 42)
        let safetyContact = SafetyContact.friend(friend)

        XCTAssertEqual(safetyContact.id, "friend-42")
    }

    // MARK: - SafetyContact Display Name Tests

    func testSafetyContact_DisplayName_EmailContact() {
        let contact = Contact(id: 1, user_id: 100, name: "Emergency Contact", email: "emergency@example.com")
        let safetyContact = SafetyContact.emailContact(contact)

        XCTAssertEqual(safetyContact.displayName, "Emergency Contact")
    }

    func testSafetyContact_DisplayName_Friend() {
        let friend = TestFixtures.makeFriend(firstName: "Jane", lastName: "Doe")
        let safetyContact = SafetyContact.friend(friend)

        XCTAssertEqual(safetyContact.displayName, "Jane Doe")
    }

    // MARK: - SafetyContact Type Check Tests

    func testSafetyContact_IsEmailContact_True() {
        let contact = Contact(id: 1, user_id: 100, name: "Test", email: "test@example.com")
        let safetyContact = SafetyContact.emailContact(contact)

        XCTAssertTrue(safetyContact.isEmailContact)
        XCTAssertFalse(safetyContact.isFriend)
    }

    func testSafetyContact_IsFriend_True() {
        let friend = TestFixtures.makeFriend()
        let safetyContact = SafetyContact.friend(friend)

        XCTAssertTrue(safetyContact.isFriend)
        XCTAssertFalse(safetyContact.isEmailContact)
    }

    // MARK: - SafetyContact Icon Tests

    func testSafetyContact_IconName_EmailContact() {
        let contact = Contact(id: 1, user_id: 100, name: "Test", email: "test@example.com")
        let safetyContact = SafetyContact.emailContact(contact)

        XCTAssertEqual(safetyContact.iconName, "envelope.fill")
    }

    func testSafetyContact_IconName_Friend() {
        let friend = TestFixtures.makeFriend()
        let safetyContact = SafetyContact.friend(friend)

        XCTAssertEqual(safetyContact.iconName, "bell.fill")
    }

    // MARK: - SafetyContact Hashable Tests

    func testSafetyContact_Hashable_EmailContacts() {
        let contact1 = Contact(id: 1, user_id: 100, name: "Test1", email: "test1@example.com")
        let contact2 = Contact(id: 1, user_id: 100, name: "Test1", email: "test1@example.com")
        let contact3 = Contact(id: 2, user_id: 100, name: "Test2", email: "test2@example.com")

        let safetyContact1 = SafetyContact.emailContact(contact1)
        let safetyContact2 = SafetyContact.emailContact(contact2)
        let safetyContact3 = SafetyContact.emailContact(contact3)

        XCTAssertEqual(safetyContact1, safetyContact2)
        XCTAssertNotEqual(safetyContact1, safetyContact3)

        // Test Set behavior
        var set: Set<SafetyContact> = []
        set.insert(safetyContact1)
        set.insert(safetyContact2)
        XCTAssertEqual(set.count, 1)

        set.insert(safetyContact3)
        XCTAssertEqual(set.count, 2)
    }

    func testSafetyContact_Hashable_Friends() {
        let friend1 = TestFixtures.makeFriend(userId: 42)
        let friend2 = TestFixtures.makeFriend(userId: 42)
        let friend3 = TestFixtures.makeFriend(userId: 43)

        let safetyContact1 = SafetyContact.friend(friend1)
        let safetyContact2 = SafetyContact.friend(friend2)
        let safetyContact3 = SafetyContact.friend(friend3)

        XCTAssertEqual(safetyContact1, safetyContact2)
        XCTAssertNotEqual(safetyContact1, safetyContact3)
    }

    func testSafetyContact_Hashable_MixedTypes() {
        let contact = Contact(id: 42, user_id: 100, name: "Test", email: "test@example.com")
        let friend = TestFixtures.makeFriend(userId: 42)

        let emailContact = SafetyContact.emailContact(contact)
        let friendContact = SafetyContact.friend(friend)

        // Same ID numbers but different types should not be equal
        XCTAssertNotEqual(emailContact, friendContact)
    }

    // MARK: - ActivityTypeAdapter Tests

    func testActivityTypeAdapter_PrimaryColor() {
        let activity = TestFixtures.makeActivity()
        let adapter = ActivityTypeAdapter(activity: activity)

        // Should not crash and return a color
        XCTAssertNotNil(adapter.primaryColor)
    }

    func testActivityTypeAdapter_RawValue() {
        let activity = Activity(
            id: 1, name: "Road Trip", icon: "car.fill",
            default_grace_minutes: 30,
            colors: Activity.ActivityColors(primary: "#000", secondary: "#111", accent: "#222"),
            messages: Activity.ActivityMessages(start: "", checkin: "", checkout: "", overdue: "", encouragement: []),
            safety_tips: [], order: 1
        )
        let adapter = ActivityTypeAdapter(activity: activity)

        XCTAssertEqual(adapter.rawValue, "road_trip")
    }

    func testActivityTypeAdapter_Hashable() {
        let activity1 = TestFixtures.makeActivity(id: 1)
        let activity2 = TestFixtures.makeActivity(id: 1)
        let activity3 = TestFixtures.makeActivity(id: 2)

        let adapter1 = ActivityTypeAdapter(activity: activity1)
        let adapter2 = ActivityTypeAdapter(activity: activity2)
        let adapter3 = ActivityTypeAdapter(activity: activity3)

        XCTAssertEqual(adapter1, adapter2)
        XCTAssertNotEqual(adapter1, adapter3)
    }

    func testActivityArray_ToAdapters() {
        let activities = [
            TestFixtures.makeActivity(id: 1),
            TestFixtures.makeActivity(id: 2),
            TestFixtures.makeActivity(id: 3)
        ]

        let adapters = activities.toAdapters()

        XCTAssertEqual(adapters.count, 3)
        XCTAssertEqual(adapters[0].id, 1)
        XCTAssertEqual(adapters[1].id, 2)
        XCTAssertEqual(adapters[2].id, 3)
    }
}
