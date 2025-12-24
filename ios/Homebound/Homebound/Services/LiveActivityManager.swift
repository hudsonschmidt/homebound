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

    /// Track delayed unregistration tasks by trip ID (for cleanup on app termination)
    private var delayedUnregistrationTasks: [Int: Task<Void, Never>] = [:]

    /// Non-blocking token registration queue to avoid blocking the push token stream
    private var pendingTokenQueue: [(token: String, tripId: Int)] = []
    private var tokenRegistrationTask: Task<Void, Never>?
    private var lastRegisteredToken: [Int: String] = [:]  // Track last registered token per trip for deduplication

    /// Debounce: track last update timestamp per trip to prevent rapid updates
    private var lastUpdateTime: [Int: Date] = [:]
    private let debounceInterval: TimeInterval = 2.0  // 2 seconds (increased from 500ms)

    /// Mutex: prevent concurrent start/update operations that cause flicker
    private var isOperationInProgress = false

    /// Retained reference for Darwin notification observer (for memory safety)
    private var darwinObserverRef: Unmanaged<LiveActivityManager>?

    // MARK: - Initialization

    private init() {
        checkSupport()
        setupDarwinNotificationObserver()
    }

    // Store notification name as nonisolated constant for use in deinit
    private nonisolated let darwinNotificationNameForCleanup = LiveActivityConstants.darwinNotificationName

    deinit {
        // Cancel all tracked tasks
        for task in tokenObservationTasks.values {
            task.cancel()
        }
        for task in delayedUnregistrationTasks.values {
            task.cancel()
        }
        tokenRegistrationTask?.cancel()

        // Remove Darwin notification observer and release retained reference
        CFNotificationCenterRemoveObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            darwinObserverRef?.toOpaque(),
            CFNotificationName(darwinNotificationNameForCleanup as CFString),
            nil
        )
        darwinObserverRef?.release()
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
        // Use passRetained to ensure memory safety - the observer reference is retained
        // and will be released in deinit
        darwinObserverRef = Unmanaged.passRetained(self)
        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            darwinObserverRef?.toOpaque(),
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
        guard let defaults = sharedDefaults else {
            debugLog("[LiveActivity] handlePendingActions: No shared defaults available")
            return
        }

        // Longer delay to ensure UserDefaults is synced from widget extension
        try? await Task.sleep(nanoseconds: 100_000_000) // 100ms (was 50ms)

        // Check both pending flags
        let pendingCheckout = defaults.double(forKey: LiveActivityConstants.pendingCheckoutKey)
        let pendingCheckin = defaults.double(forKey: LiveActivityConstants.pendingCheckinKey)

        // Clear flags immediately to prevent duplicate handling
        if pendingCheckout > 0 {
            defaults.removeObject(forKey: LiveActivityConstants.pendingCheckoutKey)
        }
        if pendingCheckin > 0 {
            defaults.removeObject(forKey: LiveActivityConstants.pendingCheckinKey)
        }

        // Log what we're handling
        if pendingCheckout > 0 || pendingCheckin > 0 {
            debugLog("[LiveActivity] handlePendingActions: checkout=\(pendingCheckout > 0), checkin=\(pendingCheckin > 0)")
        }

        // Always refresh from server to get authoritative state
        if pendingCheckout > 0 || pendingCheckin > 0 {
            await refreshTripDataFromServer()
        }

        // Handle checkout (ends activity) after refresh
        if pendingCheckout > 0 {
            debugLog("[LiveActivity] Handling pending checkout action - ending activities")
            await endAllActivities()
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
        // Mutex: prevent concurrent operations that cause flicker
        guard !isOperationInProgress else {
            debugLog("[LiveActivity] Operation already in progress, skipping start for trip #\(trip.id)")
            return false
        }
        isOperationInProgress = true
        defer { isOperationInProgress = false }

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

        // Check if activity for this trip already exists
        let activities = ActivityKit.Activity<TripLiveActivityAttributes>.activities
        if activities.contains(where: { $0.attributes.tripId == trip.id }) {
            // Activity exists, update it instead of restarting
            debugLog("[LiveActivity] Activity already exists for trip #\(trip.id), updating instead")
            await updateActivity(with: trip, checkinCount: checkinCount)
            return true
        }

        // End activities for OTHER trips (not this one)
        for activity in activities {
            if activity.attributes.tripId != trip.id {
                let tripId = activity.attributes.tripId
                tokenObservationTasks[tripId]?.cancel()
                tokenObservationTasks.removeValue(forKey: tripId)
                await Session.shared.unregisterLiveActivityToken(tripId: tripId)
                let finalState = TripLiveActivityAttributes.ContentState(
                    status: "completed", eta: Date(), graceEnd: Date(), lastCheckinTime: nil, isOverdue: false, checkinCount: 0
                )
                let content = ActivityKit.ActivityContent(state: finalState, staleDate: nil)
                await activity.end(content, dismissalPolicy: .immediate)
                debugLog("[LiveActivity] Ended stale activity for trip #\(tripId)")
            }
        }

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

        // Calculate grace end time
        let graceEnd = trip.eta_at.addingTimeInterval(Double(trip.grace_minutes) * 60)

        let initialState = TripLiveActivityAttributes.ContentState(
            status: trip.status,
            eta: trip.eta_at,
            graceEnd: graceEnd,
            lastCheckinTime: parseLastCheckin(trip.last_checkin),
            isOverdue: isOverdue(trip),
            checkinCount: checkinCount
        )

        // Set stale date to ETA + grace period + 5 minute buffer
        // Activity will show as stale if no updates received by this time
        let staleDate = trip.eta_at.addingTimeInterval(Double(trip.grace_minutes + 5) * 60)

        do {
            let content = ActivityKit.ActivityContent(state: initialState, staleDate: staleDate)
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

    /// Observe push token updates for an activity and queue for non-blocking registration
    @available(iOS 16.1, *)
    private func observePushTokenUpdates(for activity: ActivityKit.Activity<TripLiveActivityAttributes>, tripId: Int) {
        // Cancel any existing observation for this trip
        tokenObservationTasks[tripId]?.cancel()
        debugLog("[LiveActivity] Starting token observation for trip #\(tripId)")

        // Start new observation task - this now queues tokens instead of blocking
        // Note: Using strong self since this is a singleton (static let shared) and the task
        // is tracked in tokenObservationTasks for proper cancellation in deinit.
        tokenObservationTasks[tripId] = Task {
            for await tokenData in activity.pushTokenUpdates {
                guard !Task.isCancelled else {
                    debugLog("[LiveActivity] Token observation cancelled for trip #\(tripId)")
                    break
                }

                // Verify activity still exists for this tripId before registering
                let activities = ActivityKit.Activity<TripLiveActivityAttributes>.activities
                guard activities.contains(where: { $0.attributes.tripId == tripId }) else {
                    debugLog("[LiveActivity] Activity no longer exists for trip #\(tripId), skipping token registration")
                    continue
                }

                let tokenString = tokenData.map { String(format: "%02x", $0) }.joined()
                debugLog("[LiveActivity] Push token received for trip #\(tripId): \(tokenString.prefix(20))...")

                // Queue token for non-blocking registration (doesn't block the stream)
                self.queueTokenForRegistration(token: tokenString, tripId: tripId)
            }
            debugLog("[LiveActivity] Token observation ended for trip #\(tripId)")
        }
    }

    /// Queue a token for async registration without blocking the push token stream
    private func queueTokenForRegistration(token: String, tripId: Int) {
        // Deduplicate: skip if this exact token was already registered for this trip
        if lastRegisteredToken[tripId] == token {
            debugLog("[LiveActivity] Skipping duplicate token for trip #\(tripId)")
            return
        }

        debugLog("[LiveActivity] Queuing token for trip #\(tripId): \(token.prefix(20))...")

        // Add to queue (replacing any pending token for same trip to avoid stale registrations)
        pendingTokenQueue.removeAll { $0.tripId == tripId }
        pendingTokenQueue.append((token: token, tripId: tripId))

        debugLog("[LiveActivity] Token queue size: \(pendingTokenQueue.count)")

        // Start registration task if not already running
        startTokenRegistrationTaskIfNeeded()
    }

    /// Start the background token registration task if not already running
    private func startTokenRegistrationTaskIfNeeded() {
        guard tokenRegistrationTask == nil else {
            debugLog("[LiveActivity] Token registration task already running")
            return
        }

        debugLog("[LiveActivity] Starting token registration task")
        tokenRegistrationTask = Task {
            while !pendingTokenQueue.isEmpty {
                let (token, tripId) = pendingTokenQueue.removeFirst()

                debugLog("[LiveActivity] Registering token for trip #\(tripId)...")

                // Retry up to 3 times with exponential backoff
                var success = false
                for attempt in 1...3 {
                    success = await self.sendPushTokenToBackend(token: token, tripId: tripId)
                    if success {
                        debugLog("[LiveActivity] ✅ Token registered for trip #\(tripId) on attempt \(attempt)")
                        lastRegisteredToken[tripId] = token
                        break
                    } else if attempt < 3 {
                        debugLog("[LiveActivity] ⚠️ Token registration for trip #\(tripId) failed, retrying in \(attempt)s...")
                        try? await Task.sleep(nanoseconds: UInt64(attempt) * 1_000_000_000)
                    } else {
                        debugLog("[LiveActivity] ❌ Token registration for trip #\(tripId) failed after 3 attempts")
                    }
                }
            }
            debugLog("[LiveActivity] Token registration task completed")
            tokenRegistrationTask = nil
        }
    }

    /// Send live activity push token to backend
    /// Returns true if successful
    private func sendPushTokenToBackend(token: String, tripId: Int) async -> Bool {
        return await Session.shared.registerLiveActivityToken(token: token, tripId: tripId)
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

        // Calculate grace end time
        let graceEnd = trip.eta_at.addingTimeInterval(Double(trip.grace_minutes) * 60)

        let updatedState = TripLiveActivityAttributes.ContentState(
            status: trip.status,
            eta: trip.eta_at,
            graceEnd: graceEnd,
            lastCheckinTime: parseLastCheckin(trip.last_checkin),
            isOverdue: isOverdue(trip),
            checkinCount: finalCheckinCount
        )

        // Update stale date to ETA + grace period + 5 minute buffer
        let staleDate = trip.eta_at.addingTimeInterval(Double(activity.attributes.graceMinutes + 5) * 60)
        let content = ActivityKit.ActivityContent(state: updatedState, staleDate: staleDate)
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

            // End the activity UI first
            if let trip = trip {
                let graceEnd = trip.eta_at.addingTimeInterval(Double(trip.grace_minutes) * 60)
                let finalState = TripLiveActivityAttributes.ContentState(
                    status: "completed",
                    eta: trip.eta_at,
                    graceEnd: graceEnd,
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
                    graceEnd: Date(),
                    lastCheckinTime: nil,
                    isOverdue: false,
                    checkinCount: 0
                )
                let content = ActivityKit.ActivityContent(state: finalState, staleDate: nil)
                await activity.end(content, dismissalPolicy: ActivityKit.ActivityUIDismissalPolicy.immediate)
            }

            // Delay token unregistration to allow backend to send final update
            // Cancel any existing delayed task for this trip
            delayedUnregistrationTasks[tripId]?.cancel()
            let unregisterTask = Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)  // 3 seconds
                guard !Task.isCancelled else { return }
                await Session.shared.unregisterLiveActivityToken(tripId: tripId)
                debugLog("[LiveActivity] Token unregistered for trip #\(tripId) after delay")
            }
            delayedUnregistrationTasks[tripId] = unregisterTask
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

            // End the activity UI first
            let finalState = TripLiveActivityAttributes.ContentState(
                status: "completed",
                eta: Date(),
                graceEnd: Date(),
                lastCheckinTime: nil,
                isOverdue: false,
                checkinCount: 0
            )
            let content = ActivityKit.ActivityContent(state: finalState, staleDate: nil)
            await activity.end(content, dismissalPolicy: ActivityKit.ActivityUIDismissalPolicy.immediate)

            // Delay token unregistration to allow backend to send final update
            // Cancel any existing delayed task for this trip
            delayedUnregistrationTasks[tripId]?.cancel()
            let unregisterTask = Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)  // 3 seconds
                guard !Task.isCancelled else { return }
                await Session.shared.unregisterLiveActivityToken(tripId: tripId)
                debugLog("[LiveActivity] Token unregistered for trip #\(tripId) after delay")
            }
            delayedUnregistrationTasks[tripId] = unregisterTask
        }
        // Clear the stored activity ID
        sharedDefaults?.removeObject(forKey: LiveActivityConstants.activityIdKey)
        debugLog("[LiveActivity] Ended all activities")
    }

    /// Track last status per trip for debounce logic
    private var lastStatus: [Int: String] = [:]

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

        // Check if status changed - always process status changes even if debounced
        let statusChanged = lastStatus[trip.id] != trip.status
        lastStatus[trip.id] = trip.status

        // Debounce: skip if we just updated this trip recently AND status hasn't changed
        // Status changes (e.g., active -> overdue) should always be processed immediately
        if !statusChanged,
           let lastUpdate = lastUpdateTime[trip.id],
           Date().timeIntervalSince(lastUpdate) < debounceInterval {
            debugLog("[LiveActivity] Skipping restore for trip #\(trip.id) - debounced (status unchanged)")
            return
        }

        if existingActivity != nil {
            // Update existing activity
            await updateActivity(with: trip, checkinCount: checkinCount)
        } else {
            // Start new activity
            await startActivity(for: trip, checkinCount: checkinCount)
        }

        // Record update time
        lastUpdateTime[trip.id] = Date()
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
