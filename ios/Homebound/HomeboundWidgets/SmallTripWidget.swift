//
//  SmallTripWidget.swift
//  HomeboundWidgets
//
//  Small home screen widget showing active trip status
//

import WidgetKit
import SwiftUI

// MARK: - Small Trip Widget

struct SmallTripWidget: Widget {
    let kind: String = "SmallTripWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: TripWidgetProvider()) { entry in
            SmallTripWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Trip Status")
        .description("See your active trip at a glance.")
        .supportedFamilies([.systemSmall])
    }
}

// MARK: - Small Widget View

struct SmallTripWidgetView: View {
    let entry: TripWidgetEntry

    var body: some View {
        // Check if widgets are enabled
        if !LiveActivityConstants.widgetsEnabled {
            UpgradePremiumSmallView()
        } else if let trip = entry.tripData {
            ActiveTripSmallView(trip: trip)
        } else {
            NoTripSmallView()
        }
    }
}

// MARK: - Upgrade Premium View

private struct UpgradePremiumSmallView: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "star.fill")
                .font(.title)
                .foregroundStyle(Color(hex: "#356B3D") ?? .green)

            Text("Homebound+")
                .font(.headline)
                .fontWeight(.bold)

            Text("Upgrade to unlock widgets")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Active Trip View

private struct ActiveTripSmallView: View {
    let trip: WidgetTripData

    private var primaryColor: Color {
        Color(hex: trip.primaryColor) ?? .blue
    }

    private var statusColor: Color {
        if trip.contactsNotified {
            return .red
        } else if trip.isOverdue {
            return .orange
        } else {
            return .green
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Activity icon with status
            HStack {
                Text(trip.activityIcon)
                    .font(.title2)

                Spacer()

                // Status dot with pulse effect for overdue
                Circle()
                    .fill(statusColor)
                    .frame(width: 10, height: 10)
            }

            Spacer()

            // Title
            Text(trip.title)
                .font(.headline)
                .fontWeight(.semibold)
                .lineLimit(2)
                .foregroundColor(.primary)

            // Countdown
            if trip.isOverdue {
                Text(trip.formattedTimeRemaining)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundColor(.red)
            } else {
                Text(trip.formattedTimeRemaining)
                    .font(.title3)
                    .fontWeight(.bold)
                    .foregroundColor(primaryColor)
            }

            // Status text
            Text(trip.statusText)
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

// MARK: - No Trip View

private struct NoTripSmallView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "location.circle")
                .font(.largeTitle)
                .foregroundColor(.secondary)

            Text("No Active Trip")
                .font(.headline)
                .foregroundColor(.secondary)

            Text("Tap to start")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Preview

#Preview(as: .systemSmall) {
    SmallTripWidget()
} timeline: {
    TripWidgetEntry(date: .now, tripData: .placeholder)
    TripWidgetEntry(date: .now, tripData: nil)
}
