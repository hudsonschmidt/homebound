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

    /// Convenience: whether there's an active trip
    var hasActiveTrip: Bool {
        tripData != nil
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
        let now = Date()

        var entries: [TripWidgetEntry] = []

        if let trip = tripData {
            let timeToETA = trip.etaAt.timeIntervalSince(now)

            if timeToETA > 3600 {
                // More than 1 hour away - update every 15 minutes
                for i in 0..<4 {
                    let entryDate = now.addingTimeInterval(Double(i) * 15 * 60)
                    entries.append(TripWidgetEntry(date: entryDate, tripData: trip))
                }
            } else if timeToETA > 900 {
                // 15 min to 1 hour - update every 5 minutes
                for i in 0..<12 {
                    let entryDate = now.addingTimeInterval(Double(i) * 5 * 60)
                    entries.append(TripWidgetEntry(date: entryDate, tripData: trip))
                }
            } else {
                // Less than 15 minutes - update every minute
                for i in 0..<15 {
                    let entryDate = now.addingTimeInterval(Double(i) * 60)
                    entries.append(TripWidgetEntry(date: entryDate, tripData: trip))
                }
            }
        } else {
            // No active trip - single entry, refresh in 15 minutes
            entries.append(TripWidgetEntry(date: now, tripData: nil))
        }

        // Refresh policy: after timeline ends or in 15 minutes max
        let refreshDate = entries.last?.date.addingTimeInterval(60) ?? now.addingTimeInterval(15 * 60)
        let timeline = Timeline(entries: entries, policy: .after(refreshDate))
        completion(timeline)
    }

    // MARK: - Private Helpers

    private func loadTripData() -> WidgetTripData? {
        // Use the proper Codable accessor that handles ISO8601 date decoding correctly
        return LiveActivityConstants.widgetTripData
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
