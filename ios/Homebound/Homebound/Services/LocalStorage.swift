import Foundation
import GRDB

/// Local SQLite storage for offline trip viewing and pending sync operations
final class LocalStorage {
    static let shared = LocalStorage()

    private var dbQueue: DatabaseQueue?
    private let maxCachedTrips = 5

    // Schema versioning
    private let currentSchemaVersion = 2
    private let userDefaultsSchemaKey = "LocalStorageSchemaVersion"

    private init() {
        do {
            try setupDatabase()
            try runMigrations()
        } catch {
            print("[LocalStorage] Failed to setup database: \(error)")
        }
    }

    // MARK: - Database Versioning

    private func getDatabaseVersion() -> Int {
        UserDefaults.standard.integer(forKey: userDefaultsSchemaKey)
    }

    private func setDatabaseVersion(_ version: Int) {
        UserDefaults.standard.set(version, forKey: userDefaultsSchemaKey)
        print("[LocalStorage] ✅ Schema version updated to \(version)")
    }

    private func needsMigration() -> Bool {
        let currentVersion = getDatabaseVersion()
        return currentVersion < currentSchemaVersion
    }

    // MARK: - Database Migrations

    /// Migration definition structure
    private struct Migration {
        let version: Int
        let description: String
        let execute: (Database) throws -> Void
    }

    /// Run pending database migrations
    private func runMigrations() throws {
        guard let dbQueue = dbQueue else {
            print("[LocalStorage] ⚠️ No database queue available for migrations")
            return
        }

        let currentVersion = getDatabaseVersion()
        print("[LocalStorage] Current schema version: \(currentVersion)")

        if !needsMigration() {
            print("[LocalStorage] ✅ No migrations needed")
            return
        }

        print("[LocalStorage] 🔄 Running migrations from v\(currentVersion) to v\(currentSchemaVersion)...")

        // Define all migrations
        let migrations: [Migration] = [
            Migration(
                version: 1,
                description: "Convert activity TEXT to activity_id INTEGER",
                execute: { db in
                    try self.migrateActivityColumn(db)
                }
            ),
            Migration(
                version: 2,
                description: "Clear orphaned trips from v1 migration",
                execute: { db in
                    try self.clearOrphanedTrips(db)
                }
            )
        ]

        // Run pending migrations in order
        let pendingMigrations = migrations.filter { $0.version > currentVersion }

        for migration in pendingMigrations.sorted(by: { $0.version < $1.version }) {
            print("[LocalStorage] 🔄 Applying migration v\(migration.version): \(migration.description)")

            try dbQueue.write { db in
                try migration.execute(db)
                setDatabaseVersion(migration.version)
            }

            print("[LocalStorage] ✅ Migration v\(migration.version) completed successfully")
        }

        print("[LocalStorage] ✅ All migrations completed")
    }

    /// Migration v1: Convert activity TEXT to activity_id INTEGER
    private func migrateActivityColumn(_ db: Database) throws {
        // Check if migration is needed by inspecting the schema
        let columns = try db.columns(in: "cached_trips")
        let hasOldActivityColumn = columns.contains { $0.name == "activity" && $0.type == "TEXT" }
        let hasNewActivityIdColumn = columns.contains { $0.name == "activity_id" }

        if hasNewActivityIdColumn && !hasOldActivityColumn {
            print("[LocalStorage] ✅ Schema already correct (has activity_id), skipping migration")
            return
        }

        if !hasOldActivityColumn {
            print("[LocalStorage] ✅ No old activity column found, skipping migration")
            return
        }

        print("[LocalStorage] 🔄 Found legacy activity TEXT column, converting to activity_id INTEGER...")

        // Count existing trips (for logging)
        let oldTripCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM cached_trips") ?? 0
        print("[LocalStorage] Found \(oldTripCount) cached trips (will be cleared and re-cached from API)")

        // Strategy: Clear old cached trips rather than migrate
        // Reason: Activities may not be cached yet, leading to orphaned trips
        // Trips will be automatically re-cached from API with correct activity_id

        // Step 1: Create new table with correct schema (empty)
        try db.execute(sql: """
            CREATE TABLE cached_trips_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                activity_id INTEGER NOT NULL,
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

        // Step 2: Drop old table and rename new one
        try db.execute(sql: "DROP TABLE cached_trips")
        try db.execute(sql: "ALTER TABLE cached_trips_new RENAME TO cached_trips")

        print("[LocalStorage] ✅ Activity column migration completed (trips cleared, will re-cache from API)")
    }

    /// Migration v2: Clear orphaned trips from buggy v1 migration
    private func clearOrphanedTrips(_ db: Database) throws {
        // Check for orphaned trips (trips with activity_id that don't exist in cached_activities)
        let orphanedCount = try Int.fetchOne(db, sql: """
            SELECT COUNT(*)
            FROM cached_trips ct
            LEFT JOIN cached_activities ca ON ct.activity_id = ca.id
            WHERE ca.id IS NULL
        """) ?? 0

        if orphanedCount == 0 {
            print("[LocalStorage] ✅ No orphaned trips found")
            return
        }

        print("[LocalStorage] 🔄 Found \(orphanedCount) orphaned trips, clearing...")

        // Delete orphaned trips
        try db.execute(sql: """
            DELETE FROM cached_trips
            WHERE id IN (
                SELECT ct.id
                FROM cached_trips ct
                LEFT JOIN cached_activities ca ON ct.activity_id = ca.id
                WHERE ca.id IS NULL
            )
        """)

        let remainingCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM cached_trips") ?? 0
        print("[LocalStorage] ✅ Cleared \(orphanedCount) orphaned trips, \(remainingCount) trips remaining")
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
                    activity_id INTEGER NOT NULL,
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

            // Create cached_activities table
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS cached_activities (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    default_grace_minutes INTEGER NOT NULL,
                    colors TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    safety_tips TEXT NOT NULL,
                    "order" INTEGER NOT NULL,
                    cached_at TEXT NOT NULL
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
                // Cache the activity first
                try cacheActivity(trip.activity, in: db)

                // Insert or replace the trip
                try db.execute(sql: """
                    INSERT OR REPLACE INTO cached_trips (
                        id, user_id, title, activity_id, start, eta, grace_min,
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
                    trip.id, trip.user_id, trip.title, trip.activity.id,
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

    /// Helper to cache a single activity within a transaction
    private func cacheActivity(_ activity: Activity, in db: Database) throws {
        let colorsJSON = try JSONEncoder().encode(activity.colors)
        let messagesJSON = try JSONEncoder().encode(activity.messages)
        let tipsJSON = try JSONEncoder().encode(activity.safety_tips)

        try db.execute(sql: """
            INSERT OR REPLACE INTO cached_activities
            (id, name, icon, default_grace_minutes, colors, messages, safety_tips, "order", cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, arguments: [
            activity.id,
            activity.name,
            activity.icon,
            activity.default_grace_minutes,
            String(data: colorsJSON, encoding: .utf8),
            String(data: messagesJSON, encoding: .utf8),
            String(data: tipsJSON, encoding: .utf8),
            activity.order,
            ISO8601DateFormatter().string(from: Date())
        ])
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
                    // Cache the activity first
                    try cacheActivity(trip.activity, in: db)

                    try db.execute(sql: """
                        INSERT INTO cached_trips (
                            id, user_id, title, activity_id, start, eta, grace_min,
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
                        trip.id, trip.user_id, trip.title, trip.activity.id,
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
                    SELECT ct.*, ca.id as act_id, ca.name as act_name, ca.icon as act_icon,
                           ca.default_grace_minutes as act_grace, ca.colors as act_colors,
                           ca.messages as act_messages, ca.safety_tips as act_tips,
                           ca."order" as act_order
                    FROM cached_trips ct
                    JOIN cached_activities ca ON ct.activity_id = ca.id
                    ORDER BY ct.cached_at DESC
                """)

                return rows.compactMap { row -> PlanOut? in
                    // Check for orphaned trip (missing activity)
                    guard let activityId = row["act_id"] as? Int else {
                        let tripId = row["id"] as? Int ?? -1
                        let tripTitle = row["title"] as? String ?? "Unknown"
                        print("[LocalStorage] ⚠️ Skipping orphaned trip #\(tripId) '\(tripTitle)' - missing activity")
                        return nil
                    }

                    guard let id = row["id"] as? Int,
                          let userId = row["user_id"] as? Int,
                          let title = row["title"] as? String,
                          let activityName = row["act_name"] as? String,
                          let activityIcon = row["act_icon"] as? String,
                          let activityGrace = row["act_grace"] as? Int,
                          let colorsStr = row["act_colors"] as? String,
                          let messagesStr = row["act_messages"] as? String,
                          let tipsStr = row["act_tips"] as? String,
                          let activityOrder = row["act_order"] as? Int,
                          let startStr = row["start"] as? String,
                          let etaStr = row["eta"] as? String,
                          let graceMin = row["grace_min"] as? Int,
                          let status = row["status"] as? String,
                          let createdAt = row["created_at"] as? String,
                          let startDate = ISO8601DateFormatter().date(from: startStr),
                          let etaDate = ISO8601DateFormatter().date(from: etaStr),
                          let colorsData = colorsStr.data(using: .utf8),
                          let messagesData = messagesStr.data(using: .utf8),
                          let tipsData = tipsStr.data(using: .utf8),
                          let colors = try? JSONDecoder().decode(Activity.ActivityColors.self, from: colorsData),
                          let messages = try? JSONDecoder().decode(Activity.ActivityMessages.self, from: messagesData),
                          let tips = try? JSONDecoder().decode([String].self, from: tipsData)
                    else {
                        print("[LocalStorage] ⚠️ Failed to parse cached trip data")
                        return nil
                    }

                    let activity = Activity(
                        id: activityId,
                        name: activityName,
                        icon: activityIcon,
                        default_grace_minutes: activityGrace,
                        colors: colors,
                        messages: messages,
                        safety_tips: tips,
                        order: activityOrder
                    )

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
                    SELECT ct.*, ca.id as act_id, ca.name as act_name, ca.icon as act_icon,
                           ca.default_grace_minutes as act_grace, ca.colors as act_colors,
                           ca.messages as act_messages, ca.safety_tips as act_tips,
                           ca."order" as act_order
                    FROM cached_trips ct
                    JOIN cached_activities ca ON ct.activity_id = ca.id
                    WHERE ct.id = ?
                """, arguments: [id]) else {
                    print("[LocalStorage] ⚠️ Trip #\(id) not found in cache")
                    return nil
                }

                // Check for orphaned trip (missing activity)
                guard let activityId = row["act_id"] as? Int else {
                    let tripTitle = row["title"] as? String ?? "Unknown"
                    print("[LocalStorage] ⚠️ Trip #\(id) '\(tripTitle)' has missing activity - cannot load")
                    return nil
                }

                guard let tripId = row["id"] as? Int,
                      let userId = row["user_id"] as? Int,
                      let title = row["title"] as? String,
                      let activityName = row["act_name"] as? String,
                      let activityIcon = row["act_icon"] as? String,
                      let activityGrace = row["act_grace"] as? Int,
                      let colorsStr = row["act_colors"] as? String,
                      let messagesStr = row["act_messages"] as? String,
                      let tipsStr = row["act_tips"] as? String,
                      let activityOrder = row["act_order"] as? Int,
                      let startStr = row["start"] as? String,
                      let etaStr = row["eta"] as? String,
                      let graceMin = row["grace_min"] as? Int,
                      let status = row["status"] as? String,
                      let createdAt = row["created_at"] as? String,
                      let startDate = ISO8601DateFormatter().date(from: startStr),
                      let etaDate = ISO8601DateFormatter().date(from: etaStr),
                      let colorsData = colorsStr.data(using: .utf8),
                      let messagesData = messagesStr.data(using: .utf8),
                      let tipsData = tipsStr.data(using: .utf8),
                      let colors = try? JSONDecoder().decode(Activity.ActivityColors.self, from: colorsData),
                      let messages = try? JSONDecoder().decode(Activity.ActivityMessages.self, from: messagesData),
                      let tips = try? JSONDecoder().decode([String].self, from: tipsData)
                else {
                    print("[LocalStorage] ⚠️ Failed to parse cached trip #\(id)")
                    return nil
                }

                let activity = Activity(
                    id: activityId,
                    name: activityName,
                    icon: activityIcon,
                    default_grace_minutes: activityGrace,
                    colors: colors,
                    messages: messages,
                    safety_tips: tips,
                    order: activityOrder
                )

                return PlanOut(
                    id: tripId,
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

    // MARK: - Activity Caching

    /// Cache activities from the server
    func cacheActivities(_ activities: [Activity]) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Clear existing cache
                try db.execute(sql: "DELETE FROM cached_activities")

                // Insert activities
                for activity in activities {
                    let colorsJSON = try JSONEncoder().encode(activity.colors)
                    let messagesJSON = try JSONEncoder().encode(activity.messages)
                    let tipsJSON = try JSONEncoder().encode(activity.safety_tips)

                    try db.execute(sql: """
                        INSERT INTO cached_activities
                        (id, name, icon, default_grace_minutes, colors, messages, safety_tips, "order", cached_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, arguments: [
                        activity.id,
                        activity.name,
                        activity.icon,
                        activity.default_grace_minutes,
                        String(data: colorsJSON, encoding: .utf8),
                        String(data: messagesJSON, encoding: .utf8),
                        String(data: tipsJSON, encoding: .utf8),
                        activity.order,
                        ISO8601DateFormatter().string(from: Date())
                    ])
                }
            }
            print("[LocalStorage] Cached \(activities.count) activities")
        } catch {
            print("[LocalStorage] Failed to cache activities: \(error)")
        }
    }

    /// Get cached activities
    func getCachedActivities() -> [Activity] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT * FROM cached_activities ORDER BY "order" ASC
                """)

                return rows.compactMap { row -> Activity? in
                    guard let id = row["id"] as? Int,
                          let name = row["name"] as? String,
                          let icon = row["icon"] as? String,
                          let graceMin = row["default_grace_minutes"] as? Int,
                          let colorsStr = row["colors"] as? String,
                          let messagesStr = row["messages"] as? String,
                          let tipsStr = row["safety_tips"] as? String,
                          let order = row["order"] as? Int,
                          let colorsData = colorsStr.data(using: .utf8),
                          let messagesData = messagesStr.data(using: .utf8),
                          let tipsData = tipsStr.data(using: .utf8),
                          let colors = try? JSONDecoder().decode(Activity.ActivityColors.self, from: colorsData),
                          let messages = try? JSONDecoder().decode(Activity.ActivityMessages.self, from: messagesData),
                          let tips = try? JSONDecoder().decode([String].self, from: tipsData)
                    else { return nil }

                    return Activity(
                        id: id,
                        name: name,
                        icon: icon,
                        default_grace_minutes: graceMin,
                        colors: colors,
                        messages: messages,
                        safety_tips: tips,
                        order: order
                    )
                }
            }
        } catch {
            print("[LocalStorage] Failed to get cached activities: \(error)")
            return []
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
                try db.execute(sql: "DELETE FROM cached_activities")
            }
            print("[LocalStorage] Cleared all data")
        } catch {
            print("[LocalStorage] Failed to clear all data: \(error)")
        }
    }

    // MARK: - Debug Helpers

    /// Print database schema information for debugging
    func debugSchema() {
        guard let dbQueue = dbQueue else {
            print("[LocalStorage] ⚠️ No database queue available")
            return
        }

        do {
            try dbQueue.read { db in
                print("[LocalStorage] 📊 Database Schema Information")
                print(String(repeating: "=", count: 60))
                print("Schema Version: \(getDatabaseVersion())")
                print("Target Version: \(currentSchemaVersion)")
                print("")

                let tables = ["cached_trips", "cached_activities", "pending_actions", "auth_tokens"]

                for tableName in tables {
                    if try db.tableExists(tableName) {
                        print("Table: \(tableName)")
                        let columns = try db.columns(in: tableName)
                        for column in columns {
                            let nullable = column.isNotNull ? "NOT NULL" : "NULL"
                            print("  - \(column.name): \(column.type) (\(nullable))")
                        }

                        // Get row count
                        let count = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM \(tableName)") ?? 0
                        print("  Rows: \(count)")
                        print("")
                    } else {
                        print("Table: \(tableName) - NOT FOUND")
                        print("")
                    }
                }

                print(String(repeating: "=", count: 60))
            }
        } catch {
            print("[LocalStorage] ⚠️ Failed to inspect schema: \(error)")
        }
    }

    /// Check database health and report issues
    func healthCheck() -> (isHealthy: Bool, issues: [String]) {
        guard let dbQueue = dbQueue else {
            return (false, ["Database queue not initialized"])
        }

        var issues: [String] = []

        do {
            try dbQueue.read { db in
                // Check schema version
                let currentVersion = getDatabaseVersion()
                if currentVersion < currentSchemaVersion {
                    issues.append("Schema outdated: v\(currentVersion) (expected v\(currentSchemaVersion))")
                }

                // Check required tables exist
                let requiredTables = ["cached_trips", "cached_activities", "pending_actions", "auth_tokens"]
                for table in requiredTables {
                    if try !db.tableExists(table) {
                        issues.append("Missing required table: \(table)")
                    }
                }

                // Check cached_trips has correct schema
                if try db.tableExists("cached_trips") {
                    let columns = try db.columns(in: "cached_trips")
                    let hasActivityId = columns.contains { $0.name == "activity_id" }
                    let hasOldActivity = columns.contains { $0.name == "activity" && $0.type == "TEXT" }

                    if !hasActivityId {
                        issues.append("cached_trips missing activity_id column")
                    }
                    if hasOldActivity {
                        issues.append("cached_trips has legacy activity TEXT column")
                    }
                }

                // Check for orphaned trips
                let orphanedCount = try Int.fetchOne(db, sql: """
                    SELECT COUNT(*)
                    FROM cached_trips ct
                    LEFT JOIN cached_activities ca ON ct.activity_id = ca.id
                    WHERE ca.id IS NULL
                """) ?? 0

                if orphanedCount > 0 {
                    issues.append("Found \(orphanedCount) orphaned trip(s) with missing activities")
                }
            }
        } catch {
            issues.append("Health check error: \(error.localizedDescription)")
        }

        return (issues.isEmpty, issues)
    }
}
