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
        // Validate token before making API call
        guard !checkoutToken.isEmpty else {
            // Invalid token - silently fail without crashing
            return .result()
        }

        guard let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier) else {
            // App group not available - log and fail gracefully
            debugLog("[CheckOutIntent] ❌ Failed to access app group UserDefaults")
            return .result()
        }

        // Set pending flag BEFORE API call so main app knows to refresh even if widget is killed
        defaults.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckoutKey)

        // Post Darwin notification early as backup signaling
        postDarwinNotification()

        // Retry logic with single retry attempt
        var lastError: Error?
        for attempt in 1...2 {
            do {
                // Perform API call
                _ = try await LiveActivityAPI.shared.checkOut(token: checkoutToken)

                // API succeeded - clear widget data since trip is complete
                defaults.removeObject(forKey: LiveActivityConstants.widgetTripDataKey)

                // Refresh widgets to show "No Active Trip"
                WidgetCenter.shared.reloadAllTimelines()

                return .result()  // Success - exit early

            } catch {
                lastError = error
                if attempt < 2 {
                    // Wait 1 second before retry
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
        }

        // All attempts failed - clear pending flag so main app doesn't act on false success
        defaults.removeObject(forKey: LiveActivityConstants.pendingCheckoutKey)
        if let error = lastError {
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
