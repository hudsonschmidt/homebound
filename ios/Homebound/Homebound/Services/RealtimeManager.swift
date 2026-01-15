import Foundation
import Combine
import Supabase

/// Manages Supabase Realtime subscriptions for instant UI updates
/// Subscribes to database changes and triggers Session refreshes when relevant data changes
@MainActor
final class RealtimeManager: ObservableObject {
    static let shared = RealtimeManager()

    private var friendshipsChannel: RealtimeChannelV2?
    private var tripsChannel: RealtimeChannelV2?
    private var participantsChannel: RealtimeChannelV2?
    private var eventsChannel: RealtimeChannelV2?
    private var votesChannel: RealtimeChannelV2?
    private var usersChannel: RealtimeChannelV2?
    private var liveLocationsChannel: RealtimeChannelV2?

    private var currentUserId: Int?
    private var isRunning = false

    /// Whether there's an active connection issue
    @Published private(set) var hasConnectionIssue = false

    /// Retry configuration
    private static let maxRetryAttempts = 5
    private static let baseRetryDelay: Double = 2.0
    private static let maxRetryDelay: Double = 60.0

    /// Track retry state for each subscription type
    private var retryTasks: [String: Task<Void, Never>] = [:]

    private init() {}

    // MARK: - Public API

    /// Start all realtime subscriptions for the given user
    /// Called after successful authentication
    func start(userId: Int) async {
        guard !isRunning else {
            debugLog("[Realtime] Already running, skipping start")
            return
        }

        debugLog("[Realtime] Starting subscriptions for user \(userId)")
        self.currentUserId = userId
        self.isRunning = true

        await subscribeToFriendships()
        await subscribeToTrips()
        await subscribeToParticipants()
        await subscribeToEvents()
        await subscribeToVotes()
        await subscribeToUserChanges()
        await subscribeToLiveLocations()

        debugLog("[Realtime] All subscriptions started")
    }

    /// Stop all realtime subscriptions
    /// Called on logout or app termination
    func stop() async {
        guard isRunning else { return }

        debugLog("[Realtime] Stopping all subscriptions")

        // Cancel any pending retry tasks
        for (name, task) in retryTasks {
            task.cancel()
            debugLog("[Realtime] Cancelled retry task for \(name)")
        }
        retryTasks.removeAll()

        await friendshipsChannel?.unsubscribe()
        await tripsChannel?.unsubscribe()
        await participantsChannel?.unsubscribe()
        await eventsChannel?.unsubscribe()
        await votesChannel?.unsubscribe()
        await usersChannel?.unsubscribe()
        await liveLocationsChannel?.unsubscribe()

        friendshipsChannel = nil
        tripsChannel = nil
        participantsChannel = nil
        eventsChannel = nil
        votesChannel = nil
        usersChannel = nil
        liveLocationsChannel = nil
        currentUserId = nil
        isRunning = false
        hasConnectionIssue = false

        debugLog("[Realtime] All subscriptions stopped")
    }

    /// Attempt to reconnect all subscriptions
    /// Call this when network becomes available or after a connection failure
    func reconnect() async {
        guard let userId = currentUserId, isRunning else {
            debugLog("[Realtime] Cannot reconnect: not running or no user ID")
            return
        }

        debugLog("[Realtime] Attempting to reconnect all subscriptions")
        hasConnectionIssue = false

        await subscribeToFriendships()
        await subscribeToTrips()
        await subscribeToParticipants()
        await subscribeToEvents()
        await subscribeToVotes()
        await subscribeToUserChanges()
        await subscribeToLiveLocations()

        debugLog("[Realtime] Reconnection attempt complete")
    }

    // MARK: - Retry Logic

    /// Subscribe to a channel with exponential backoff retry
    private func subscribeWithRetry(
        channel: RealtimeChannelV2,
        name: String,
        attempt: Int = 0
    ) async -> Bool {
        do {
            try await channel.subscribe()
            hasConnectionIssue = false
            debugLog("[Realtime] Subscribed to \(name)")
            return true
        } catch {
            debugLog("[Realtime] Failed to subscribe to \(name): \(error)")

            if attempt < Self.maxRetryAttempts {
                let delay = min(
                    Self.baseRetryDelay * pow(2.0, Double(attempt)),
                    Self.maxRetryDelay
                )
                debugLog("[Realtime] Retrying \(name) subscription in \(delay)s (attempt \(attempt + 1)/\(Self.maxRetryAttempts))")

                // Schedule retry
                let retryTask = Task { [weak self] in
                    try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                    guard !Task.isCancelled else { return }
                    let _ = await self?.subscribeWithRetry(channel: channel, name: name, attempt: attempt + 1)
                }
                retryTasks[name] = retryTask
            } else {
                debugLog("[Realtime] Max retry attempts reached for \(name)")
                hasConnectionIssue = true
            }

            return false
        }
    }

    // MARK: - Subscriptions

    /// Subscribe to friendships table for new friend connections
    private func subscribeToFriendships() async {
        guard let userId = currentUserId else { return }

        let channel = supabase.channel("friendships-\(userId)")
        friendshipsChannel = channel

        // Listen for new friendships (INSERT)
        let inserts = channel.postgresChange(
            InsertAction.self,
            schema: "public",
            table: "friendships"
        )

        // Listen for deleted friendships (DELETE)
        let deletes = channel.postgresChange(
            DeleteAction.self,
            schema: "public",
            table: "friendships"
        )

        let success = await subscribeWithRetry(channel: channel, name: "friendships")
        guard success else { return }

        // Handle new friendships
        Task { [weak self] in
            for await insert in inserts {
                guard self != nil else { break }  // Exit if manager deallocated
                // Check if this friendship involves the current user
                // record is [String: AnyJSON], extract values
                let record = insert.record
                if let userId1 = record["user_id_1"]?.intValue,
                   let userId2 = record["user_id_2"]?.intValue,
                   (userId1 == userId || userId2 == userId) {
                    debugLog("[Realtime] New friendship detected - refreshing friends list")
                    _ = await Session.shared.loadFriends(forceRefresh: true)
                }
            }
        }

        // Handle removed friendships
        Task { [weak self] in
            for await delete in deletes {
                guard self != nil else { break }  // Exit if manager deallocated
                // On delete, oldRecord contains the deleted data
                let oldRecord = delete.oldRecord
                if let userId1 = oldRecord["user_id_1"]?.intValue,
                   let userId2 = oldRecord["user_id_2"]?.intValue,
                   (userId1 == userId || userId2 == userId) {
                    debugLog("[Realtime] Friendship removed - refreshing friends list")
                    _ = await Session.shared.loadFriends(forceRefresh: true)
                }
            }
        }
    }

    /// Subscribe to trips table for trip status changes
    private func subscribeToTrips() async {
        guard let userId = currentUserId else { return }

        let channel = supabase.channel("trips-\(userId)")
        tripsChannel = channel

        // Listen for trip updates (status changes, check-ins, etc.)
        let updates = channel.postgresChange(
            UpdateAction.self,
            schema: "public",
            table: "trips"
        )

        // Listen for new trips (friend started a trip where I'm a contact)
        let inserts = channel.postgresChange(
            InsertAction.self,
            schema: "public",
            table: "trips"
        )

        let success = await subscribeWithRetry(channel: channel, name: "trips")
        guard success else { return }

        // Handle trip updates
        Task { [weak self] in
            for await update in updates {
                guard self != nil else { break }  // Exit if manager deallocated
                // Refresh trip data - Session will filter to relevant trips
                let record = update.record
                let tripId = record["trip_id"]?.intValue ?? record["id"]?.intValue
                debugLog("[Realtime] Trip update detected: tripId=\(String(describing: tripId))")

                // Bug 3 fix: Check if it's safe to load active plan (respects local update protection window)
                if Session.shared.shouldLoadActivePlan() {
                    await Session.shared.loadActivePlan()
                }
                _ = await Session.shared.loadAllTrips()
                _ = await Session.shared.loadFriendActiveTrips()

                // If the active trip is a group trip, refresh vote status
                if let activeTripId = Session.shared.activeTrip?.id,
                   Session.shared.activeTrip?.is_group_trip == true {
                    await Session.shared.refreshVoteStatus(tripId: activeTripId)
                }
            }
        }

        // Handle new trips
        Task { [weak self] in
            for await _ in inserts {
                guard self != nil else { break }  // Exit if manager deallocated
                debugLog("[Realtime] New trip detected")
                _ = await Session.shared.loadFriendActiveTrips()
            }
        }
    }

    /// Subscribe to trip_participants table for invitations
    private func subscribeToParticipants() async {
        guard let userId = currentUserId else { return }

        let channel = supabase.channel("participants-\(userId)")
        participantsChannel = channel

        // Listen for new invitations
        let inserts = channel.postgresChange(
            InsertAction.self,
            schema: "public",
            table: "trip_participants"
        )

        // Listen for invitation status changes (accepted, declined)
        let updates = channel.postgresChange(
            UpdateAction.self,
            schema: "public",
            table: "trip_participants"
        )

        let success = await subscribeWithRetry(channel: channel, name: "participants")
        guard success else { return }

        // Handle new invitations
        Task { [weak self] in
            for await insert in inserts {
                guard self != nil else { break }  // Exit if manager deallocated
                // Check if this invitation is for the current user
                let record = insert.record
                if let invitedUserId = record["user_id"]?.intValue,
                   invitedUserId == userId {
                    debugLog("[Realtime] New trip invitation received")
                    await Session.shared.loadTripInvitations()
                }
            }
        }

        // Handle invitation status updates
        Task { [weak self] in
            for await _ in updates {
                guard self != nil else { break }  // Exit if manager deallocated
                // Refresh participant data - someone accepted/declined
                debugLog("[Realtime] Participant status changed")
                // Bug 3 fix: Check protection window before refreshing active plan
                if Session.shared.shouldLoadActivePlan() {
                    await Session.shared.loadActivePlan()
                }
                _ = await Session.shared.loadAllTrips()
            }
        }
    }

    /// Subscribe to events table for check-ins and other trip events
    private func subscribeToEvents() async {
        let channel = supabase.channel("events-checkins")
        eventsChannel = channel

        // Listen for new events (check-ins, extensions, etc.)
        let inserts = channel.postgresChange(
            InsertAction.self,
            schema: "public",
            table: "events"
        )

        let success = await subscribeWithRetry(channel: channel, name: "events")
        guard success else { return }

        // Handle new events
        Task { [weak self] in
            for await insert in inserts {
                guard self != nil else { break }  // Exit if manager deallocated
                // Someone checked in or performed an action
                let record = insert.record
                let eventType = record["what"]?.stringValue ?? "unknown"
                let tripId = record["trip_id"]?.intValue
                debugLog("[Realtime] New event detected: type=\(eventType), tripId=\(String(describing: tripId))")

                // Bug 3 fix: Check protection window before refreshing active plan
                // This prevents the extend event from triggering a stale data fetch
                if Session.shared.shouldLoadActivePlan() {
                    await Session.shared.loadActivePlan()
                }
                _ = await Session.shared.loadAllTrips()
                _ = await Session.shared.loadFriendActiveTrips()

                // Notify views to refresh timeline (for check-in counter updates)
                Session.shared.notifyTimelineUpdated()
            }
        }
    }

    /// Subscribe to checkout_votes table for vote updates
    private func subscribeToVotes() async {
        let channel = supabase.channel("checkout-votes")
        votesChannel = channel

        // Listen for new votes
        let inserts = channel.postgresChange(
            InsertAction.self,
            schema: "public",
            table: "checkout_votes"
        )

        // Listen for deleted votes (e.g., when trip completes, votes are cleared)
        let deletes = channel.postgresChange(
            DeleteAction.self,
            schema: "public",
            table: "checkout_votes"
        )

        let success = await subscribeWithRetry(channel: channel, name: "votes")
        guard success else { return }

        // Handle new votes
        Task { [weak self] in
            for await insert in inserts {
                guard self != nil else { break }  // Exit if manager deallocated
                let record = insert.record
                let tripId = record["trip_id"]?.intValue
                debugLog("[Realtime] Vote cast detected: tripId=\(String(describing: tripId))")

                // Refresh vote status for the active trip
                if let activeTripId = Session.shared.activeTrip?.id,
                   Session.shared.activeTrip?.is_group_trip == true {
                    await Session.shared.refreshVoteStatus(tripId: activeTripId)
                }
            }
        }

        // Handle vote deletions (vote removed or trip completed)
        Task { [weak self] in
            for await delete in deletes {
                guard self != nil else { break }  // Exit if manager deallocated
                let oldRecord = delete.oldRecord
                let tripId = oldRecord["trip_id"]?.intValue
                debugLog("[Realtime] Vote deleted: tripId=\(String(describing: tripId))")

                // Refresh vote status for the active trip
                if let activeTripId = Session.shared.activeTrip?.id,
                   Session.shared.activeTrip?.is_group_trip == true {
                    await Session.shared.refreshVoteStatus(tripId: activeTripId)
                }
            }
        }
    }

    /// Subscribe to users table for subscription tier changes
    private func subscribeToUserChanges() async {
        guard let userId = currentUserId else { return }

        let channel = supabase.channel("user-\(userId)")
        usersChannel = channel

        // Listen for user updates (subscription_tier, subscription_expires_at)
        let updates = channel.postgresChange(
            UpdateAction.self,
            schema: "public",
            table: "users",
            filter: "id=eq.\(userId)"
        )

        let success = await subscribeWithRetry(channel: channel, name: "users")
        guard success else { return }

        // Handle user updates
        Task { [weak self] in
            for await update in updates {
                guard self != nil else { break }  // Exit if manager deallocated
                let oldRecord = update.oldRecord
                let newRecord = update.record

                // Check if subscription-related fields changed
                let oldTier = oldRecord["subscription_tier"]?.stringValue
                let newTier = newRecord["subscription_tier"]?.stringValue
                let oldExpires = oldRecord["subscription_expires_at"]?.stringValue
                let newExpires = newRecord["subscription_expires_at"]?.stringValue

                if oldTier != newTier || oldExpires != newExpires {
                    debugLog("[Realtime] Subscription change detected: \(oldTier ?? "nil") -> \(newTier ?? "nil")")
                    await Session.shared.handleSubscriptionChange()
                }
            }
        }
    }

    /// Subscribe to live_locations table for real-time location updates
    private func subscribeToLiveLocations() async {
        let channel = supabase.channel("live-locations")
        liveLocationsChannel = channel

        // Listen for new live location inserts
        let inserts = channel.postgresChange(
            InsertAction.self,
            schema: "public",
            table: "live_locations"
        )

        let success = await subscribeWithRetry(channel: channel, name: "live-locations")
        guard success else { return }

        // Handle new live location updates
        Task { [weak self] in
            for await insert in inserts {
                guard self != nil else { break }
                let record = insert.record
                let tripId = record["trip_id"]?.intValue
                debugLog("[Realtime] Live location update: tripId=\(String(describing: tripId))")

                // Refresh friend active trips to pick up new location data
                _ = await Session.shared.loadFriendActiveTrips()
            }
        }
    }
}
