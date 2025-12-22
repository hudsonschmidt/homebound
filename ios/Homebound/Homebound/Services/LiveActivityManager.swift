//
//  LiveActivityManager.swift
//  Homebound
//
//  Manages Live Activity lifecycle for active trips
//

import ActivityKit
import Combine
import Foundation

// TripLiveActivityAttributes is defined in TripActivityAttributes.swift
// (shared between main app and widget extension targets)

// MARK: - Live Activity Manager

@MainActor
final class LiveActivityManager: ObservableObject {

    // MARK: - Singleton

    static let shared = LiveActivityManager()

    // MARK: - Properties

    @Published private(set) var isSupported: Bool = false

    private let appGroupIdentifier = "group.com.homeboundapp.Homebound"
    private let enabledKey = "liveActivityEnabled"

    /// Track active token observation tasks by trip ID
    private var tokenObservationTasks: [Int: Task<Void, Never>] = [:]

    // MARK: - Initialization

    private init() {
        checkSupport()
        setupDarwinNotificationObserver()
    }

    private func checkSupport() {
        if #available(iOS 16.1, *) {
            isSupported = ActivityKit.ActivityAuthorizationInfo().areActivitiesEnabled
        } else {
            isSupported = false
        }
    }

    // MARK: - Darwin Notification Observer (Cross-Process IPC)

    private func setupDarwinNotificationObserver() {
        let name = LiveActivityConstants.darwinNotificationName as CFString
        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            Unmanaged.passUnretained(self).toOpaque(),
            { _, observer, _, _, _ in
                guard let observer = observer else { return }
                let manager = Unmanaged<LiveActivityManager>.fromOpaque(observer).takeUnretainedValue()
                Task { @MainActor in
                    await manager.handlePendingActions()
                }
            },
            name,
            nil,
            .deliverImmediately
        )
        debugLog("[LiveActivity] Darwin notification observer registered")
    }

    /// Handle pending actions signaled from widget extension
    func handlePendingActions() async {
        guard let defaults = sharedDefaults else { return }

        // Small delay to ensure UserDefaults is synced from widget extension
        try? await Task.sleep(nanoseconds: 50_000_000) // 50ms

        // Handle pending checkout (takes priority - ends the activity)
        if defaults.double(forKey: LiveActivityConstants.pendingCheckoutKey) > 0 {
            defaults.removeObject(forKey: LiveActivityConstants.pendingCheckoutKey)
            debugLog("[LiveActivity] Handling pending checkout action")
            // Refresh from server to get final state, then end
            await refreshTripDataFromServer()
            await endAllActivities()
            return
        }

        // Handle pending checkin
        if defaults.double(forKey: LiveActivityConstants.pendingCheckinKey) > 0 {
            defaults.removeObject(forKey: LiveActivityConstants.pendingCheckinKey)
            debugLog("[LiveActivity] Handling pending checkin action")
            // Refresh from server - this updates both widget data and Live Activity with authoritative state
            await refreshTripDataFromServer()
        }
    }

    /// Refresh trip data from server and update Live Activity
    /// This ensures we have authoritative state from the backend
    private func refreshTripDataFromServer() async {
        debugLog("[LiveActivity] Refreshing trip data from server")
        // Session.loadActivePlan() will fetch fresh data and call updateActivity()
        await Session.shared.loadActivePlan()
    }

    // MARK: - Settings

    private var sharedDefaults: UserDefaults? {
        UserDefaults(suiteName: appGroupIdentifier)
    }

    var isEnabled: Bool {
        guard let defaults = sharedDefaults else { return true }
        if defaults.object(forKey: enabledKey) == nil {
            return true // Default to enabled
        }
        return defaults.bool(forKey: enabledKey)
    }

    // MARK: - Public Methods

    /// Start a Live Activity for the given trip
    /// - Parameters:
    ///   - trip: The active trip to display
    ///   - checkinCount: Number of check-ins already performed (default 0 for new trips)
    /// - Returns: True if activity was started successfully
    @discardableResult
    func startActivity(for trip: Trip, checkinCount: Int = 0) async -> Bool {
        guard #available(iOS 16.1, *) else {
            debugLog("[LiveActivity] iOS 16.1+ required")
            return false
        }

        guard isSupported else {
            debugLog("[LiveActivity] Activities not supported or disabled by user")
            return false
        }

        guard isEnabled else {
            debugLog("[LiveActivity] Live Activities disabled in app settings")
            return false
        }

        // End any existing activity first
        await endAllActivities()

        return await startActivityInternal(for: trip, checkinCount: checkinCount)
    }

    @available(iOS 16.1, *)
    private func startActivityInternal(for trip: Trip, checkinCount: Int) async -> Bool {
        let attributes = TripLiveActivityAttributes(
            tripId: trip.id,
            title: trip.title,
            activityIcon: trip.activity.icon,
            activityName: trip.activity.name,
            primaryColor: trip.activity.colors.primary,
            secondaryColor: trip.activity.colors.secondary,
            startLocation: trip.start_location_text,
            endLocation: trip.location_text,
            checkinToken: trip.checkin_token,
            checkoutToken: trip.checkout_token,
            graceMinutes: trip.grace_minutes,
            startTime: trip.start_at
        )

        let initialState = TripLiveActivityAttributes.ContentState(
            status: trip.status,
            eta: trip.eta_at,
            lastCheckinTime: parseLastCheckin(trip.last_checkin),
            isOverdue: isOverdue(trip),
            checkinCount: checkinCount
        )

        do {
            let content = ActivityKit.ActivityContent(state: initialState, staleDate: nil)
            let activity = try ActivityKit.Activity<TripLiveActivityAttributes>.request(
                attributes: attributes,
                content: content,
                pushType: .token
            )
            // Store the activity ID in shared UserDefaults for widget access
            sharedDefaults?.set(activity.id, forKey: LiveActivityConstants.activityIdKey)
            debugLog("[LiveActivity] Started activity for trip #\(trip.id), id: \(activity.id)")

            // Start observing push token updates to send to backend
            observePushTokenUpdates(for: activity, tripId: trip.id)

            return true
        } catch {
            debugLog("[LiveActivity] Failed to start: \(error.localizedDescription)")
            return false
        }
    }

    /// Observe push token updates for an activity and send to backend
    @available(iOS 16.1, *)
    private func observePushTokenUpdates(for activity: ActivityKit.Activity<TripLiveActivityAttributes>, tripId: Int) {
        // Cancel any existing observation for this trip
        tokenObservationTasks[tripId]?.cancel()

        // Start new observation task
        tokenObservationTasks[tripId] = Task { [weak self] in
            for await tokenData in activity.pushTokenUpdates {
                guard !Task.isCancelled else { break }
                let tokenString = tokenData.map { String(format: "%02x", $0) }.joined()
                debugLog("[LiveActivity] Push token update for trip #\(tripId): \(tokenString.prefix(20))...")
                await self?.sendPushTokenToBackend(token: tokenString, tripId: tripId)
            }
        }
    }

    /// Send live activity push token to backend
    private func sendPushTokenToBackend(token: String, tripId: Int) async {
        await Session.shared.registerLiveActivityToken(token: token, tripId: tripId)
    }

    /// Update the Live Activity with new trip state
    /// - Parameters:
    ///   - trip: The updated trip data
    ///   - checkinCount: Number of check-ins performed (default 0)
    func updateActivity(with trip: Trip, checkinCount: Int = 0) async {
        guard #available(iOS 16.1, *) else { return }

        let activities = ActivityKit.Activity<TripLiveActivityAttributes>.activities
        guard let activity = activities.first(where: { $0.attributes.tripId == trip.id }) else {
            // No current activity, try to start one
            await startActivity(for: trip, checkinCount: checkinCount)
            return
        }

        // Preserve existing check-in count if not explicitly provided
        let existingCount = activity.content.state.checkinCount
        let finalCheckinCount = checkinCount > 0 ? checkinCount : existingCount

        let updatedState = TripLiveActivityAttributes.ContentState(
            status: trip.status,
            eta: trip.eta_at,
            lastCheckinTime: parseLastCheckin(trip.last_checkin),
            isOverdue: isOverdue(trip),
            checkinCount: finalCheckinCount
        )

        let content = ActivityKit.ActivityContent(state: updatedState, staleDate: nil)
        await activity.update(content)
        debugLog("[LiveActivity] Updated state for trip #\(trip.id)")
    }

    /// End the current Live Activity
    /// - Parameter trip: Optional trip for final state display
    func endActivity(for trip: Trip? = nil) async {
        guard #available(iOS 16.1, *) else { return }

        let activities = ActivityKit.Activity<TripLiveActivityAttributes>.activities

        for activity in activities {
            let tripId = activity.attributes.tripId

            // Cancel token observation for this trip
            tokenObservationTasks[tripId]?.cancel()
            tokenObservationTasks.removeValue(forKey: tripId)

            // Unregister token from backend
            await Session.shared.unregisterLiveActivityToken(tripId: tripId)

            if let trip = trip {
                let finalState = TripLiveActivityAttributes.ContentState(
                    status: "completed",
                    eta: trip.eta_at,
                    lastCheckinTime: parseLastCheckin(trip.last_checkin),
                    isOverdue: false,
                    checkinCount: activity.content.state.checkinCount
                )
                let content = ActivityKit.ActivityContent(state: finalState, staleDate: nil)
                await activity.end(content, dismissalPolicy: ActivityKit.ActivityUIDismissalPolicy.immediate)
            } else {
                let finalState = TripLiveActivityAttributes.ContentState(
                    status: "completed",
                    eta: Date(),
                    lastCheckinTime: nil,
                    isOverdue: false,
                    checkinCount: 0
                )
                let content = ActivityKit.ActivityContent(state: finalState, staleDate: nil)
                await activity.end(content, dismissalPolicy: ActivityKit.ActivityUIDismissalPolicy.immediate)
            }
        }

        debugLog("[LiveActivity] Ended activity")
    }

    /// End all active Live Activities (cleanup)
    func endAllActivities() async {
        guard #available(iOS 16.1, *) else { return }

        let activities = ActivityKit.Activity<TripLiveActivityAttributes>.activities
        for activity in activities {
            let tripId = activity.attributes.tripId

            // Cancel token observation for this trip
            tokenObservationTasks[tripId]?.cancel()
            tokenObservationTasks.removeValue(forKey: tripId)

            // Unregister token from backend
            await Session.shared.unregisterLiveActivityToken(tripId: tripId)

            let finalState = TripLiveActivityAttributes.ContentState(
                status: "completed",
                eta: Date(),
                lastCheckinTime: nil,
                isOverdue: false,
                checkinCount: 0
            )
            let content = ActivityKit.ActivityContent(state: finalState, staleDate: nil)
            await activity.end(content, dismissalPolicy: ActivityKit.ActivityUIDismissalPolicy.immediate)
        }
        // Clear the stored activity ID
        sharedDefaults?.removeObject(forKey: LiveActivityConstants.activityIdKey)
        debugLog("[LiveActivity] Ended all activities")
    }

    /// Check and restore Live Activity for an existing active trip
    /// Call this on app launch if there's an active trip
    /// - Parameters:
    ///   - trip: The active trip to display
    ///   - checkinCount: Number of check-ins performed (default 0)
    func restoreActivityIfNeeded(for trip: Trip?, checkinCount: Int = 0) async {
        guard #available(iOS 16.1, *) else { return }
        guard let trip = trip else {
            // No active trip, end any stale activities
            await endAllActivities()
            return
        }

        // Check if there's already an activity for this trip
        let activities = ActivityKit.Activity<TripLiveActivityAttributes>.activities
        let existingActivity = activities.first { $0.attributes.tripId == trip.id }

        if existingActivity != nil {
            // Update existing activity
            await updateActivity(with: trip, checkinCount: checkinCount)
        } else {
            // Start new activity
            await startActivity(for: trip, checkinCount: checkinCount)
        }
    }

    // MARK: - Private Helpers

    private func isOverdue(_ trip: Trip) -> Bool {
        let graceEndTime = trip.eta_at.addingTimeInterval(Double(trip.grace_minutes) * 60)
        return Date() > graceEndTime
    }

    private func parseLastCheckin(_ checkin: String?) -> Date? {
        guard let checkin = checkin else { return nil }
        return parseISO8601Date(checkin)
    }
}
