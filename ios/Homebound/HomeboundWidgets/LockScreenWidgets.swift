//
//  LockScreenWidgets.swift
//  HomeboundWidgets
//
//  Lock screen accessory widgets for quick trip status
//

import WidgetKit
import SwiftUI

// MARK: - Circular Lock Screen Widget

struct LockScreenCircularWidget: Widget {
    let kind: String = "LockScreenCircularWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: TripWidgetProvider()) { entry in
            LockScreenCircularView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Trip Status")
        .description("Activity icon with progress indicator.")
        .supportedFamilies([.accessoryCircular])
    }
}

struct LockScreenCircularView: View {
    let entry: TripWidgetEntry

    var body: some View {
        // Check if widgets are enabled (premium feature)
        if !LiveActivityConstants.widgetsEnabled {
            UpgradePremiumCircularView()
        } else if let trip = entry.tripData {
            ActiveCircularView(trip: trip)
        } else {
            NoTripCircularView()
        }
    }
}

private struct UpgradePremiumCircularView: View {
    var body: some View {
        ZStack {
            Circle()
                .stroke(lineWidth: 4)
                .opacity(0.3)

            Image(systemName: "star.fill")
                .font(.title2)
        }
    }
}

private struct ActiveCircularView: View {
    let trip: WidgetTripData

    /// Progress from 0 to 1 based on time elapsed vs total trip duration
    private var progress: Double {
        let totalDuration = trip.etaAt.timeIntervalSince(trip.startAt)
        guard totalDuration > 0 else { return 1.0 }

        let elapsed = Date().timeIntervalSince(trip.startAt)
        let progress = elapsed / totalDuration

        // Clamp between 0 and 1
        return min(max(progress, 0), 1)
    }

    private var ringColor: Color {
        if trip.contactsNotified {
            return .red
        } else if trip.isOverdue {
            return .orange
        } else {
            return .green
        }
    }

    var body: some View {
        ZStack {
            // Background ring
            Circle()
                .stroke(lineWidth: 4)
                .opacity(0.3)

            // Progress ring
            Circle()
                .trim(from: 0, to: progress)
                .stroke(style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .foregroundColor(ringColor)
                .rotationEffect(.degrees(-90))

            // Activity icon
            Text(trip.activityIcon)
                .font(.title2)
        }
    }
}

private struct NoTripCircularView: View {
    var body: some View {
        ZStack {
            Circle()
                .stroke(lineWidth: 4)
                .opacity(0.3)

            Image(systemName: "location.circle")
                .font(.title2)
                .opacity(0.6)
        }
    }
}

// MARK: - Inline Lock Screen Widget

struct LockScreenInlineWidget: Widget {
    let kind: String = "LockScreenInlineWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: TripWidgetProvider()) { entry in
            LockScreenInlineView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Trip Countdown")
        .description("Compact countdown text.")
        .supportedFamilies([.accessoryInline])
    }
}

struct LockScreenInlineView: View {
    let entry: TripWidgetEntry

    var body: some View {
        // Check if widgets are enabled (premium feature)
        if !LiveActivityConstants.widgetsEnabled {
            Label("Upgrade to Plus", systemImage: "star.fill")
        } else if let trip = entry.tripData {
            HStack(spacing: 4) {
                Text(trip.activityIcon)
                Text(trip.formattedTimeRemaining)
            }
        } else {
            Label("No active trip", systemImage: "location.slash")
        }
    }
}

// MARK: - Rectangular Lock Screen Widget

struct LockScreenRectangularWidget: Widget {
    let kind: String = "LockScreenRectangularWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: TripWidgetProvider()) { entry in
            LockScreenRectangularView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Trip Details")
        .description("Activity, countdown, and status.")
        .supportedFamilies([.accessoryRectangular])
    }
}

struct LockScreenRectangularView: View {
    let entry: TripWidgetEntry

    var body: some View {
        // Check if widgets are enabled (premium feature)
        if !LiveActivityConstants.widgetsEnabled {
            UpgradePremiumRectangularView()
        } else if let trip = entry.tripData {
            ActiveRectangularView(trip: trip)
        } else {
            NoTripRectangularView()
        }
    }
}

private struct UpgradePremiumRectangularView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Image(systemName: "star.fill")
                    .font(.caption2)
                Text("Homebound+")
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .opacity(0.8)

            Text("Upgrade to Plus")
                .font(.headline)
                .fontWeight(.semibold)

            Text("Unlock widgets")
                .font(.caption2)
                .opacity(0.6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct ActiveRectangularView: View {
    let trip: WidgetTripData

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            // Activity name with icon
            HStack(spacing: 4) {
                Text(trip.activityIcon)
                    .font(.caption2)
                Text(trip.activityName)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .opacity(0.8)

            // Countdown - prominent
            Text(trip.formattedTimeRemaining)
                .font(.headline)
                .fontWeight(.bold)

            // Status text
            Text(trip.statusText)
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundColor(trip.isOverdue ? .red : .secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct NoTripRectangularView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Image(systemName: "location.circle")
                    .font(.caption2)
                Text("Homebound")
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .opacity(0.8)

            Text("No Active Trip")
                .font(.headline)
                .fontWeight(.semibold)

            Text("Tap to start")
                .font(.caption2)
                .opacity(0.6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Previews

#Preview(as: .accessoryCircular) {
    LockScreenCircularWidget()
} timeline: {
    TripWidgetEntry(date: .now, tripData: .placeholder)
    TripWidgetEntry(date: .now, tripData: nil)
}

#Preview(as: .accessoryInline) {
    LockScreenInlineWidget()
} timeline: {
    TripWidgetEntry(date: .now, tripData: .placeholder)
    TripWidgetEntry(date: .now, tripData: nil)
}

#Preview(as: .accessoryRectangular) {
    LockScreenRectangularWidget()
} timeline: {
    TripWidgetEntry(date: .now, tripData: .placeholder)
    TripWidgetEntry(date: .now, tripData: nil)
}
