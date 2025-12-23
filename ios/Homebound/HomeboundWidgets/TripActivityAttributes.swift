//
//  TripActivityAttributes.swift
//  HomeboundWidgets
//
//  Live Activity attributes for tracking active trips
//

import ActivityKit
import Foundation

// MARK: - Display Mode

enum LiveActivityDisplayMode: String, Codable, CaseIterable {
    case minimal = "minimal"
    case standard = "standard"
    case full = "full"

    var displayName: String {
        switch self {
        case .minimal: return "Minimal"
        case .standard: return "Standard"
        case .full: return "Full"
        }
    }

    var description: String {
        switch self {
        case .minimal: return "ETA countdown only"
        case .standard: return "Countdown, activity, and title"
        case .full: return "All trip details and locations"
        }
    }
}

// MARK: - Activity Attributes

@available(iOS 16.1, *)
struct TripLiveActivityAttributes: ActivityAttributes {

    // MARK: - Content State (Dynamic - can be updated)

    struct ContentState: Codable, Hashable {
        /// Trip status: "active", "overdue", "overdue_notified"
        var status: String
        /// Expected arrival time
        var eta: Date
        /// When grace period expires (ETA + grace minutes)
        var graceEnd: Date
        /// Last check-in timestamp (if any)
        var lastCheckinTime: Date?
        /// Whether the trip is past ETA + grace period
        var isOverdue: Bool
        /// Number of check-ins performed during this trip
        var checkinCount: Int

        /// Computed property for status display (matches Active Trip Card)
        var statusText: String {
            if contactsNotified { return "OVERDUE" }
            if isOverdue { return "CHECK IN NOW" }
            if status == "overdue" { return "CHECK IN NOW" }  // Past ETA, in grace period
            return "ACTIVE TRIP"
        }

        /// Whether contacts have been notified
        var contactsNotified: Bool {
            status == "overdue_notified"
        }

        /// Whether past ETA (in grace period or beyond)
        var isPastETA: Bool {
            status == "overdue" || status == "overdue_notified"
        }
    }

    // MARK: - Static Attributes (Set once when activity starts)

    /// Trip ID for identification
    let tripId: Int

    /// Trip title (e.g., "Morning Hike")
    let title: String

    /// SF Symbol name for the activity icon
    let activityIcon: String

    /// Activity name (e.g., "Hiking", "Driving")
    let activityName: String

    /// Primary color hex from activity colors
    let primaryColor: String

    /// Secondary color hex from activity colors
    let secondaryColor: String

    /// Starting location text (optional)
    let startLocation: String?

    /// Destination location text (optional)
    let endLocation: String?

    /// Token for check-in deep link
    let checkinToken: String?

    /// Token for checkout/complete deep link
    let checkoutToken: String?

    /// Grace period in minutes
    let graceMinutes: Int

    /// Trip start time
    let startTime: Date
}

// MARK: - App Group Constants

struct LiveActivityConstants {
    static let appGroupIdentifier = "group.com.homeboundapp.Homebound"
    static let displayModeKey = "liveActivityDisplayMode"
    static let enabledKey = "liveActivityEnabled"
    static let activityIdKey = "currentLiveActivityId"

    // Cross-process signaling for Live Activity actions
    static let pendingCheckinKey = "pendingCheckinAction"
    static let pendingCheckoutKey = "pendingCheckoutAction"
    static let darwinNotificationName = "com.homeboundapp.liveactivity.action"

    // Widget data sharing
    static let widgetTripDataKey = "widgetTripData"

    // Check-in confirmation feedback (timestamp when check-in button was pressed)
    static let checkinConfirmationKey = "checkinConfirmationTimestamp"

    /// Base URL for deep links
    static let baseURL = "https://api.homeboundapp.com"

    /// Get the shared UserDefaults for app group
    static var sharedDefaults: UserDefaults? {
        UserDefaults(suiteName: appGroupIdentifier)
    }

    /// Get current display mode from shared defaults
    static var displayMode: LiveActivityDisplayMode {
        guard let defaults = sharedDefaults,
              let rawValue = defaults.string(forKey: displayModeKey),
              let mode = LiveActivityDisplayMode(rawValue: rawValue) else {
            return .standard
        }
        return mode
    }

    /// Check if Live Activities are enabled in settings
    static var isEnabled: Bool {
        guard let defaults = sharedDefaults else { return true }
        // Default to true if not set
        if defaults.object(forKey: enabledKey) == nil {
            return true
        }
        return defaults.bool(forKey: enabledKey)
    }
}
