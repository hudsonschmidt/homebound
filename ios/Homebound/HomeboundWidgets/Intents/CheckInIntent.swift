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
        // Validate token before making API call
        guard !checkinToken.isEmpty else {
            // Invalid token - silently fail without crashing
            return .result()
        }

        guard let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier) else {
            // App group not available - log and fail gracefully
            debugLog("[CheckInIntent] ❌ Failed to access app group UserDefaults")
            return .result()
        }

        // Set pending flag BEFORE API call so main app knows to refresh even if widget is killed
        defaults.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckinKey)

        // Post Darwin notification early as backup signaling
        postDarwinNotification()

        // Retry logic with single retry attempt
        var lastError: Error?
        for attempt in 1...2 {
            do {
                // Perform API call
                _ = try await LiveActivityAPI.shared.checkIn(token: checkinToken)

                // API succeeded - set confirmation timestamp for visual feedback
                defaults.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.checkinConfirmationKey)

                // Refresh widgets to show updated state
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

        // All attempts failed - clear pending flag so main app doesn't show false success
        defaults.removeObject(forKey: LiveActivityConstants.pendingCheckinKey)
        if let error = lastError {
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
