//
//  TripWidgetProvider.swift
//  HomeboundWidgets
//
//  Timeline provider for trip widgets
//

import WidgetKit
import SwiftUI

// MARK: - Widget Entry

struct TripWidgetEntry: TimelineEntry {
    let date: Date
    let tripData: WidgetTripData?
    /// Whether check-in was just confirmed (for showing checkmark)
    let showCheckinConfirmation: Bool

    /// Convenience: whether there's an active trip
    var hasActiveTrip: Bool {
        tripData != nil
    }

    init(date: Date, tripData: WidgetTripData?, showCheckinConfirmation: Bool = false) {
        self.date = date
        self.tripData = tripData
        self.showCheckinConfirmation = showCheckinConfirmation
    }
}

// MARK: - Timeline Provider

struct TripWidgetProvider: TimelineProvider {

    func placeholder(in context: Context) -> TripWidgetEntry {
        // Placeholder shown during widget gallery preview
        TripWidgetEntry(
            date: Date(),
            tripData: WidgetTripData.placeholder
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (TripWidgetEntry) -> Void) {
        // Snapshot for widget gallery
        let tripData = loadTripData()
        let entry = TripWidgetEntry(
            date: Date(),
            tripData: context.isPreview ? WidgetTripData.placeholder : tripData
        )
        completion(entry)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<TripWidgetEntry>) -> Void) {
        let tripData = loadTripData()
        let confirmationInfo = getCheckinConfirmationInfo()
        let now = Date()

        var entries: [TripWidgetEntry] = []

        if let trip = tripData {
            // If confirmation is active, create entries to show then hide the checkmark
            if let (showNow, hideAt) = confirmationInfo {
                if showNow {
                    // Entry now showing checkmark
                    entries.append(TripWidgetEntry(date: now, tripData: trip, showCheckinConfirmation: true))
                    // Entry when checkmark should hide
                    entries.append(TripWidgetEntry(date: hideAt, tripData: trip, showCheckinConfirmation: false))
                }
            }

            // Create regular entries (starting after confirmation period if applicable)
            let startTime = confirmationInfo?.1 ?? now
            let timeToETA = trip.etaAt.timeIntervalSince(now)

            if timeToETA > 3600 {
                // More than 1 hour away - update every 15 minutes
                for i in 0..<4 {
                    let entryDate = startTime.addingTimeInterval(Double(i) * 15 * 60)
                    if entryDate > now || entries.isEmpty {
                        entries.append(TripWidgetEntry(date: entryDate, tripData: trip, showCheckinConfirmation: false))
                    }
                }
            } else if timeToETA > 900 {
                // 15 min to 1 hour - update every 5 minutes
                for i in 0..<12 {
                    let entryDate = startTime.addingTimeInterval(Double(i) * 5 * 60)
                    if entryDate > now || entries.isEmpty {
                        entries.append(TripWidgetEntry(date: entryDate, tripData: trip, showCheckinConfirmation: false))
                    }
                }
            } else {
                // Less than 15 minutes - update every minute
                for i in 0..<15 {
                    let entryDate = startTime.addingTimeInterval(Double(i) * 60)
                    if entryDate > now || entries.isEmpty {
                        entries.append(TripWidgetEntry(date: entryDate, tripData: trip, showCheckinConfirmation: false))
                    }
                }
            }
        } else {
            // No active trip - single entry, refresh in 15 minutes
            entries.append(TripWidgetEntry(date: now, tripData: nil))
        }

        // Remove duplicate dates and sort
        var seenDates = Set<Date>()
        entries = entries.filter { seenDates.insert($0.date).inserted }
        entries.sort { $0.date < $1.date }

        // Refresh policy: after timeline ends or in 15 minutes max
        let refreshDate = entries.last?.date.addingTimeInterval(60) ?? now.addingTimeInterval(15 * 60)
        let timeline = Timeline(entries: entries, policy: .after(refreshDate))
        completion(timeline)
    }

    // MARK: - Private Helpers

    /// Check if check-in was just confirmed
    /// Returns (shouldShowNow, hideAtDate) if confirmation is active, nil otherwise
    private func getCheckinConfirmationInfo() -> (Bool, Date)? {
        guard let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier) else {
            return nil
        }
        let timestamp = defaults.double(forKey: LiveActivityConstants.checkinConfirmationKey)
        guard timestamp > 0 else { return nil }

        let confirmationTime = Date(timeIntervalSince1970: timestamp)
        let hideAt = confirmationTime.addingTimeInterval(5.0) // Show for 5 seconds
        let now = Date()

        // If we're still within the confirmation window
        if now < hideAt {
            return (true, hideAt)
        }

        return nil
    }

    private func loadTripData() -> WidgetTripData? {
        guard let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier),
              let jsonData = defaults.data(forKey: LiveActivityConstants.widgetTripDataKey) else {
            return nil
        }

        guard let dict = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any] else {
            return nil
        }

        // Parse the dictionary into WidgetTripData
        guard let id = dict["id"] as? Int,
              let title = dict["title"] as? String,
              let status = dict["status"] as? String,
              let activityName = dict["activityName"] as? String,
              let activityIcon = dict["activityIcon"] as? String,
              let primaryColor = dict["primaryColor"] as? String,
              let secondaryColor = dict["secondaryColor"] as? String,
              let startAtInterval = dict["startAt"] as? TimeInterval,
              let etaAtInterval = dict["etaAt"] as? TimeInterval,
              let graceMinutes = dict["graceMinutes"] as? Int,
              let checkinCount = dict["checkinCount"] as? Int else {
            return nil
        }

        let locationText = dict["locationText"] as? String
        let checkinToken = dict["checkinToken"] as? String
        let checkoutToken = dict["checkoutToken"] as? String
        let lastCheckinTimeInterval = dict["lastCheckinTime"] as? TimeInterval
        let lastCheckinTime = lastCheckinTimeInterval.map { Date(timeIntervalSince1970: $0) }

        return WidgetTripData(
            id: id,
            title: title,
            status: status,
            activityName: activityName,
            activityIcon: activityIcon,
            primaryColor: primaryColor,
            secondaryColor: secondaryColor,
            startAt: Date(timeIntervalSince1970: startAtInterval),
            etaAt: Date(timeIntervalSince1970: etaAtInterval),
            graceMinutes: graceMinutes,
            locationText: locationText,
            checkinToken: checkinToken,
            checkoutToken: checkoutToken,
            lastCheckinTime: lastCheckinTime,
            checkinCount: checkinCount
        )
    }
}

// MARK: - Placeholder Data

extension WidgetTripData {
    /// Placeholder data for widget gallery preview
    static var placeholder: WidgetTripData {
        WidgetTripData(
            id: 0,
            title: "Morning Hike",
            status: "active",
            activityName: "Hiking",
            activityIcon: "🥾",
            primaryColor: "#4CAF50",
            secondaryColor: "#81C784",
            startAt: Date().addingTimeInterval(-3600),
            etaAt: Date().addingTimeInterval(7200),
            graceMinutes: 30,
            locationText: "Blue Ridge Trail",
            checkinToken: nil,
            checkoutToken: nil,
            lastCheckinTime: nil,
            checkinCount: 0
        )
    }
}
