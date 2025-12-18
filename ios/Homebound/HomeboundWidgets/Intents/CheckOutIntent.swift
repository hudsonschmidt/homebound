//
//  CheckOutIntent.swift
//  HomeboundWidgets
//
//  App Intent for Live Activity checkout/complete action
//

import ActivityKit
import AppIntents
import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct CheckOutIntent: LiveActivityIntent {
    static var title: LocalizedStringResource = "I'm Safe"
    static var description = IntentDescription("Complete your trip and mark yourself as safe")

    @Parameter(title: "Check-out Token")
    var checkoutToken: String

    @Parameter(title: "Trip ID")
    var tripId: Int

    init() {
        self.checkoutToken = ""
        self.tripId = 0
    }

    init(checkoutToken: String, tripId: Int) {
        self.checkoutToken = checkoutToken
        self.tripId = tripId
    }

    func perform() async throws -> some IntentResult {
        let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier)

        do {
            // Perform API call FIRST - only signal success if it actually succeeds
            _ = try await LiveActivityAPI.shared.checkOut(token: checkoutToken)

            // API succeeded - clear widget data since trip is complete
            defaults?.removeObject(forKey: LiveActivityConstants.widgetTripDataKey)
            defaults?.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckoutKey)
            defaults?.synchronize()

            // Small delay to ensure UserDefaults syncs across processes
            try? await Task.sleep(nanoseconds: 100_000_000) // 100ms

            // Post Darwin notification to wake main app
            postDarwinNotification()

            // Refresh widgets to show "No Active Trip"
            WidgetCenter.shared.reloadAllTimelines()

        } catch {
            // API failed - don't signal success
            throw error
        }

        return .result()
    }

    private func postDarwinNotification() {
        // Signal the main app to refresh and end the Live Activity
        // (Widget extensions cannot access activities created by the main app)
        let name = LiveActivityConstants.darwinNotificationName as CFString
        CFNotificationCenterPostNotification(
            CFNotificationCenterGetDarwinNotifyCenter(),
            CFNotificationName(name),
            nil, nil, true
        )
    }
}
