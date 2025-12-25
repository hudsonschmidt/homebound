//
//  MediumTripWidget.swift
//  HomeboundWidgets
//
//  Medium home screen widget with trip details and action buttons
//

import WidgetKit
import SwiftUI
import AppIntents

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
            ActiveTripMediumView(trip: trip, showCheckinConfirmation: entry.showCheckinConfirmation)
        } else {
            NoTripMediumView()
        }
    }
}

// MARK: - Active Trip View

private struct ActiveTripMediumView: View {
    let trip: WidgetTripData
    let showCheckinConfirmation: Bool

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

            // Right side - Action buttons
            if #available(iOS 17.0, *) {
                HStack(spacing: 6) {
                    // Checkmark confirmation (appears after check-in)
                    if showCheckinConfirmation {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.title2)
                            .foregroundColor(.green)
                            .transition(.opacity)
                    }

                    VStack(spacing: 8) {
                        // Check In button
                        if let token = trip.checkinToken {
                            Button(intent: CheckInIntent(checkinToken: token, tripId: trip.id)) {
                                Text("Check In")
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.8)
                            }
                            .buttonStyle(WidgetButtonStyle(color: primaryColor))
                        }

                        // Complete Trip button
                        if let token = trip.checkoutToken {
                            Button(intent: CheckOutIntent(checkoutToken: token, tripId: trip.id)) {
                                Text("Complete")
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .lineLimit(1)
                                    .minimumScaleFactor(0.8)
                            }
                            .buttonStyle(WidgetButtonStyle(color: .green))
                        }
                    }
                    .frame(width: 100)
                }
            } else {
                // Fallback for older iOS - just show status
                VStack(spacing: 4) {
                    Text(trip.statusText)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundColor(statusColor)

                    Text("Open app to\ncheck in")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
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

// MARK: - Widget Button Style

private struct WidgetButtonStyle: ButtonStyle {
    let color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .padding(.horizontal, 8)
            .background(color.opacity(configuration.isPressed ? 0.5 : 0.2))
            .foregroundColor(.primary)
            .cornerRadius(8)
            // Note: Per CLAUDE.md, animations only allowed on Live Activity buttons
            // Immediate press feedback without animation transition
            .scaleEffect(configuration.isPressed ? 0.95 : 1.0)
            .opacity(configuration.isPressed ? 0.9 : 1.0)
    }
}

// MARK: - Preview

#Preview(as: .systemMedium) {
    MediumTripWidget()
} timeline: {
    TripWidgetEntry(date: .now, tripData: .placeholder, showCheckinConfirmation: true)
    TripWidgetEntry(date: .now, tripData: .placeholder, showCheckinConfirmation: false)
    TripWidgetEntry(date: .now, tripData: nil)
}
