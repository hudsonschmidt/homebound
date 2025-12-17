//
//  CheckOutIntent.swift
//  HomeboundWidgets
//
//  App Intent for Live Activity checkout/complete action
//

import ActivityKit
import AppIntents
import SwiftUI

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
        // Perform the API call
        _ = try await LiveActivityAPI.shared.checkOut(token: checkoutToken)

        // End the Live Activity on successful checkout
        await endLiveActivity()

        return .result()
    }

    private func endLiveActivity() async {
        // Signal the main app to end the Live Activity
        // (Widget extensions cannot access activities created by the main app)
        let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier)
        defaults?.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckoutKey)
        defaults?.synchronize()

        // Post Darwin notification to wake main app immediately
        let name = LiveActivityConstants.darwinNotificationName as CFString
        CFNotificationCenterPostNotification(
            CFNotificationCenterGetDarwinNotifyCenter(),
            CFNotificationName(name),
            nil, nil, true
        )
    }
}
