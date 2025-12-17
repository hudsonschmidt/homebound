//
//  CheckInIntent.swift
//  HomeboundWidgets
//
//  App Intent for Live Activity check-in action
//

import ActivityKit
import AppIntents
import SwiftUI

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
        // Perform the API call
        _ = try await LiveActivityAPI.shared.checkIn(token: checkinToken)

        // Update the Live Activity to show success
        await updateLiveActivityWithSuccess()

        return .result()
    }

    private func updateLiveActivityWithSuccess() async {
        // Signal the main app to update the Live Activity
        // (Widget extensions cannot access activities created by the main app)
        let defaults = UserDefaults(suiteName: LiveActivityConstants.appGroupIdentifier)
        defaults?.set(Date().timeIntervalSince1970, forKey: LiveActivityConstants.pendingCheckinKey)
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
