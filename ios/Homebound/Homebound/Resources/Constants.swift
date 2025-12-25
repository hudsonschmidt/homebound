import Foundation
import CoreLocation

/// Centralized constants for the Homebound app
enum Constants {
    // MARK: - Trip Status
    enum TripStatus {
        /// Statuses considered "active" for trip display and filtering
        static let activeStatuses: Set<String> = ["active", "overdue", "overdue_notified"]

        /// Check if a status is considered active
        static func isActive(_ status: String) -> Bool {
            activeStatuses.contains(status)
        }
    }

    // MARK: - Time Intervals (in seconds)
    enum Time {
        static let oneMinute: TimeInterval = 60
        static let oneHour: TimeInterval = 3600
        static let twoHours: TimeInterval = 7200
        static let oneDay: TimeInterval = 86400

        /// Default ETA offset from current time when creating a new trip
        static let defaultETAOffset: TimeInterval = twoHours
    }

    // MARK: - Map Defaults
    enum Map {
        /// Default center (San Francisco) used when user location is unavailable
        static let defaultCenter = CLLocationCoordinate2D(
            latitude: 37.7749,
            longitude: -122.4194
        )

        /// Default span for initial map view
        static let defaultSpanDelta: Double = 50

        /// Zoomed span when focusing on user location
        static let zoomedSpanDelta: Double = 0.5
    }
}
