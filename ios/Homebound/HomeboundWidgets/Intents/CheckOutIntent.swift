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

        // Set pending flag BEFORE API call so main app knows to refresh even if widget is killed
        defaults?.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckoutKey)

        // Post Darwin notification early as backup signaling
        postDarwinNotification()

        do {
            // Perform API call
            _ = try await LiveActivityAPI.shared.checkOut(token: checkoutToken)

            // API succeeded - clear widget data since trip is complete
            defaults?.removeObject(forKey: LiveActivityConstants.widgetTripDataKey)

            // Refresh widgets to show "No Active Trip"
            WidgetCenter.shared.reloadAllTimelines()

        } catch {
            // API failed - clear pending flag so main app doesn't act on false success
            defaults?.removeObject(forKey: LiveActivityConstants.pendingCheckoutKey)
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
