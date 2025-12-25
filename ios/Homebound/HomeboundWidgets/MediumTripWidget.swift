//
//  MediumTripWidget.swift
//  HomeboundWidgets
//
//  Medium home screen widget with trip details and action buttons
//

import WidgetKit
import SwiftUI

// MARK: - Medium Trip Widget

struct MediumTripWidget: Widget {
    let kind: String = "MediumTripWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: TripWidgetProvider()) { entry in
            MediumTripWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Trip Control")
        .description("View trip details and quickly check in or complete your trip.")
        .supportedFamilies([.systemMedium])
    }
}

// MARK: - Medium Widget View

struct MediumTripWidgetView: View {
    let entry: TripWidgetEntry

    var body: some View {
        if let trip = entry.tripData {
            ActiveTripMediumView(trip: trip)
        } else {
            NoTripMediumView()
        }
    }
}

// MARK: - Active Trip View

private struct ActiveTripMediumView: View {
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
        HStack(spacing: 16) {
            // Left side - Trip info
            VStack(alignment: .leading, spacing: 6) {
                // Activity with icon
                HStack(spacing: 6) {
                    Text(trip.activityIcon)
                        .font(.subheadline)

                    Text(trip.activityName)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.secondary)

                    // Status dot
                    Circle()
                        .fill(statusColor)
                        .frame(width: 8, height: 8)
                }

                // Title
                Text(trip.title)
                    .font(.headline)
                    .fontWeight(.semibold)
                    .lineLimit(1)
                    .foregroundColor(.primary)

                // Countdown
                HStack(spacing: 4) {
                    if trip.isOverdue {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundColor(.red)
                    }

                    Text(trip.formattedTimeRemaining)
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(trip.isOverdue ? .red : primaryColor)
                }

                // Location if available
                if let location = trip.locationText, !location.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "mappin")
                            .font(.caption2)
                        Text(location)
                            .font(.caption)
                            .lineLimit(1)
                    }
                    .foregroundColor(.secondary)
                }
            }

            Spacer()

            // Right side - Status display
            VStack(spacing: 4) {
                Text(trip.statusText)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundColor(statusColor)

                if trip.checkinCount > 0 {
                    HStack(spacing: 2) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption2)
                        Text("\(trip.checkinCount)")
                            .font(.caption2)
                    }
                    .foregroundColor(.green)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - No Trip View

private struct NoTripMediumView: View {
    var body: some View {
        HStack(spacing: 16) {
            Image(systemName: "location.circle")
                .font(.system(size: 40))
                .foregroundColor(.secondary)

            VStack(alignment: .leading, spacing: 4) {
                Text("No Active Trip")
                    .font(.headline)
                    .foregroundColor(.primary)

                Text("Tap to start a new trip")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Preview

#Preview(as: .systemMedium) {
    MediumTripWidget()
} timeline: {
    TripWidgetEntry(date: .now, tripData: .placeholder)
    TripWidgetEntry(date: .now, tripData: nil)
}
