import Foundation
import GRDB

/// Local SQLite storage for offline trip viewing and pending sync operations
final class LocalStorage {
    static let shared = LocalStorage()

    private var dbQueue: DatabaseQueue?
    private let maxCachedTrips = 5

    private init() {
        do {
            try setupDatabase()
        } catch {
            print("[LocalStorage] Failed to setup database: \(error)")
        }
    }

    // MARK: - Database Setup

    private func setupDatabase() throws {
        let fileManager = FileManager.default
        let appSupport = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let dbURL = appSupport.appendingPathComponent("homebound.sqlite")

        dbQueue = try DatabaseQueue(path: dbURL.path)

        try dbQueue?.write { db in
            // Create cached_trips table
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS cached_trips (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    activity TEXT NOT NULL,
                    start TEXT NOT NULL,
                    eta TEXT NOT NULL,
                    grace_min INTEGER NOT NULL,
                    location_text TEXT,
                    gen_lat REAL,
                    gen_lon REAL,
                    notes TEXT,
                    status TEXT NOT NULL,
                    completed_at TEXT,
                    last_checkin TEXT,
                    created_at TEXT NOT NULL,
                    contact1 INTEGER,
                    contact2 INTEGER,
                    contact3 INTEGER,
                    checkin_token TEXT,
                    checkout_token TEXT,
                    cached_at TEXT NOT NULL
                )
            """)

            // Create pending_actions table for offline changes
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS pending_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    trip_id INTEGER,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            // Create auth_tokens table (backup to Keychain)
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    access_token TEXT,
                    refresh_token TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
        }

        print("[LocalStorage] Database initialized at \(dbURL.path)")
    }

    // MARK: - Trip Caching

    /// Cache a trip from the server
    func cacheTrip(_ trip: PlanOut) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Insert or replace the trip
                try db.execute(sql: """
                    INSERT OR REPLACE INTO cached_trips (
                        id, user_id, title, activity, start, eta, grace_min,
                        location_text, gen_lat, gen_lon, notes, status,
                        completed_at, last_checkin, created_at,
                        contact1, contact2, contact3,
                        checkin_token, checkout_token, cached_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?
                    )
                """, arguments: [
                    trip.id, trip.user_id, trip.title, trip.activity,
                    ISO8601DateFormatter().string(from: trip.start_at),
                    ISO8601DateFormatter().string(from: trip.eta_at),
                    trip.grace_minutes,
                    trip.location_text, trip.location_lat, trip.location_lng,
                    trip.notes, trip.status,
                    trip.completed_at, trip.last_checkin, trip.created_at,
                    trip.contact1, trip.contact2, trip.contact3,
                    trip.checkin_token, trip.checkout_token,
                    ISO8601DateFormatter().string(from: Date())
                ])

                // Keep only the most recent N trips
                try db.execute(sql: """
                    DELETE FROM cached_trips
                    WHERE id NOT IN (
                        SELECT id FROM cached_trips
                        ORDER BY cached_at DESC
                        LIMIT ?
                    )
                """, arguments: [maxCachedTrips])
            }
        } catch {
            print("[LocalStorage] Failed to cache trip: \(error)")
        }
    }

    /// Cache multiple trips (replaces all cached trips)
    func cacheTrips(_ trips: [PlanOut]) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Clear existing cache
                try db.execute(sql: "DELETE FROM cached_trips")

                // Insert new trips (up to maxCachedTrips)
                let tripsToCache = Array(trips.prefix(maxCachedTrips))
                for trip in tripsToCache {
                    try db.execute(sql: """
                        INSERT INTO cached_trips (
                            id, user_id, title, activity, start, eta, grace_min,
                            location_text, gen_lat, gen_lon, notes, status,
                            completed_at, last_checkin, created_at,
                            contact1, contact2, contact3,
                            checkin_token, checkout_token, cached_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?
                        )
                    """, arguments: [
                        trip.id, trip.user_id, trip.title, trip.activity,
                        ISO8601DateFormatter().string(from: trip.start_at),
                        ISO8601DateFormatter().string(from: trip.eta_at),
                        trip.grace_minutes,
                        trip.location_text, trip.location_lat, trip.location_lng,
                        trip.notes, trip.status,
                        trip.completed_at, trip.last_checkin, trip.created_at,
                        trip.contact1, trip.contact2, trip.contact3,
                        trip.checkin_token, trip.checkout_token,
                        ISO8601DateFormatter().string(from: Date())
                    ])
                }
            }
            print("[LocalStorage] Cached \(min(trips.count, maxCachedTrips)) trips")
        } catch {
            print("[LocalStorage] Failed to cache trips: \(error)")
        }
    }

    /// Get all cached trips
    func getCachedTrips() -> [PlanOut] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT * FROM cached_trips
                    ORDER BY cached_at DESC
                """)

                return rows.compactMap { row -> PlanOut? in
                    guard let id = row["id"] as? Int,
                          let userId = row["user_id"] as? Int,
                          let title = row["title"] as? String,
                          let activity = row["activity"] as? String,
                          let startStr = row["start"] as? String,
                          let etaStr = row["eta"] as? String,
                          let graceMin = row["grace_min"] as? Int,
                          let status = row["status"] as? String,
                          let createdAt = row["created_at"] as? String,
                          let startDate = ISO8601DateFormatter().date(from: startStr),
                          let etaDate = ISO8601DateFormatter().date(from: etaStr)
                    else { return nil }

                    return PlanOut(
                        id: id,
                        user_id: userId,
                        title: title,
                        activity: activity,
                        start_at: startDate,
                        eta_at: etaDate,
                        grace_minutes: graceMin,
                        location_text: row["location_text"] as? String,
                        location_lat: row["gen_lat"] as? Double,
                        location_lng: row["gen_lon"] as? Double,
                        notes: row["notes"] as? String,
                        status: status,
                        completed_at: row["completed_at"] as? String,
                        last_checkin: row["last_checkin"] as? String,
                        created_at: createdAt,
                        contact1: row["contact1"] as? Int,
                        contact2: row["contact2"] as? Int,
                        contact3: row["contact3"] as? Int,
                        checkin_token: row["checkin_token"] as? String,
                        checkout_token: row["checkout_token"] as? String
                    )
                }
            }
        } catch {
            print("[LocalStorage] Failed to get cached trips: \(error)")
            return []
        }
    }

    /// Get a specific cached trip
    func getCachedTrip(id: Int) -> PlanOut? {
        guard let dbQueue = dbQueue else { return nil }

        do {
            return try dbQueue.read { db in
                guard let row = try Row.fetchOne(db, sql: """
                    SELECT * FROM cached_trips WHERE id = ?
                """, arguments: [id]) else { return nil }

                guard let id = row["id"] as? Int,
                      let userId = row["user_id"] as? Int,
                      let title = row["title"] as? String,
                      let activity = row["activity"] as? String,
                      let startStr = row["start"] as? String,
                      let etaStr = row["eta"] as? String,
                      let graceMin = row["grace_min"] as? Int,
                      let status = row["status"] as? String,
                      let createdAt = row["created_at"] as? String,
                      let startDate = ISO8601DateFormatter().date(from: startStr),
                      let etaDate = ISO8601DateFormatter().date(from: etaStr)
                else { return nil }

                return PlanOut(
                    id: id,
                    user_id: userId,
                    title: title,
                    activity: activity,
                    start_at: startDate,
                    eta_at: etaDate,
                    grace_minutes: graceMin,
                    location_text: row["location_text"] as? String,
                    location_lat: row["gen_lat"] as? Double,
                    location_lng: row["gen_lon"] as? Double,
                    notes: row["notes"] as? String,
                    status: status,
                    completed_at: row["completed_at"] as? String,
                    last_checkin: row["last_checkin"] as? String,
                    created_at: createdAt,
                    contact1: row["contact1"] as? Int,
                    contact2: row["contact2"] as? Int,
                    contact3: row["contact3"] as? Int,
                    checkin_token: row["checkin_token"] as? String,
                    checkout_token: row["checkout_token"] as? String
                )
            }
        } catch {
            print("[LocalStorage] Failed to get cached trip: \(error)")
            return nil
        }
    }

    /// Clear all cached trips
    func clearCachedTrips() {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM cached_trips")
            }
        } catch {
            print("[LocalStorage] Failed to clear cached trips: \(error)")
        }
    }

    // MARK: - Pending Actions (Offline Sync)

    /// Queue an action to be synced when online
    func queuePendingAction(type: String, tripId: Int?, payload: [String: Any]) {
        guard let dbQueue = dbQueue else { return }

        do {
            let payloadData = try JSONSerialization.data(withJSONObject: payload)
            let payloadString = String(data: payloadData, encoding: .utf8) ?? "{}"

            try dbQueue.write { db in
                try db.execute(sql: """
                    INSERT INTO pending_actions (action_type, trip_id, payload, created_at)
                    VALUES (?, ?, ?, ?)
                """, arguments: [
                    type,
                    tripId,
                    payloadString,
                    ISO8601DateFormatter().string(from: Date())
                ])
            }
            print("[LocalStorage] Queued pending action: \(type)")
        } catch {
            print("[LocalStorage] Failed to queue pending action: \(error)")
        }
    }

    /// Get all pending actions
    func getPendingActions() -> [(id: Int, type: String, tripId: Int?, payload: [String: Any])] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT * FROM pending_actions ORDER BY created_at ASC
                """)

                return rows.compactMap { row -> (id: Int, type: String, tripId: Int?, payload: [String: Any])? in
                    guard let id = row["id"] as? Int,
                          let type = row["action_type"] as? String,
                          let payloadString = row["payload"] as? String,
                          let payloadData = payloadString.data(using: .utf8),
                          let payload = try? JSONSerialization.jsonObject(with: payloadData) as? [String: Any]
                    else { return nil }

                    return (id: id, type: type, tripId: row["trip_id"] as? Int, payload: payload)
                }
            }
        } catch {
            print("[LocalStorage] Failed to get pending actions: \(error)")
            return []
        }
    }

    /// Remove a pending action after successful sync
    func removePendingAction(id: Int) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM pending_actions WHERE id = ?", arguments: [id])
            }
        } catch {
            print("[LocalStorage] Failed to remove pending action: \(error)")
        }
    }

    /// Check if there are pending actions to sync
    func hasPendingActions() -> Bool {
        guard let dbQueue = dbQueue else { return false }

        do {
            return try dbQueue.read { db in
                let count = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM pending_actions") ?? 0
                return count > 0
            }
        } catch {
            return false
        }
    }

    // MARK: - Auth Tokens (Backup)

    /// Save auth tokens as backup to Keychain
    func saveAuthTokens(access: String?, refresh: String?) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: """
                    INSERT OR REPLACE INTO auth_tokens (id, access_token, refresh_token, updated_at)
                    VALUES (1, ?, ?, ?)
                """, arguments: [
                    access,
                    refresh,
                    ISO8601DateFormatter().string(from: Date())
                ])
            }
        } catch {
            print("[LocalStorage] Failed to save auth tokens: \(error)")
        }
    }

    /// Get saved auth tokens
    func getAuthTokens() -> (access: String?, refresh: String?) {
        guard let dbQueue = dbQueue else { return (nil, nil) }

        do {
            return try dbQueue.read { db in
                guard let row = try Row.fetchOne(db, sql: "SELECT * FROM auth_tokens WHERE id = 1") else {
                    return (nil, nil)
                }
                return (row["access_token"] as? String, row["refresh_token"] as? String)
            }
        } catch {
            print("[LocalStorage] Failed to get auth tokens: \(error)")
            return (nil, nil)
        }
    }

    /// Clear auth tokens on logout
    func clearAuthTokens() {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM auth_tokens")
            }
        } catch {
            print("[LocalStorage] Failed to clear auth tokens: \(error)")
        }
    }

    // MARK: - Clear All Data

    /// Clear all local storage (for logout)
    func clearAll() {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM cached_trips")
                try db.execute(sql: "DELETE FROM pending_actions")
                try db.execute(sql: "DELETE FROM auth_tokens")
            }
            print("[LocalStorage] Cleared all data")
        } catch {
            print("[LocalStorage] Failed to clear all data: \(error)")
        }
    }
}
