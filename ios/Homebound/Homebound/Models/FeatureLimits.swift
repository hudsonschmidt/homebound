import Foundation

/// Feature limits based on subscription tier.
///
/// These limits are fetched from the backend and cached locally for offline use.
/// The backend is the source of truth for subscription status.
struct FeatureLimits: Codable {
    let tier: String
    let isPremium: Bool
    let contactsPerTrip: Int
    let savedTripsLimit: Int
    let historyDays: Int?  // nil = unlimited
    let extensions: [Int]  // Available extension durations in minutes
    let visibleStats: Int
    let widgetsEnabled: Bool
    let liveActivityEnabled: Bool
    let customIntervalsEnabled: Bool
    let tripMapEnabled: Bool  // Access to the Trip Map tab
    let pinnedActivitiesLimit: Int
    let groupTripsEnabled: Bool
    let contactGroupsEnabled: Bool
    let customMessagesEnabled: Bool
    let exportEnabled: Bool
    let familySharingEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case tier
        case isPremium = "is_premium"
        case contactsPerTrip = "contacts_per_trip"
        case savedTripsLimit = "saved_trips_limit"
        case historyDays = "history_days"
        case extensions
        case visibleStats = "visible_stats"
        case widgetsEnabled = "widgets_enabled"
        case liveActivityEnabled = "live_activity_enabled"
        case customIntervalsEnabled = "custom_intervals_enabled"
        case tripMapEnabled = "trip_map_enabled"
        case pinnedActivitiesLimit = "pinned_activities_limit"
        case groupTripsEnabled = "group_trips_enabled"
        case contactGroupsEnabled = "contact_groups_enabled"
        case customMessagesEnabled = "custom_messages_enabled"
        case exportEnabled = "export_enabled"
        case familySharingEnabled = "family_sharing_enabled"
    }

    /// Free tier defaults (used as fallback when offline without cached data)
    static let free = FeatureLimits(
        tier: "free",
        isPremium: false,
        contactsPerTrip: 2,
        savedTripsLimit: 0,
        historyDays: 30,
        extensions: [30],
        visibleStats: 2,
        widgetsEnabled: false,
        liveActivityEnabled: false,
        customIntervalsEnabled: false,
        tripMapEnabled: false,
        pinnedActivitiesLimit: 0,
        groupTripsEnabled: false,
        contactGroupsEnabled: false,
        customMessagesEnabled: false,
        exportEnabled: false,
        familySharingEnabled: false
    )

    /// Plus tier defaults (used as fallback when offline with valid subscription)
    static let plus = FeatureLimits(
        tier: "plus",
        isPremium: true,
        contactsPerTrip: 5,
        savedTripsLimit: 10,
        historyDays: nil,
        extensions: [30, 60, 120, 180, 240],
        visibleStats: 8,
        widgetsEnabled: true,
        liveActivityEnabled: true,
        customIntervalsEnabled: true,
        tripMapEnabled: true,
        pinnedActivitiesLimit: 3,
        groupTripsEnabled: true,
        contactGroupsEnabled: true,
        customMessagesEnabled: true,
        exportEnabled: true,
        familySharingEnabled: true
    )
}

/// Subscription status from the backend
struct SubscriptionStatusResponse: Codable {
    let tier: String
    let isActive: Bool
    let expiresAt: String?
    let autoRenew: Bool
    let isFamilyShared: Bool
    let isTrial: Bool
    let productId: String?

    enum CodingKeys: String, CodingKey {
        case tier
        case isActive = "is_active"
        case expiresAt = "expires_at"
        case autoRenew = "auto_renew"
        case isFamilyShared = "is_family_shared"
        case isTrial = "is_trial"
        case productId = "product_id"
    }
}

/// Request to verify a purchase with the backend
struct VerifyPurchaseRequest: Encodable {
    let transactionId: String
    let originalTransactionId: String
    let productId: String
    let purchaseDate: String
    let expiresDate: String?
    let environment: String
    let isFamilyShared: Bool
    let autoRenew: Bool
    let isTrial: Bool

    enum CodingKeys: String, CodingKey {
        case transactionId = "transaction_id"
        case originalTransactionId = "original_transaction_id"
        case productId = "product_id"
        case purchaseDate = "purchase_date"
        case expiresDate = "expires_date"
        case environment
        case isFamilyShared = "is_family_shared"
        case autoRenew = "auto_renew"
        case isTrial = "is_trial"
    }
}

/// Response from purchase verification
struct VerifyPurchaseResponse: Codable {
    let ok: Bool
    let tier: String
    let expiresAt: String?
    let message: String

    enum CodingKeys: String, CodingKey {
        case ok
        case tier
        case expiresAt = "expires_at"
        case message
    }
}

/// Pinned activity from the backend
struct PinnedActivity: Codable, Identifiable {
    let id: Int
    let activityId: Int
    let activityName: String
    let activityIcon: String
    let position: Int

    enum CodingKeys: String, CodingKey {
        case id
        case activityId = "activity_id"
        case activityName = "activity_name"
        case activityIcon = "activity_icon"
        case position
    }
}

/// Premium feature types for paywall context
enum PremiumFeature: String, CaseIterable {
    case moreContacts = "More Contacts"
    case savedTrips = "Saved Trips"
    case unlimitedHistory = "Unlimited History"
    case allExtensions = "All Extensions"
    case allStats = "All Stats"
    case widgets = "Widgets"
    case liveActivity = "Live Activity"
    case customIntervals = "Custom Intervals"
    case tripMap = "Trip Map"
    case pinnedActivities = "Favorite Activities"
    case groupTrips = "Group Trips"
    case contactGroups = "Contact Groups"
    case customMessages = "Custom Messages"
    case export = "Export Data"

    var description: String {
        switch self {
        case .moreContacts: return "Add up to 5 safety contacts per trip"
        case .savedTrips: return "Save up to 10 trip templates for quick reuse"
        case .unlimitedHistory: return "View your complete trip history"
        case .allExtensions: return "Access all time extension options"
        case .allStats: return "See all 8 adventure statistics"
        case .widgets: return "Add Homebound widgets to your home screen"
        case .liveActivity: return "Track trips with Dynamic Island and Live Activities"
        case .customIntervals: return "Customize grace periods and check-in intervals"
        case .tripMap: return "See all your adventures on an interactive map"
        case .pinnedActivities: return "Pin your 3 favorite activities for quick access"
        case .groupTrips: return "Create trips with multiple participants"
        case .contactGroups: return "Organize contacts into reusable groups"
        case .customMessages: return "Customize notification messages to contacts"
        case .export: return "Export your trip data"
        }
    }

    var icon: String {
        switch self {
        case .moreContacts: return "person.3.fill"
        case .savedTrips: return "bookmark.fill"
        case .unlimitedHistory: return "clock.arrow.circlepath"
        case .allExtensions: return "timer"
        case .allStats: return "chart.bar.fill"
        case .widgets: return "square.grid.2x2.fill"
        case .liveActivity: return "iphone.radiowaves.left.and.right"
        case .customIntervals: return "slider.horizontal.3"
        case .tripMap: return "map.fill"
        case .pinnedActivities: return "star.fill"
        case .groupTrips: return "person.2.fill"
        case .contactGroups: return "folder.fill.badge.person.crop"
        case .customMessages: return "text.bubble.fill"
        case .export: return "square.and.arrow.up"
        }
    }
}
