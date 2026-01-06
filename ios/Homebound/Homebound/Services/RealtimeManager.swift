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

    private var currentUserId: Int?
    private var isRunning = false

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

        debugLog("[Realtime] All subscriptions started")
    }

    /// Stop all realtime subscriptions
    /// Called on logout or app termination
    func stop() async {
        guard isRunning else { return }

        debugLog("[Realtime] Stopping all subscriptions")

        await friendshipsChannel?.unsubscribe()
        await tripsChannel?.unsubscribe()
        await participantsChannel?.unsubscribe()
        await eventsChannel?.unsubscribe()

        friendshipsChannel = nil
        tripsChannel = nil
        participantsChannel = nil
        eventsChannel = nil
        currentUserId = nil
        isRunning = false

        debugLog("[Realtime] All subscriptions stopped")
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

        do {
            try await channel.subscribe()
        } catch {
            debugLog("[Realtime] Failed to subscribe to friendships: \(error)")
            return
        }

        // Handle new friendships
        Task {
            for await insert in inserts {
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
        Task {
            for await delete in deletes {
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

        debugLog("[Realtime] Subscribed to friendships")
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

        do {
            try await channel.subscribe()
        } catch {
            debugLog("[Realtime] Failed to subscribe to trips: \(error)")
            return
        }

        // Handle trip updates
        Task {
            for await _ in updates {
                // Refresh trip data - Session will filter to relevant trips
                debugLog("[Realtime] Trip update detected")
                await Session.shared.loadActivePlan()
                _ = await Session.shared.loadAllTrips()
                _ = await Session.shared.loadFriendActiveTrips()
            }
        }

        // Handle new trips
        Task {
            for await _ in inserts {
                debugLog("[Realtime] New trip detected")
                _ = await Session.shared.loadFriendActiveTrips()
            }
        }

        debugLog("[Realtime] Subscribed to trips")
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

        do {
            try await channel.subscribe()
        } catch {
            debugLog("[Realtime] Failed to subscribe to participants: \(error)")
            return
        }

        // Handle new invitations
        Task {
            for await insert in inserts {
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
        Task {
            for await _ in updates {
                // Refresh participant data - someone accepted/declined
                debugLog("[Realtime] Participant status changed")
                await Session.shared.loadActivePlan()
                _ = await Session.shared.loadAllTrips()
            }
        }

        debugLog("[Realtime] Subscribed to trip_participants")
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

        do {
            try await channel.subscribe()
        } catch {
            debugLog("[Realtime] Failed to subscribe to events: \(error)")
            return
        }

        // Handle new events
        Task {
            for await _ in inserts {
                // Someone checked in or performed an action
                debugLog("[Realtime] New event detected (check-in, extension, etc.)")
                await Session.shared.loadActivePlan()
                _ = await Session.shared.loadAllTrips()
                _ = await Session.shared.loadFriendActiveTrips()
            }
        }

        debugLog("[Realtime] Subscribed to events")
    }
}
