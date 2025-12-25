//
//  TripStateManager.swift
//  Homebound
//
//  Unified state management for trips across app, widget, and Live Activity.
//  Single source of truth to prevent sync issues between components.
//

import Foundation
import WidgetKit
import Combine

// MARK: - Widget Trip Data
// Note: This struct must match the one in HomeboundWidgets/WidgetSharedData.swift
// If you modify this, update both locations.

/// Simplified trip data for widget display.
/// Stored in shared UserDefaults (App Group) by main app.
struct WidgetTripData: Codable {
    let id: Int
    let title: String
    let status: String              // "active", "overdue", "overdue_notified"
    let activityName: String
    let activityIcon: String        // SF Symbol name
    let primaryColor: String        // hex color
    let secondaryColor: String      // hex color
    let startAt: Date
    let etaAt: Date
    let graceMinutes: Int
    let locationText: String?
    let checkinToken: String?
    let checkoutToken: String?
    let lastCheckinTime: Date?
    let checkinCount: Int

    // MARK: - Computed Properties

    /// Whether the trip is past ETA + grace period
    var isOverdue: Bool {
        let deadline = etaAt.addingTimeInterval(TimeInterval(graceMinutes * 60))
        return Date() > deadline
    }

    /// Whether contacts have been notified
    var contactsNotified: Bool {
        status == "overdue_notified"
    }

    /// Time remaining until ETA (negative if past)
    var timeRemaining: TimeInterval {
        etaAt.timeIntervalSince(Date())
    }

    /// Formatted time remaining string (e.g., "2h 30m")
    var formattedTimeRemaining: String {
        let remaining = timeRemaining

        if remaining <= 0 {
            let overdue = abs(remaining)
            if overdue < 60 {
                return "Now"
            } else if overdue < 3600 {
                let minutes = Int(overdue / 60)
                return "\(minutes)m overdue"
            } else {
                let hours = Int(overdue / 3600)
                let minutes = Int((overdue.truncatingRemainder(dividingBy: 3600)) / 60)
                if minutes > 0 {
                    return "\(hours)h \(minutes)m overdue"
                }
                return "\(hours)h overdue"
            }
        }

        if remaining < 60 {
            return "<1m"
        } else if remaining < 3600 {
            let minutes = Int(remaining / 60)
            return "\(minutes)m"
        } else {
            let hours = Int(remaining / 3600)
            let minutes = Int((remaining.truncatingRemainder(dividingBy: 3600)) / 60)
            if minutes > 0 {
                return "\(hours)h \(minutes)m"
            }
            return "\(hours)h"
        }
    }

    /// Status text for display
    var statusText: String {
        if contactsNotified { return "OVERDUE" }
        if isOverdue { return "CHECK IN NOW" }
        return "ACTIVE"
    }
}

// MARK: - Trip State Manager

/// Coordinates trip state updates between Session, Widget, and Live Activity
/// to ensure all components display consistent data.
@MainActor
final class TripStateManager: ObservableObject {

    // MARK: - Singleton

    static let shared = TripStateManager()

    // MARK: - Published State

    /// Current check-in count for the active trip (for optimistic UI updates)
    @Published private(set) var checkinCount: Int = 0

    /// Version number incremented on each update (for staleness detection)
    @Published private(set) var stateVersion: Int = 0

    /// Last update timestamp
    @Published private(set) var lastUpdatedAt: Date?

    // MARK: - Private Properties

    private let appGroupIdentifier = "group.com.homeboundapp.Homebound"
    private let widgetTripDataKey = "widgetTripData"

    private var sharedDefaults: UserDefaults? {
        UserDefaults(suiteName: appGroupIdentifier)
    }

    // MARK: - Initialization

    private init() {
        // Load persisted check-in count if available
        if let defaults = sharedDefaults {
            checkinCount = defaults.integer(forKey: "tripStateManagerCheckinCount")
            stateVersion = defaults.integer(forKey: "tripStateManagerVersion")
        }
        debugLog("[TripStateManager] Initialized with checkinCount=\(checkinCount), version=\(stateVersion)")
    }

    // MARK: - Public Methods

    /// Update trip state across all systems (widget, live activity)
    /// Call this after any trip modification (start, check-in, extend, complete)
    /// - Parameters:
    ///   - trip: The updated trip data
    ///   - checkinCount: Number of check-ins performed
    func updateTripState(trip: Trip, checkinCount: Int) {
        debugLog("[TripStateManager] Updating state for trip #\(trip.id), checkinCount=\(checkinCount)")

        // Update local state
        self.checkinCount = checkinCount
        self.stateVersion += 1
        self.lastUpdatedAt = Date()

        // Persist state
        persistState()

        // Update widget data
        saveWidgetTripData(trip: trip, checkinCount: checkinCount)

        // Notify widgets to reload
        reloadWidgets()

        // Update Live Activity
        Task {
            await LiveActivityManager.shared.restoreActivityIfNeeded(for: trip, checkinCount: checkinCount)
        }
    }

    /// Optimistic check-in: immediately increment count before API call completes
    /// Returns the new check-in count for immediate UI feedback
    /// - Parameter trip: The current active trip
    /// - Returns: The new optimistic check-in count
    func optimisticCheckin(trip: Trip) -> Int {
        let newCount = checkinCount + 1
        debugLog("[TripStateManager] Optimistic check-in: \(checkinCount) -> \(newCount)")

        // Update local state immediately
        self.checkinCount = newCount
        self.stateVersion += 1
        self.lastUpdatedAt = Date()

        // Persist state
        persistState()

        // Update widget data with optimistic count
        saveWidgetTripData(trip: trip, checkinCount: newCount)

        // Notify widgets to reload
        reloadWidgets()

        // Update Live Activity with optimistic count
        Task {
            await LiveActivityManager.shared.updateActivity(with: trip, checkinCount: newCount)
        }

        return newCount
    }

    /// Rollback optimistic check-in if API call fails
    /// - Parameter previousCount: The count before the optimistic update
    func rollbackCheckin(to previousCount: Int, trip: Trip) {
        debugLog("[TripStateManager] Rolling back check-in: \(checkinCount) -> \(previousCount)")

        self.checkinCount = previousCount
        self.stateVersion += 1
        self.lastUpdatedAt = Date()

        persistState()
        saveWidgetTripData(trip: trip, checkinCount: previousCount)
        reloadWidgets()

        Task {
            await LiveActivityManager.shared.updateActivity(with: trip, checkinCount: previousCount)
        }
    }

    /// Clear all trip state (call when trip is completed or cancelled)
    func clearTripState() {
        debugLog("[TripStateManager] Clearing trip state")

        self.checkinCount = 0
        self.stateVersion += 1
        self.lastUpdatedAt = Date()

        persistState()

        // Clear widget data
        clearWidgetData()

        // Notify widgets
        reloadWidgets()

        // End Live Activity
        Task {
            await LiveActivityManager.shared.endAllActivities()
        }
    }

    /// Start a new trip and initialize state
    /// - Parameters:
    ///   - trip: The new trip
    ///   - checkinCount: Initial check-in count (usually 0)
    func startTrip(_ trip: Trip, checkinCount: Int = 0) {
        debugLog("[TripStateManager] Starting trip #\(trip.id)")

        self.checkinCount = checkinCount
        self.stateVersion += 1
        self.lastUpdatedAt = Date()

        persistState()
        saveWidgetTripData(trip: trip, checkinCount: checkinCount)
        reloadWidgets()

        Task {
            await LiveActivityManager.shared.startActivity(for: trip, checkinCount: checkinCount)
        }
    }

    // MARK: - Widget Data

    private func saveWidgetTripData(trip: Trip, checkinCount: Int) {
        guard let defaults = sharedDefaults else {
            debugLog("[TripStateManager] Failed to access shared defaults for widget data")
            return
        }

        let widgetData = WidgetTripData(
            id: trip.id,
            title: trip.title,
            status: trip.status,
            activityName: trip.activity.name,
            activityIcon: trip.activity.icon,
            primaryColor: trip.activity.colors.primary,
            secondaryColor: trip.activity.colors.secondary,
            startAt: trip.start_at,
            etaAt: trip.eta_at,
            graceMinutes: trip.grace_minutes,
            locationText: trip.location_text,
            checkinToken: trip.checkin_token,
            checkoutToken: trip.checkout_token,
            lastCheckinTime: parseLastCheckin(trip.last_checkin),
            checkinCount: checkinCount
        )

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601

        if let data = try? encoder.encode(widgetData) {
            defaults.set(data, forKey: widgetTripDataKey)
            debugLog("[TripStateManager] Widget data saved for trip #\(trip.id)")
        } else {
            debugLog("[TripStateManager] Failed to encode widget data")
        }
    }

    private func clearWidgetData() {
        guard let defaults = sharedDefaults else { return }
        defaults.removeObject(forKey: widgetTripDataKey)
        debugLog("[TripStateManager] Widget data cleared")
    }

    private func reloadWidgets() {
        WidgetCenter.shared.reloadAllTimelines()
        debugLog("[TripStateManager] Widget timelines reloaded")
    }

    // MARK: - Persistence

    private func persistState() {
        guard let defaults = sharedDefaults else { return }
        defaults.set(checkinCount, forKey: "tripStateManagerCheckinCount")
        defaults.set(stateVersion, forKey: "tripStateManagerVersion")
    }

    // MARK: - Helpers

    private func parseLastCheckin(_ checkin: String?) -> Date? {
        guard let checkin = checkin else { return nil }
        return DateUtils.parseISO8601(checkin)
    }
}
