import XCTest
@testable import Homebound

final class SubscriptionModelsTests: XCTestCase {

    // MARK: - FeatureLimits Decoding Tests

    func testFeatureLimits_DecodesFromFullJSON() throws {
        let json = """
        {
            "tier": "plus",
            "is_premium": true,
            "contacts_per_trip": 5,
            "saved_trips_limit": 10,
            "history_days": null,
            "extensions": [30, 60, 120, 180, 240],
            "visible_stats": 8,
            "widgets_enabled": true,
            "live_activity_enabled": true,
            "custom_intervals_enabled": true,
            "trip_map_enabled": true,
            "pinned_activities_limit": 3,
            "group_trips_enabled": true,
            "contact_groups_enabled": true,
            "custom_messages_enabled": true,
            "export_enabled": true,
            "family_sharing_enabled": true
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let limits = try decoder.decode(FeatureLimits.self, from: json)

        XCTAssertEqual(limits.tier, "plus")
        XCTAssertTrue(limits.isPremium)
        XCTAssertEqual(limits.contactsPerTrip, 5)
        XCTAssertEqual(limits.savedTripsLimit, 10)
        XCTAssertNil(limits.historyDays) // Unlimited
        XCTAssertEqual(limits.extensions, [30, 60, 120, 180, 240])
        XCTAssertEqual(limits.visibleStats, 8)
        XCTAssertTrue(limits.widgetsEnabled)
        XCTAssertTrue(limits.liveActivityEnabled)
        XCTAssertTrue(limits.customIntervalsEnabled)
        XCTAssertTrue(limits.tripMapEnabled)
        XCTAssertEqual(limits.pinnedActivitiesLimit, 3)
        XCTAssertTrue(limits.groupTripsEnabled)
        XCTAssertTrue(limits.contactGroupsEnabled)
        XCTAssertTrue(limits.customMessagesEnabled)
        XCTAssertTrue(limits.exportEnabled)
        XCTAssertTrue(limits.familySharingEnabled)
    }

    func testFeatureLimits_DecodesFreeTierJSON() throws {
        let json = """
        {
            "tier": "free",
            "is_premium": false,
            "contacts_per_trip": 2,
            "saved_trips_limit": 0,
            "history_days": 30,
            "extensions": [30],
            "visible_stats": 2,
            "widgets_enabled": false,
            "live_activity_enabled": false,
            "custom_intervals_enabled": false,
            "trip_map_enabled": false,
            "pinned_activities_limit": 0,
            "group_trips_enabled": false,
            "contact_groups_enabled": false,
            "custom_messages_enabled": false,
            "export_enabled": false,
            "family_sharing_enabled": false
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let limits = try decoder.decode(FeatureLimits.self, from: json)

        XCTAssertEqual(limits.tier, "free")
        XCTAssertFalse(limits.isPremium)
        XCTAssertEqual(limits.contactsPerTrip, 2)
        XCTAssertEqual(limits.savedTripsLimit, 0)
        XCTAssertEqual(limits.historyDays, 30)
        XCTAssertEqual(limits.extensions, [30])
        XCTAssertEqual(limits.visibleStats, 2)
        XCTAssertFalse(limits.widgetsEnabled)
        XCTAssertFalse(limits.liveActivityEnabled)
    }

    // MARK: - FeatureLimits Static Defaults Tests

    func testFeatureLimits_FreeDefaults() {
        let free = FeatureLimits.free

        XCTAssertEqual(free.tier, "free")
        XCTAssertFalse(free.isPremium)
        XCTAssertEqual(free.contactsPerTrip, 2)
        XCTAssertEqual(free.savedTripsLimit, 0)
        XCTAssertEqual(free.historyDays, 30)
        XCTAssertEqual(free.extensions, [30])
        XCTAssertEqual(free.visibleStats, 2)
        XCTAssertFalse(free.widgetsEnabled)
        XCTAssertFalse(free.liveActivityEnabled)
        XCTAssertFalse(free.customIntervalsEnabled)
        XCTAssertFalse(free.tripMapEnabled)
        XCTAssertEqual(free.pinnedActivitiesLimit, 0)
        XCTAssertFalse(free.groupTripsEnabled)
        XCTAssertFalse(free.contactGroupsEnabled)
        XCTAssertFalse(free.customMessagesEnabled)
        XCTAssertFalse(free.exportEnabled)
        XCTAssertFalse(free.familySharingEnabled)
    }

    func testFeatureLimits_PlusDefaults() {
        let plus = FeatureLimits.plus

        XCTAssertEqual(plus.tier, "plus")
        XCTAssertTrue(plus.isPremium)
        XCTAssertEqual(plus.contactsPerTrip, 5)
        XCTAssertEqual(plus.savedTripsLimit, 10)
        XCTAssertNil(plus.historyDays) // Unlimited
        XCTAssertEqual(plus.extensions, [30, 60, 120, 180, 240])
        XCTAssertEqual(plus.visibleStats, 8)
        XCTAssertTrue(plus.widgetsEnabled)
        XCTAssertTrue(plus.liveActivityEnabled)
        XCTAssertTrue(plus.customIntervalsEnabled)
        XCTAssertTrue(plus.tripMapEnabled)
        XCTAssertEqual(plus.pinnedActivitiesLimit, 3)
        XCTAssertTrue(plus.groupTripsEnabled)
        XCTAssertTrue(plus.contactGroupsEnabled)
        XCTAssertTrue(plus.customMessagesEnabled)
        XCTAssertTrue(plus.exportEnabled)
        XCTAssertTrue(plus.familySharingEnabled)
    }

    func testFeatureLimits_FreeTierHasRestrictedExtensions() {
        let free = FeatureLimits.free
        let plus = FeatureLimits.plus

        XCTAssertEqual(free.extensions.count, 1)
        XCTAssertEqual(free.extensions, [30])
        XCTAssertGreaterThan(plus.extensions.count, 1)
        XCTAssertTrue(plus.extensions.contains(30))
        XCTAssertTrue(plus.extensions.contains(60))
        XCTAssertTrue(plus.extensions.contains(120))
    }

    func testFeatureLimits_FreeTierHasLimitedHistory() {
        let free = FeatureLimits.free
        let plus = FeatureLimits.plus

        XCTAssertEqual(free.historyDays, 30)
        XCTAssertNil(plus.historyDays) // nil = unlimited
    }

    // MARK: - SubscriptionStatusResponse Tests

    func testSubscriptionStatusResponse_DecodesActiveSubscription() throws {
        let json = """
        {
            "tier": "plus",
            "is_active": true,
            "expires_at": "2025-12-31T23:59:59Z",
            "auto_renew": true,
            "is_family_shared": false,
            "is_trial": false,
            "product_id": "com.homeboundapp.homebound.plus.monthly"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let status = try decoder.decode(SubscriptionStatusResponse.self, from: json)

        XCTAssertEqual(status.tier, "plus")
        XCTAssertTrue(status.isActive)
        XCTAssertEqual(status.expiresAt, "2025-12-31T23:59:59Z")
        XCTAssertTrue(status.autoRenew)
        XCTAssertFalse(status.isFamilyShared)
        XCTAssertFalse(status.isTrial)
        XCTAssertEqual(status.productId, "com.homeboundapp.homebound.plus.monthly")
    }

    func testSubscriptionStatusResponse_DecodesFreeUser() throws {
        let json = """
        {
            "tier": "free",
            "is_active": false,
            "expires_at": null,
            "auto_renew": false,
            "is_family_shared": false,
            "is_trial": false,
            "product_id": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let status = try decoder.decode(SubscriptionStatusResponse.self, from: json)

        XCTAssertEqual(status.tier, "free")
        XCTAssertFalse(status.isActive)
        XCTAssertNil(status.expiresAt)
        XCTAssertFalse(status.autoRenew)
        XCTAssertNil(status.productId)
    }

    func testSubscriptionStatusResponse_DecodesTrialSubscription() throws {
        let json = """
        {
            "tier": "plus",
            "is_active": true,
            "expires_at": "2025-01-15T23:59:59Z",
            "auto_renew": true,
            "is_family_shared": false,
            "is_trial": true,
            "product_id": "com.homeboundapp.homebound.plus.yearly"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let status = try decoder.decode(SubscriptionStatusResponse.self, from: json)

        XCTAssertTrue(status.isActive)
        XCTAssertTrue(status.isTrial)
        XCTAssertTrue(status.autoRenew)
    }

    func testSubscriptionStatusResponse_DecodesCancelledSubscription() throws {
        let json = """
        {
            "tier": "plus",
            "is_active": true,
            "expires_at": "2025-02-28T23:59:59Z",
            "auto_renew": false,
            "is_family_shared": false,
            "is_trial": false,
            "product_id": "com.homeboundapp.homebound.plus.monthly"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let status = try decoder.decode(SubscriptionStatusResponse.self, from: json)

        XCTAssertTrue(status.isActive)
        XCTAssertFalse(status.autoRenew) // Cancelled = will not auto-renew
    }

    func testSubscriptionStatusResponse_DecodesFamilyShared() throws {
        let json = """
        {
            "tier": "plus",
            "is_active": true,
            "expires_at": "2025-12-31T23:59:59Z",
            "auto_renew": true,
            "is_family_shared": true,
            "is_trial": false,
            "product_id": "com.homeboundapp.homebound.plus.yearly"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let status = try decoder.decode(SubscriptionStatusResponse.self, from: json)

        XCTAssertTrue(status.isFamilyShared)
    }

    // MARK: - VerifyPurchaseRequest Encoding Tests

    func testVerifyPurchaseRequest_EncodesToJSON() throws {
        let request = VerifyPurchaseRequest(
            transactionId: "txn_123456",
            originalTransactionId: "orig_123456",
            productId: "com.homeboundapp.homebound.plus.monthly",
            purchaseDate: "2025-01-01T12:00:00Z",
            expiresDate: "2025-02-01T12:00:00Z",
            environment: "sandbox",
            isFamilyShared: false,
            autoRenew: true,
            isTrial: false
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["transaction_id"] as? String, "txn_123456")
        XCTAssertEqual(json["original_transaction_id"] as? String, "orig_123456")
        XCTAssertEqual(json["product_id"] as? String, "com.homeboundapp.homebound.plus.monthly")
        XCTAssertEqual(json["purchase_date"] as? String, "2025-01-01T12:00:00Z")
        XCTAssertEqual(json["expires_date"] as? String, "2025-02-01T12:00:00Z")
        XCTAssertEqual(json["environment"] as? String, "sandbox")
        XCTAssertEqual(json["is_family_shared"] as? Bool, false)
        XCTAssertEqual(json["auto_renew"] as? Bool, true)
        XCTAssertEqual(json["is_trial"] as? Bool, false)
    }

    func testVerifyPurchaseRequest_EncodesTrialPurchase() throws {
        let request = VerifyPurchaseRequest(
            transactionId: "txn_trial_123",
            originalTransactionId: "orig_trial_123",
            productId: "com.homeboundapp.homebound.plus.yearly",
            purchaseDate: "2025-01-01T12:00:00Z",
            expiresDate: "2025-01-08T12:00:00Z", // 7 day trial
            environment: "sandbox",
            isFamilyShared: false,
            autoRenew: true,
            isTrial: true
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(json["is_trial"] as? Bool, true)
    }

    func testVerifyPurchaseRequest_EncodesNilExpiresDate() throws {
        let request = VerifyPurchaseRequest(
            transactionId: "txn_123",
            originalTransactionId: "orig_123",
            productId: "com.homeboundapp.homebound.plus.monthly",
            purchaseDate: "2025-01-01T12:00:00Z",
            expiresDate: nil,
            environment: "production",
            isFamilyShared: false,
            autoRenew: true,
            isTrial: false
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        // nil should encode as null or be absent
        XCTAssertTrue(json["expires_date"] == nil || json["expires_date"] is NSNull)
    }

    // MARK: - VerifyPurchaseResponse Tests

    func testVerifyPurchaseResponse_DecodesSuccessfulVerification() throws {
        let json = """
        {
            "ok": true,
            "tier": "plus",
            "expires_at": "2025-02-01T12:00:00Z",
            "message": "Purchase verified successfully"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let response = try decoder.decode(VerifyPurchaseResponse.self, from: json)

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.tier, "plus")
        XCTAssertEqual(response.expiresAt, "2025-02-01T12:00:00Z")
        XCTAssertEqual(response.message, "Purchase verified successfully")
    }

    func testVerifyPurchaseResponse_DecodesFailedVerification() throws {
        let json = """
        {
            "ok": false,
            "tier": "free",
            "expires_at": null,
            "message": "Invalid transaction"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let response = try decoder.decode(VerifyPurchaseResponse.self, from: json)

        XCTAssertFalse(response.ok)
        XCTAssertEqual(response.tier, "free")
        XCTAssertNil(response.expiresAt)
        XCTAssertEqual(response.message, "Invalid transaction")
    }

    // MARK: - PremiumFeature Enum Tests

    func testPremiumFeature_AllCases() {
        let allCases = PremiumFeature.allCases

        XCTAssertEqual(allCases.count, 14)
        XCTAssertTrue(allCases.contains(.moreContacts))
        XCTAssertTrue(allCases.contains(.savedTrips))
        XCTAssertTrue(allCases.contains(.unlimitedHistory))
        XCTAssertTrue(allCases.contains(.allExtensions))
        XCTAssertTrue(allCases.contains(.allStats))
        XCTAssertTrue(allCases.contains(.widgets))
        XCTAssertTrue(allCases.contains(.liveActivity))
        XCTAssertTrue(allCases.contains(.customIntervals))
        XCTAssertTrue(allCases.contains(.tripMap))
        XCTAssertTrue(allCases.contains(.pinnedActivities))
        XCTAssertTrue(allCases.contains(.groupTrips))
        XCTAssertTrue(allCases.contains(.contactGroups))
        XCTAssertTrue(allCases.contains(.customMessages))
        XCTAssertTrue(allCases.contains(.export))
    }

    func testPremiumFeature_RawValues() {
        XCTAssertEqual(PremiumFeature.moreContacts.rawValue, "More Contacts")
        XCTAssertEqual(PremiumFeature.savedTrips.rawValue, "Saved Trips")
        XCTAssertEqual(PremiumFeature.unlimitedHistory.rawValue, "Unlimited History")
        XCTAssertEqual(PremiumFeature.tripMap.rawValue, "Trip Map")
        XCTAssertEqual(PremiumFeature.groupTrips.rawValue, "Group Trips")
    }

    func testPremiumFeature_HasDescriptions() {
        for feature in PremiumFeature.allCases {
            XCTAssertFalse(feature.description.isEmpty, "\(feature.rawValue) should have a description")
            XCTAssertGreaterThan(feature.description.count, 10, "\(feature.rawValue) description should be meaningful")
        }
    }

    func testPremiumFeature_HasIcons() {
        for feature in PremiumFeature.allCases {
            XCTAssertFalse(feature.icon.isEmpty, "\(feature.rawValue) should have an icon")
            // SF Symbols typically contain a period or are single words
            XCTAssertTrue(feature.icon.contains(".") || feature.icon.count > 0)
        }
    }

    func testPremiumFeature_SpecificDescriptions() {
        XCTAssertTrue(PremiumFeature.moreContacts.description.lowercased().contains("5"))
        XCTAssertTrue(PremiumFeature.savedTrips.description.lowercased().contains("10"))
        XCTAssertTrue(PremiumFeature.allStats.description.lowercased().contains("8"))
        XCTAssertTrue(PremiumFeature.pinnedActivities.description.lowercased().contains("3"))
    }

    func testPremiumFeature_IconsAreSFSymbols() {
        // SF Symbols follow patterns like "name.modifier" or "name"
        let iconPattern = #"^[a-z0-9]+(\.[a-z0-9]+)*$"#
        let regex = try! NSRegularExpression(pattern: iconPattern, options: [])

        for feature in PremiumFeature.allCases {
            let range = NSRange(feature.icon.startIndex..., in: feature.icon)
            let match = regex.firstMatch(in: feature.icon, options: [], range: range)
            XCTAssertNotNil(match, "\(feature.rawValue) icon '\(feature.icon)' should be a valid SF Symbol name")
        }
    }

    // MARK: - PinnedActivity Tests

    func testPinnedActivity_DecodesFromJSON() throws {
        let json = """
        {
            "id": 1,
            "activity_id": 5,
            "activity_name": "Hiking",
            "activity_icon": "figure.hiking",
            "position": 0
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let pinnedActivity = try decoder.decode(PinnedActivity.self, from: json)

        XCTAssertEqual(pinnedActivity.id, 1)
        XCTAssertEqual(pinnedActivity.activityId, 5)
        XCTAssertEqual(pinnedActivity.activityName, "Hiking")
        XCTAssertEqual(pinnedActivity.activityIcon, "figure.hiking")
        XCTAssertEqual(pinnedActivity.position, 0)
    }

    func testPinnedActivity_Identifiable() {
        let json = """
        {
            "id": 42,
            "activity_id": 5,
            "activity_name": "Running",
            "activity_icon": "figure.run",
            "position": 1
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let pinnedActivity = try! decoder.decode(PinnedActivity.self, from: json)

        // Identifiable conformance uses id
        XCTAssertEqual(pinnedActivity.id, 42)
    }
}
