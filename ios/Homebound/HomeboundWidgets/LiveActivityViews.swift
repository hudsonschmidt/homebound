//
//  LiveActivityViews.swift
//  HomeboundWidgets
//
//  Live Activity UI for Lock Screen and Dynamic Island
//

import ActivityKit
import AppIntents
import SwiftUI
import WidgetKit

// MARK: - Live Activity Configuration

struct TripLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: TripLiveActivityAttributes.self) { context in
            // Lock Screen / Banner UI
            LockScreenView(
                attributes: context.attributes,
                state: context.state
            )
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded UI
                DynamicIslandExpandedRegion(.leading) {
                    ExpandedLeadingView(attributes: context.attributes, state: context.state)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    ExpandedTrailingView(attributes: context.attributes, state: context.state)
                }
                DynamicIslandExpandedRegion(.center) {
                    ExpandedCenterView(attributes: context.attributes, state: context.state)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    ExpandedBottomView(attributes: context.attributes, state: context.state)
                }
            } compactLeading: {
                CompactLeadingView(attributes: context.attributes, state: context.state)
            } compactTrailing: {
                CompactTrailingView(attributes: context.attributes, state: context.state)
            } minimal: {
                MinimalView(attributes: context.attributes, state: context.state)
            }
        }
    }
}

// MARK: - Lock Screen View

struct LockScreenView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState
    let displayMode: LiveActivityDisplayMode  // Cached at init to avoid repeated UserDefaults reads

    init(attributes: TripLiveActivityAttributes, state: TripLiveActivityAttributes.ContentState) {
        self.attributes = attributes
        self.state = state
        self.displayMode = LiveActivityConstants.displayMode  // Read once at init
    }

    private var primaryColor: Color {
        Color(hex: attributes.primaryColor) ?? .green
    }

    private var isOverdue: Bool {
        state.isOverdue || state.status == "overdue" || state.status == "overdue_notified"
    }

    private var statusColor: Color {
        if state.contactsNotified {
            return .red
        } else if isOverdue {
            return .orange
        }
        return .green
    }

    // Brand green from app theme (#356B3D)
    private var brandGreen: Color {
        Color(hex: "#356B3D") ?? .green
    }

    // Helper to format check-in time
    private func checkinTimeText(_ checkinTime: Date) -> String {
        let elapsed = Date().timeIntervalSince(checkinTime)
        let minutes = Int(elapsed / 60)

        if minutes < 1 {
            return "Just checked in"
        } else if minutes < 60 {
            return "Checked in \(minutes)m ago"
        } else {
            return "Checked in \(minutes / 60)h ago"
        }
    }

    private var backgroundColor: Color {
        if isOverdue {
            return state.contactsNotified ? Color.red.opacity(0.15) : Color.orange.opacity(0.15)
        }
        return primaryColor.opacity(0.1)
    }

    // Whether trip is in urgent state (overdue or grace warning)
    private var isUrgent: Bool {
        isOverdue
    }

    // Status badge dot size (larger when urgent)
    private var statusBadgeSize: CGFloat {
        isUrgent ? 10 : 6
    }

    // MARK: - Status Badge View (matches Active Trip Card)

    private var statusBadgeView: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: statusBadgeSize, height: statusBadgeSize)
                .shadow(color: statusColor.opacity(0.6), radius: 4)  // Glow effect

            Text(state.statusText)  // "ACTIVE TRIP" / "CHECK IN NOW" / "OVERDUE"
                .font(.caption)
                .fontWeight(.bold)
                .foregroundStyle(isUrgent ? statusColor : .white.opacity(0.9))

            Spacer()

            if isUrgent {
                Image(systemName: "bell.fill")
                    .font(.caption)
                    .foregroundStyle(statusColor)
            }
        }
    }

    // MARK: - Check-in Info View (matches Active Trip Card format)

    @ViewBuilder
    private var checkinInfoView: some View {
        if state.checkinCount > 0 {
            HStack {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle")
                        .font(.caption2)
                    Text("\(state.checkinCount) check-in\(state.checkinCount == 1 ? "" : "s")")
                        .font(.caption2)
                }
                .foregroundStyle(.green)

                if let checkinTime = state.lastCheckinTime {
                    Spacer()
                    Text("Last: \(timeText(checkinTime))")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
        }
    }

    // Helper for "Last: 12:45 PM" format - shows actual time
    private func timeText(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: date)
    }

    var body: some View {
        VStack(spacing: displayMode == .full ? 6 : 12) {
            switch displayMode {
            case .minimal:
                minimalLayout
            case .standard:
                standardLayout
            case .full:
                fullLayout
            }
        }
        .padding(displayMode == .full ? 10 : 16)
        .background(backgroundColor)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.white.opacity(0.1), lineWidth: 1)
        )
        .activityBackgroundTint(Color.black.opacity(0.85))
    }

    // MARK: - Minimal Layout

    private var minimalLayout: some View {
        HStack(spacing: 16) {
            // Status dot + countdown
            HStack(spacing: 8) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)

                CountdownView(eta: state.eta, isOverdue: isOverdue, statusColor: statusColor)
            }

            Spacer()

            completeButton
        }
    }

    // MARK: - Standard Layout

    private var standardLayout: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Row 1: Status badge + Title + Icon (combined for compactness)
            HStack(spacing: 6) {
                Circle()
                    .fill(statusColor)
                    .frame(width: statusBadgeSize, height: statusBadgeSize)
                    .shadow(color: statusColor.opacity(0.6), radius: 3)

                Text(attributes.title)
                    .font(.headline)
                    .fontWeight(.bold)
                    .foregroundStyle(.white)
                    .lineLimit(1)

                Spacer()

                if isUrgent {
                    Image(systemName: "bell.fill")
                        .font(.caption)
                        .foregroundStyle(statusColor)
                }

                Text(attributes.activityIcon)
                    .font(.title3)
            }

            // Row 2: Activity name + check-in info (combined)
            HStack(spacing: 8) {
                Text(attributes.activityName)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.7))

                if state.checkinCount > 0 {
                    Text("•")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.5))

                    HStack(spacing: 3) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 10))
                        Text("\(state.checkinCount)")
                            .font(.caption2)
                        if let checkinTime = state.lastCheckinTime {
                            Text("@ \(timeText(checkinTime))")
                                .font(.caption2)
                        }
                    }
                    .foregroundStyle(.green)
                }
            }

            // Row 3: Countdown
            CountdownView(eta: state.eta, isOverdue: isOverdue, statusColor: statusColor)

            // Row 4: Action buttons
            actionButtons
        }
    }

    // MARK: - Full Layout

    private var fullLayout: some View {
        VStack(alignment: .leading, spacing: 5) {
            // Row 1: Status badge + Title + Icon (combined)
            HStack(spacing: 6) {
                Circle()
                    .fill(statusColor)
                    .frame(width: statusBadgeSize, height: statusBadgeSize)
                    .shadow(color: statusColor.opacity(0.6), radius: 3)

                Text(attributes.title)
                    .font(.subheadline)
                    .fontWeight(.bold)
                    .foregroundStyle(.white)
                    .lineLimit(1)

                Spacer()

                if isUrgent {
                    Image(systemName: "bell.fill")
                        .font(.caption2)
                        .foregroundStyle(statusColor)
                }

                Text(attributes.activityIcon)
                    .font(.callout)
            }

            // Row 2: Activity name + Location + check-in info
            HStack(spacing: 6) {
                Text(attributes.activityName)
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.7))

                if let location = attributes.endLocation {
                    Text("•")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.5))

                    Image(systemName: "location.fill")
                        .font(.system(size: 8))
                        .foregroundStyle(.white.opacity(0.6))

                    Text(location)
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.7))
                        .lineLimit(1)
                }

                if state.checkinCount > 0 {
                    Text("•")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.5))

                    HStack(spacing: 2) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 8))
                        Text("\(state.checkinCount)")
                            .font(.caption2)
                    }
                    .foregroundStyle(.green)
                }
            }

            // Row 3: Countdown
            Text(timerInterval: Date()...(isOverdue ? Date() : state.eta), countsDown: true)
                .font(.system(.title2, design: .rounded, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(isOverdue ? statusColor : .white)

            // Row 4: Action buttons (compact)
            fullModeButtons
        }
    }

    private var fullModeButtons: some View {
        Group {
            if #available(iOS 17.0, *) {
                fullModeButtonsWithIntents
            } else {
                fullModeButtonsLegacy
            }
        }
    }

    @available(iOS 17.0, *)
    private var fullModeButtonsWithIntents: some View {
        HStack(spacing: 8) {
            if !isOverdue {
                if let checkinToken = attributes.checkinToken {
                    Button(intent: CheckInIntent(checkinToken: checkinToken, tripId: attributes.tripId)) {
                        HStack(spacing: 3) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 10))
                            Text("Check In")
                                .font(.caption)
                                .fontWeight(.semibold)
                        }
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Color.green)
                        .cornerRadius(10)
                    }
                    .buttonStyle(LiveActivityButtonStyle())
                }
            }

            if let checkoutToken = attributes.checkoutToken {
                Button(intent: CheckOutIntent(checkoutToken: checkoutToken, tripId: attributes.tripId)) {
                    HStack(spacing: 3) {
                        Image(systemName: "house.fill")
                            .font(.system(size: 10))
                        Text("I'm Safe")
                            .font(.caption)
                            .fontWeight(.semibold)
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .background(isOverdue ? statusColor : brandGreen)
                    .cornerRadius(10)
                }
                .buttonStyle(LiveActivityButtonStyle())
            }
        }
    }

    private var fullModeButtonsLegacy: some View {
        HStack(spacing: 8) {
            if !isOverdue {
                if let checkinToken = attributes.checkinToken,
                   let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(checkinToken)/checkin") {
                    Link(destination: url) {
                        HStack(spacing: 3) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 10))
                            Text("Check In")
                                .font(.caption)
                                .fontWeight(.semibold)
                        }
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Color.green)
                        .cornerRadius(10)
                    }
                }
            }

            if let checkoutToken = attributes.checkoutToken,
               let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(checkoutToken)/checkout") {
                Link(destination: url) {
                    HStack(spacing: 3) {
                        Image(systemName: "house.fill")
                            .font(.system(size: 10))
                        Text("I'm Safe")
                            .font(.caption)
                            .fontWeight(.semibold)
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .background(isOverdue ? statusColor : brandGreen)
                    .cornerRadius(10)
                }
            }
        }
    }

    // MARK: - Components

    private var actionButtons: some View {
        Group {
            if #available(iOS 17.0, *) {
                actionButtonsWithIntents
            } else {
                actionButtonsLegacy
            }
        }
    }

    @available(iOS 17.0, *)
    private var actionButtonsWithIntents: some View {
        HStack(spacing: 12) {
            if !isOverdue {
                if let checkinToken = attributes.checkinToken {
                    Button(intent: CheckInIntent(checkinToken: checkinToken, tripId: attributes.tripId)) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                            Text("Check In")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Color.green)
                        .cornerRadius(12)
                    }
                    .buttonStyle(LiveActivityButtonStyle())
                }
            }

            completeButton
        }
    }

    private var actionButtonsLegacy: some View {
        HStack(spacing: 12) {
            if !isOverdue {
                if let checkinToken = attributes.checkinToken,
                   let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(checkinToken)/checkin") {
                    Link(destination: url) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                            Text("Check In")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                        }
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Color.green)
                        .cornerRadius(12)
                    }
                }
            }

            completeButtonLegacy
        }
    }

    private var completeButton: some View {
        Group {
            if #available(iOS 17.0, *) {
                completeButtonWithIntent
            } else {
                completeButtonLegacy
            }
        }
    }

    @available(iOS 17.0, *)
    private var completeButtonWithIntent: some View {
        Group {
            if let checkoutToken = attributes.checkoutToken {
                Button(intent: CheckOutIntent(checkoutToken: checkoutToken, tripId: attributes.tripId)) {
                    HStack(spacing: 4) {
                        Image(systemName: "house.fill")
                            .font(.caption)
                        Text("I'm Safe")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(isOverdue ? statusColor : brandGreen)
                    .cornerRadius(12)
                }
                .buttonStyle(LiveActivityButtonStyle())
            }
        }
    }

    private var completeButtonLegacy: some View {
        Group {
            if let checkoutToken = attributes.checkoutToken,
               let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(checkoutToken)/checkout") {
                Link(destination: url) {
                    HStack(spacing: 4) {
                        Image(systemName: "house.fill")
                            .font(.caption)
                        Text("I'm Safe")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(isOverdue ? statusColor : brandGreen)
                    .cornerRadius(12)
                }
            }
        }
    }
}

// MARK: - Countdown View

struct CountdownView: View {
    let eta: Date
    let isOverdue: Bool
    var statusColor: Color = .orange

    var body: some View {
        if isOverdue {
            Text("OVERDUE")
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(statusColor)
        } else {
            Text(timerInterval: Date()...eta, countsDown: true)
                .font(.system(.title3, design: .rounded, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(.white)
        }
    }
}

// MARK: - Dynamic Island Views

// Compact Leading - Activity Icon
struct CompactLeadingView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    private var isOverdue: Bool {
        state.isOverdue || state.status == "overdue" || state.status == "overdue_notified"
    }

    private var statusColor: Color {
        if state.contactsNotified { return .red }
        if isOverdue { return .orange }
        return .green
    }

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(statusColor)
                .frame(width: 6, height: 6)
            Text(attributes.activityIcon)
                .font(.caption)
        }
    }
}

// Compact Trailing - Time Remaining
struct CompactTrailingView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    private var isOverdue: Bool {
        state.isOverdue || state.status == "overdue" || state.status == "overdue_notified"
    }

    private var statusColor: Color {
        if state.contactsNotified { return .red }
        if isOverdue { return .orange }
        return .white
    }

    var body: some View {
        if isOverdue {
            Text("!")
                .font(.caption.weight(.bold))
                .foregroundStyle(statusColor)
        } else {
            Text(timerInterval: Date()...state.eta, countsDown: true)
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(.white)
                .frame(minWidth: 40)
        }
    }
}

// Minimal View - Icon only
struct MinimalView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    private var isOverdue: Bool {
        state.isOverdue || state.status == "overdue" || state.status == "overdue_notified"
    }

    private var statusColor: Color {
        if state.contactsNotified { return .red }
        if isOverdue { return .orange }
        return .green
    }

    var body: some View {
        ZStack {
            Circle()
                .fill(statusColor)
                .frame(width: 6, height: 6)
                .offset(x: 8, y: -8)

            Text(attributes.activityIcon)
                .font(.caption)
        }
    }
}

// Expanded Leading - Icon and Activity Name
struct ExpandedLeadingView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    private var isOverdue: Bool {
        state.isOverdue || state.status == "overdue" || state.status == "overdue_notified"
    }

    private var statusColor: Color {
        if state.contactsNotified { return .red }
        if isOverdue { return .orange }
        return .green
    }

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 6, height: 6)
            Text(attributes.activityIcon)
                .font(.title3)
            Text(attributes.activityName)
                .font(.caption.weight(.medium))
                .foregroundStyle(.white.opacity(0.7))
        }
    }
}

// Expanded Trailing - ETA Time
struct ExpandedTrailingView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text("ETA")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.6))
            Text(state.eta.formatted(date: .omitted, time: .shortened))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
        }
    }
}

// Expanded Center - Title
struct ExpandedCenterView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    var body: some View {
        Text(attributes.title)
            .font(.subheadline.weight(.bold))
            .foregroundStyle(.white)
            .lineLimit(1)
    }
}

// Expanded Bottom - Actions and Progress
struct ExpandedBottomView: View {
    let attributes: TripLiveActivityAttributes
    let state: TripLiveActivityAttributes.ContentState

    private var isOverdue: Bool {
        state.isOverdue || state.status == "overdue" || state.status == "overdue_notified"
    }

    private var statusColor: Color {
        if state.contactsNotified { return .red }
        if isOverdue { return .orange }
        return .green
    }

    private var brandGreen: Color {
        Color(hex: "#356B3D") ?? .green
    }

    private var progress: Double {
        let total = state.eta.timeIntervalSince(attributes.startTime)
        let elapsed = Date().timeIntervalSince(attributes.startTime)
        guard total > 0 else { return 1.0 }
        return min(max(elapsed / total, 0), 1.0)
    }

    var body: some View {
        VStack(spacing: 10) {
            // Progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.2))
                        .frame(height: 4)

                    Capsule()
                        .fill(isOverdue ? statusColor : brandGreen)
                        .frame(width: geo.size.width * progress, height: 4)
                }
            }
            .frame(height: 4)

            // Action buttons
            actionButtons
        }
    }

    private var actionButtons: some View {
        Group {
            if #available(iOS 17.0, *) {
                actionButtonsWithIntents
            } else {
                actionButtonsLegacy
            }
        }
    }

    @available(iOS 17.0, *)
    private var actionButtonsWithIntents: some View {
        HStack(spacing: 12) {
            if !isOverdue {
                if let checkinToken = attributes.checkinToken {
                    Button(intent: CheckInIntent(checkinToken: checkinToken, tripId: attributes.tripId)) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption2)
                            Text("Check In")
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(Color.green)
                        .cornerRadius(12)
                    }
                    .buttonStyle(LiveActivityButtonStyle())
                }
            }

            if let checkoutToken = attributes.checkoutToken {
                Button(intent: CheckOutIntent(checkoutToken: checkoutToken, tripId: attributes.tripId)) {
                    HStack(spacing: 4) {
                        Image(systemName: "house.fill")
                            .font(.caption2)
                        Text("I'm Safe")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(isOverdue ? statusColor : brandGreen)
                    .cornerRadius(12)
                }
                .buttonStyle(LiveActivityButtonStyle())
            }
        }
    }

    private var actionButtonsLegacy: some View {
        HStack(spacing: 12) {
            if !isOverdue {
                if let checkinToken = attributes.checkinToken,
                   let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(checkinToken)/checkin") {
                    Link(destination: url) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption2)
                            Text("Check In")
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(Color.green)
                        .cornerRadius(12)
                    }
                }
            }

            if let checkoutToken = attributes.checkoutToken,
               let url = URL(string: "\(LiveActivityConstants.baseURL)/t/\(checkoutToken)/checkout") {
                Link(destination: url) {
                    HStack(spacing: 4) {
                        Image(systemName: "house.fill")
                            .font(.caption2)
                        Text("I'm Safe")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(isOverdue ? statusColor : brandGreen)
                    .cornerRadius(12)
                }
            }
        }
    }
}

// MARK: - Live Activity Button Style

private struct LiveActivityButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.92 : 1.0)
            .opacity(configuration.isPressed ? 0.7 : 1.0)
            .animation(.easeInOut(duration: 0.1), value: configuration.isPressed)
    }
}

// MARK: - Color Extension

extension Color {
    init?(hex: String) {
        var hexSanitized = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        hexSanitized = hexSanitized.replacingOccurrences(of: "#", with: "")

        var rgb: UInt64 = 0
        guard Scanner(string: hexSanitized).scanHexInt64(&rgb) else { return nil }

        let r, g, b: Double
        switch hexSanitized.count {
        case 6:
            r = Double((rgb & 0xFF0000) >> 16) / 255.0
            g = Double((rgb & 0x00FF00) >> 8) / 255.0
            b = Double(rgb & 0x0000FF) / 255.0
        case 8:
            r = Double((rgb & 0xFF000000) >> 24) / 255.0
            g = Double((rgb & 0x00FF0000) >> 16) / 255.0
            b = Double((rgb & 0x0000FF00) >> 8) / 255.0
        default:
            return nil
        }

        self.init(red: r, green: g, blue: b)
    }
}

// MARK: - Preview

#if DEBUG
struct TripLiveActivity_Previews: PreviewProvider {
    static var previews: some View {
        LockScreenView(
            attributes: TripLiveActivityAttributes(
                tripId: 1,
                title: "Morning Summit Hike",
                activityIcon: "figure.hiking",
                activityName: "Hiking",
                primaryColor: "#34C759",
                secondaryColor: "#A8E6CF",
                startLocation: "Trailhead Parking",
                endLocation: "Summit Peak",
                checkinToken: "abc123",
                checkoutToken: "xyz789",
                graceMinutes: 30,
                startTime: Date().addingTimeInterval(-3600)
            ),
            state: TripLiveActivityAttributes.ContentState(
                status: "active",
                eta: Date().addingTimeInterval(7200),
                lastCheckinTime: nil,
                isOverdue: false,
                checkinCount: 0
            )
        )
        .previewDisplayName("Lock Screen - Standard")
    }
}
#endif
