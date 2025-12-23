//
//  CheckInIntent.swift
//  HomeboundWidgets
//
//  App Intent for Live Activity check-in action
//

import ActivityKit
import AppIntents
import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct CheckInIntent: LiveActivityIntent {
    static var title: LocalizedStringResource = "Check In"
    static var description = IntentDescription("Check in to your current trip")

    @Parameter(title: "Check-in Token")
    var checkinToken: String

    @Parameter(title: "Trip ID")
    var tripId: Int

    init() {
        self.checkinToken = ""
        self.tripId = 0
    }

    init(checkinToken: String, tripId: Int) {
        self.checkinToken = checkinToken
        self.tripId = tripId
    }

    func perform() async throws -> some IntentResult {
        let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier)

        do {
            // Perform API call FIRST - only show success if it actually succeeds
            _ = try await LiveActivityAPI.shared.checkIn(token: checkinToken)

            // API succeeded - now set confirmation timestamp for visual feedback
            defaults?.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.checkinConfirmationKey)
            defaults?.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckinKey)
            // Note: synchronize() is deprecated - iOS handles UserDefaults synchronization automatically

            // Small delay to ensure UserDefaults syncs across processes
            try? await Task.sleep(nanoseconds: 100_000_000) // 100ms

            // Post Darwin notification to wake main app
            postDarwinNotification()

            // Refresh widgets to show updated state
            WidgetCenter.shared.reloadAllTimelines()

        } catch {
            // API failed - don't show success indicators
            // The error will propagate and the button won't show false success
            throw error
        }

        return .result()
    }

    private func postDarwinNotification() {
        // Signal the main app to refresh trip data and update Live Activity
        // (Widget extensions cannot access activities created by the main app)
        let name = LiveActivityConstants.darwinNotificationName as CFString
        CFNotificationCenterPostNotification(
            CFNotificationCenterGetDarwinNotifyCenter(),
            CFNotificationName(name),
            nil, nil, true
        )
    }
}
