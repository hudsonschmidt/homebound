import Foundation
@testable import Homebound

// MARK: - Test Fixtures

enum TestFixtures {

    // MARK: - Sample JSON Data

    static let activityJSON = """
    {
        "id": 1,
        "name": "Hiking",
        "icon": "figure.hiking",
        "default_grace_minutes": 30,
        "colors": {
            "primary": "#4CAF50",
            "secondary": "#81C784",
            "accent": "#2E7D32"
        },
        "messages": {
            "start": "Have a great hike!",
            "checkin": "How's the trail?",
            "checkout": "Welcome back!",
            "overdue": "Are you okay?",
            "encouragement": ["Keep going!", "You've got this!"]
        },
        "safety_tips": ["Tell someone your route", "Bring water"],
        "order": 1
    }
    """.data(using: .utf8)!

    static let tripJSON = """
    {
        "id": 1,
        "user_id": 100,
        "title": "Morning Hike",
        "activity": {
            "id": 1,
            "name": "Hiking",
            "icon": "figure.hiking",
            "default_grace_minutes": 30,
            "colors": {
                "primary": "#4CAF50",
                "secondary": "#81C784",
                "accent": "#2E7D32"
            },
            "messages": {
                "start": "Have a great hike!",
                "checkin": "How's the trail?",
                "checkout": "Welcome back!",
                "overdue": "Are you okay?",
                "encouragement": ["Keep going!"]
            },
            "safety_tips": ["Tell someone your route"],
            "order": 1
        },
        "start": "2025-12-05T10:30:00Z",
        "eta": "2025-12-05T14:30:00Z",
        "grace_min": 30,
        "status": "active",
        "location_text": "Mt. Tamalpais",
        "gen_lat": 37.9235,
        "gen_lon": -122.5965,
        "notes": "Taking the Dipsea trail",
        "created_at": "2025-12-05T08:00:00Z",
        "has_separate_locations": false,
        "notify_self": false,
        "share_live_location": false,
        "is_group_trip": false,
        "participant_count": 0
    }
    """.data(using: .utf8)!

    static let tripJSONWithCompletedAt = """
    {
        "id": 2,
        "user_id": 100,
        "title": "Completed Hike",
        "activity": {
            "id": 1,
            "name": "Hiking",
            "icon": "figure.hiking",
            "default_grace_minutes": 30,
            "colors": {
                "primary": "#4CAF50",
                "secondary": "#81C784",
                "accent": "#2E7D32"
            },
            "messages": {
                "start": "Have a great hike!",
                "checkin": "How's the trail?",
                "checkout": "Welcome back!",
                "overdue": "Are you okay?",
                "encouragement": ["Keep going!"]
            },
            "safety_tips": ["Tell someone your route"],
            "order": 1
        },
        "start": "2025-12-05T10:30:00Z",
        "eta": "2025-12-05T14:30:00Z",
        "grace_min": 30,
        "status": "completed",
        "completed_at": "2025-12-05T14:00:00Z",
        "location_text": "Mt. Tamalpais",
        "gen_lat": 37.9235,
        "gen_lon": -122.5965,
        "created_at": "2025-12-05T08:00:00Z",
        "has_separate_locations": false,
        "notify_self": false,
        "share_live_location": false,
        "is_group_trip": false,
        "participant_count": 0
    }
    """.data(using: .utf8)!

    static let friendJSON = """
    {
        "user_id": 42,
        "first_name": "Jane",
        "last_name": "Doe",
        "profile_photo_url": null,
        "member_since": "2024-01-15T00:00:00Z",
        "friendship_since": "2024-06-01T00:00:00Z",
        "age": 28,
        "achievements_count": 15,
        "total_achievements": 40,
        "total_trips": 25,
        "total_adventure_hours": 50,
        "favorite_activity_name": "Hiking",
        "favorite_activity_icon": "figure.hiking"
    }
    """.data(using: .utf8)!

    static let contactJSON = """
    {
        "id": 1,
        "user_id": 100,
        "name": "Emergency Contact",
        "email": "emergency@example.com"
    }
    """.data(using: .utf8)!

    static let timelineEventJSON = """
    {
        "kind": "checkin",
        "at": "2025-12-05T12:30:00.123456Z",
        "lat": 37.9235,
        "lon": -122.5965
    }
    """.data(using: .utf8)!

    static let groupSettingsJSON = """
    {
        "checkout_mode": "anyone",
        "vote_threshold": 0.5,
        "allow_participant_invites": false,
        "share_locations_between_participants": true
    }
    """.data(using: .utf8)!

    // MARK: - Subscription JSON Data

    static let featureLimitsPlusJSON = """
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

    static let featureLimitsFreeJSON = """
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

    static let subscriptionStatusActiveJSON = """
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

    static let subscriptionStatusTrialJSON = """
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

    static let subscriptionStatusCancelledJSON = """
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

    static let subscriptionStatusFreeJSON = """
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

    // MARK: - Factory Methods

    static func makeActivity(
        id: Int = 1,
        name: String = "Hiking",
        icon: String = "figure.hiking",
        defaultGraceMinutes: Int = 30
    ) -> Activity {
        Activity(
            id: id,
            name: name,
            icon: icon,
            default_grace_minutes: defaultGraceMinutes,
            colors: Activity.ActivityColors(
                primary: "#4CAF50",
                secondary: "#81C784",
                accent: "#2E7D32"
            ),
            messages: Activity.ActivityMessages(
                start: "Have a great trip!",
                checkin: "How's it going?",
                checkout: "Welcome back!",
                overdue: "Are you okay?",
                encouragement: ["Keep going!"]
            ),
            safety_tips: ["Tell someone your plans"],
            order: 1
        )
    }

    static func makeTrip(
        id: Int = 1,
        userId: Int = 100,
        title: String = "Test Trip",
        activity: Activity? = nil,
        startAt: Date = Date(),
        etaAt: Date = Date().addingTimeInterval(3600 * 4),
        graceMinutes: Int = 30,
        status: String = "active",
        completedAt: Date? = nil,
        locationText: String? = "Test Location"
    ) -> Trip {
        Trip(
            id: id,
            user_id: userId,
            title: title,
            activity: activity ?? makeActivity(),
            start_at: startAt,
            eta_at: etaAt,
            grace_minutes: graceMinutes,
            location_text: locationText,
            location_lat: 37.9235,
            location_lng: -122.5965,
            start_location_text: nil,
            start_lat: nil,
            start_lng: nil,
            has_separate_locations: false,
            notes: nil,
            status: status,
            completed_at: completedAt,
            last_checkin: nil,
            created_at: "2025-12-05T08:00:00Z",
            contact1: nil,
            contact2: nil,
            contact3: nil,
            friend_contact1: nil,
            friend_contact2: nil,
            friend_contact3: nil,
            checkin_token: nil,
            checkout_token: nil,
            checkin_interval_min: 30,
            notify_start_hour: nil,
            notify_end_hour: nil,
            timezone: nil,
            start_timezone: nil,
            eta_timezone: nil,
            notify_self: false,
            share_live_location: false,
            is_group_trip: false,
            group_settings: nil,
            participant_count: 0
        )
    }

    static func makeContact(
        id: Int = 1,
        userId: Int = 100,
        name: String = "Emergency Contact",
        email: String = "emergency@example.com",
        group: String? = nil
    ) -> Contact {
        Contact(id: id, user_id: userId, name: name, email: email, group: group)
    }

    static func makeFriend(
        userId: Int = 42,
        firstName: String = "Jane",
        lastName: String = "Doe",
        totalAdventureHours: Int? = 50,
        achievementsCount: Int? = 15,
        totalAchievements: Int? = 40
    ) -> Friend {
        Friend(
            user_id: userId,
            first_name: firstName,
            last_name: lastName,
            profile_photo_url: nil,
            member_since: "2024-01-15T00:00:00Z",
            friendship_since: "2024-06-01T00:00:00Z",
            age: 28,
            achievements_count: achievementsCount,
            total_achievements: totalAchievements,
            total_trips: 25,
            total_adventure_hours: totalAdventureHours,
            favorite_activity_name: "Hiking",
            favorite_activity_icon: "figure.hiking"
        )
    }
}
