//
//  WidgetSharedData.swift
//  HomeboundWidgets
//
//  Helper extensions for accessing shared widget data.
//

import Foundation

// MARK: - Widget Trip Data
// Note: This struct must match the one in the main app (TripStateManager.swift)
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

// MARK: - LiveActivityConstants Extension

extension LiveActivityConstants {
    /// Get current widget trip data from shared defaults
    static var widgetTripData: WidgetTripData? {
        guard let defaults = sharedDefaults,
              let data = defaults.data(forKey: widgetTripDataKey) else {
            return nil
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        do {
            return try decoder.decode(WidgetTripData.self, from: data)
        } catch {
            // Decode failure - can happen if schema changes
            return nil
        }
    }

    /// Save widget trip data to shared defaults
    static func saveWidgetTripData(_ tripData: WidgetTripData?) {
        guard let defaults = sharedDefaults else { return }

        if let tripData = tripData {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            if let data = try? encoder.encode(tripData) {
                defaults.set(data, forKey: widgetTripDataKey)
            }
        } else {
            defaults.removeObject(forKey: widgetTripDataKey)
        }
    }
}
