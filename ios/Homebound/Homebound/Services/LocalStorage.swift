import Foundation
import GRDB

/// Local SQLite storage for offline trip viewing and pending sync operations
final class LocalStorage {
    static let shared = LocalStorage()

    private var dbQueue: DatabaseQueue?
    private let maxCachedTrips = 25

    // Schema versioning
    private let currentSchemaVersion = 2
    private let userDefaultsSchemaKey = "LocalStorageSchemaVersion"

    private init() {
        do {
            try setupDatabase()
            try runMigrations()
        } catch {
            debugLog("[LocalStorage] Failed to setup database: \(error)")
        }
    }

    // MARK: - Database Versioning

    private func getDatabaseVersion() -> Int {
        UserDefaults.standard.integer(forKey: userDefaultsSchemaKey)
    }

    private func setDatabaseVersion(_ version: Int) {
        UserDefaults.standard.set(version, forKey: userDefaultsSchemaKey)
        debugLog("[LocalStorage] ✅ Schema version updated to \(version)")
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
            debugLog("[LocalStorage] ⚠️ No database queue available for migrations")
            return
        }

        let currentVersion = getDatabaseVersion()
        debugLog("[LocalStorage] Current schema version: \(currentVersion)")

        if !needsMigration() {
            debugLog("[LocalStorage] ✅ No migrations needed")
            return
        }

        debugLog("[LocalStorage] 🔄 Running migrations from v\(currentVersion) to v\(currentSchemaVersion)...")

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
            debugLog("[LocalStorage] 🔄 Applying migration v\(migration.version): \(migration.description)")

            try dbQueue.write { db in
                try migration.execute(db)
                setDatabaseVersion(migration.version)
            }

            debugLog("[LocalStorage] ✅ Migration v\(migration.version) completed successfully")
        }

        debugLog("[LocalStorage] ✅ All migrations completed")
    }

    /// Migration v1: Convert activity TEXT to activity_id INTEGER
    private func migrateActivityColumn(_ db: Database) throws {
        // Check if migration is needed by inspecting the schema
        let columns = try db.columns(in: "cached_trips")
        let hasOldActivityColumn = columns.contains { $0.name == "activity" && $0.type == "TEXT" }
        let hasNewActivityIdColumn = columns.contains { $0.name == "activity_id" }

        if hasNewActivityIdColumn && !hasOldActivityColumn {
            debugLog("[LocalStorage] ✅ Schema already correct (has activity_id), skipping migration")
            return
        }

        if !hasOldActivityColumn {
            debugLog("[LocalStorage] ✅ No old activity column found, skipping migration")
            return
        }

        debugLog("[LocalStorage] 🔄 Found legacy activity TEXT column, converting to activity_id INTEGER...")

        // Count existing trips (for logging)
        let oldTripCount = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM cached_trips") ?? 0
        debugLog("[LocalStorage] Found \(oldTripCount) cached trips (will be cleared and re-cached from API)")

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

        debugLog("[LocalStorage] ✅ Activity column migration completed (trips cleared, will re-cache from API)")
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
            debugLog("[LocalStorage] ✅ No orphaned trips found")
            return
        }

        debugLog("[LocalStorage] 🔄 Found \(orphanedCount) orphaned trips, clearing...")

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
        debugLog("[LocalStorage] ✅ Cleared \(orphanedCount) orphaned trips, \(remainingCount) trips remaining")
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

            // Create cached_contacts table
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS cached_contacts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                )
            """)

            // Create cached_timeline table for offline check-in display
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS cached_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trip_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    at TEXT NOT NULL,
                    lat REAL,
                    lon REAL,
                    extended_by INTEGER,
                    cached_at TEXT NOT NULL
                )
            """)

            // Create failed_actions table for tracking permanently failed sync actions
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS failed_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    trip_id INTEGER,
                    error TEXT NOT NULL,
                    failed_at TEXT NOT NULL
                )
            """)
        }

        debugLog("[LocalStorage] Database initialized at \(dbURL.path)")
    }

    // MARK: - Trip Caching

    /// Cache a trip from the server
    func cacheTrip(_ trip: Trip) {
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
                    trip.completed_at.map { ISO8601DateFormatter().string(from: $0) }, trip.last_checkin, trip.created_at,
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
            debugLog("[LocalStorage] Failed to cache trip: \(error)")
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
    /// Uses savepoint for atomic operation - if any insert fails, entire operation rolls back
    func cacheTrips(_ trips: [Trip]) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Use savepoint for rollback capability - if any insert fails, nothing is deleted
                try db.inSavepoint {
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
                            trip.completed_at.map { ISO8601DateFormatter().string(from: $0) }, trip.last_checkin, trip.created_at,
                            trip.contact1, trip.contact2, trip.contact3,
                            trip.checkin_token, trip.checkout_token,
                            ISO8601DateFormatter().string(from: Date())
                        ])
                    }
                    return .commit  // Only commits if all inserts succeed
                }
            }
            debugLog("[LocalStorage] Cached \(min(trips.count, maxCachedTrips)) trips")
        } catch {
            debugLog("[LocalStorage] ❌ Failed to cache trips (rolled back): \(error)")
        }
    }

    /// Get all cached trips
    func getCachedTrips() -> [Trip] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                // Use LEFT JOIN so trips are returned even if activity is missing
                let rows = try Row.fetchAll(db, sql: """
                    SELECT ct.*, ca.id as act_id, ca.name as act_name, ca.icon as act_icon,
                           ca.default_grace_minutes as act_grace, ca.colors as act_colors,
                           ca.messages as act_messages, ca.safety_tips as act_tips,
                           ca."order" as act_order
                    FROM cached_trips ct
                    LEFT JOIN cached_activities ca ON ct.activity_id = ca.id
                    ORDER BY ct.cached_at DESC
                """)

                return rows.compactMap { row -> Trip? in
                    // Handle Int64 -> Int conversion (SQLite uses 64-bit integers)
                    guard let id = (row["id"] as? Int64).map({ Int($0) }) ?? (row["id"] as? Int) else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse trip id")
                        return nil
                    }
                    guard let userId = (row["user_id"] as? Int64).map({ Int($0) }) ?? (row["user_id"] as? Int) else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse user_id for trip #\(id)")
                        return nil
                    }
                    guard let title = row["title"] as? String else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse title for trip #\(id)")
                        return nil
                    }
                    guard let startStr = row["start"] as? String else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse start for trip #\(id)")
                        return nil
                    }
                    guard let etaStr = row["eta"] as? String else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse eta for trip #\(id)")
                        return nil
                    }
                    guard let graceMin = (row["grace_min"] as? Int64).map({ Int($0) }) ?? (row["grace_min"] as? Int) else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse grace_min for trip #\(id)")
                        return nil
                    }
                    guard let status = row["status"] as? String else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse status for trip #\(id)")
                        return nil
                    }
                    guard let createdAt = row["created_at"] as? String else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse created_at for trip #\(id)")
                        return nil
                    }

                    // Parse dates - try with and without fractional seconds
                    let dateFormatter = ISO8601DateFormatter()
                    var startDate = dateFormatter.date(from: startStr)
                    if startDate == nil {
                        dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                        startDate = dateFormatter.date(from: startStr)
                    }
                    guard let startDate = startDate else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse start date '\(startStr)' for trip #\(id)")
                        return nil
                    }

                    dateFormatter.formatOptions = [.withInternetDateTime]
                    var etaDate = dateFormatter.date(from: etaStr)
                    if etaDate == nil {
                        dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                        etaDate = dateFormatter.date(from: etaStr)
                    }
                    guard let etaDate = etaDate else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse eta date '\(etaStr)' for trip #\(id)")
                        return nil
                    }

                    // Parse optional completed_at date
                    let completedAtDate: Date? = {
                        if let completedAtStr = row["completed_at"] as? String {
                            return ISO8601DateFormatter().date(from: completedAtStr)
                        }
                        return nil
                    }()

                    // Build activity - use placeholder if activity data is missing
                    // Handle Int64 -> Int conversion for activity fields
                    let activity: Activity
                    if let activityId = (row["act_id"] as? Int64).map({ Int($0) }) ?? (row["act_id"] as? Int),
                       let activityName = row["act_name"] as? String,
                       let activityIcon = row["act_icon"] as? String,
                       let activityGrace = (row["act_grace"] as? Int64).map({ Int($0) }) ?? (row["act_grace"] as? Int),
                       let colorsStr = row["act_colors"] as? String,
                       let messagesStr = row["act_messages"] as? String,
                       let tipsStr = row["act_tips"] as? String,
                       let activityOrder = (row["act_order"] as? Int64).map({ Int($0) }) ?? (row["act_order"] as? Int),
                       let colorsData = colorsStr.data(using: .utf8),
                       let messagesData = messagesStr.data(using: .utf8),
                       let tipsData = tipsStr.data(using: .utf8),
                       let colors = try? JSONDecoder().decode(Activity.ActivityColors.self, from: colorsData),
                       let messages = try? JSONDecoder().decode(Activity.ActivityMessages.self, from: messagesData),
                       let tips = try? JSONDecoder().decode([String].self, from: tipsData) {
                        activity = Activity(
                            id: activityId,
                            name: activityName,
                            icon: activityIcon,
                            default_grace_minutes: activityGrace,
                            colors: colors,
                            messages: messages,
                            safety_tips: tips,
                            order: activityOrder
                        )
                    } else {
                        // Placeholder activity for trips with missing activity data
                        let activityId = (row["activity_id"] as? Int64).map({ Int($0) }) ?? (row["activity_id"] as? Int) ?? 0
                        debugLog("[LocalStorage] ⚠️ Using placeholder activity for trip #\(id) '\(title)'")
                        activity = Activity(
                            id: activityId,
                            name: "Activity",
                            icon: "figure.walk",
                            default_grace_minutes: 15,
                            colors: Activity.ActivityColors(primary: "#666666", secondary: "#999999", accent: "#CCCCCC"),
                            messages: Activity.ActivityMessages(
                                start: "Start your trip",
                                checkin: "Check in",
                                checkout: "I'm safe",
                                overdue: "Overdue",
                                encouragement: ["Stay safe!"]
                            ),
                            safety_tips: [],
                            order: 999
                        )
                    }

                    return Trip(
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
                        completed_at: completedAtDate,
                        last_checkin: row["last_checkin"] as? String,
                        created_at: createdAt,
                        contact1: (row["contact1"] as? Int64).map({ Int($0) }) ?? (row["contact1"] as? Int),
                        contact2: (row["contact2"] as? Int64).map({ Int($0) }) ?? (row["contact2"] as? Int),
                        contact3: (row["contact3"] as? Int64).map({ Int($0) }) ?? (row["contact3"] as? Int),
                        checkin_token: row["checkin_token"] as? String,
                        checkout_token: row["checkout_token"] as? String
                    )
                }
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached trips: \(error)")
            return []
        }
    }

    /// Get a specific cached trip
    /// Uses LEFT JOIN with placeholder activity for consistency with getCachedTrips()
    func getCachedTrip(id: Int) -> Trip? {
        guard let dbQueue = dbQueue else { return nil }

        do {
            return try dbQueue.read { db -> Trip? in
                // Use LEFT JOIN so trips are returned even if activity is missing (consistent with getCachedTrips)
                guard let row = try Row.fetchOne(db, sql: """
                    SELECT ct.*, ca.id as act_id, ca.name as act_name, ca.icon as act_icon,
                           ca.default_grace_minutes as act_grace, ca.colors as act_colors,
                           ca.messages as act_messages, ca.safety_tips as act_tips,
                           ca."order" as act_order
                    FROM cached_trips ct
                    LEFT JOIN cached_activities ca ON ct.activity_id = ca.id
                    WHERE ct.id = ?
                """, arguments: [id]) else {
                    debugLog("[LocalStorage] ⚠️ Trip #\(id) not found in cache")
                    return nil
                }

                // Handle Int64 -> Int conversion (SQLite uses 64-bit integers)
                guard let tripId = (row["id"] as? Int64).map({ Int($0) }) ?? (row["id"] as? Int),
                      let userId = (row["user_id"] as? Int64).map({ Int($0) }) ?? (row["user_id"] as? Int),
                      let title = row["title"] as? String,
                      let startStr = row["start"] as? String,
                      let etaStr = row["eta"] as? String,
                      let graceMin = (row["grace_min"] as? Int64).map({ Int($0) }) ?? (row["grace_min"] as? Int),
                      let status = row["status"] as? String,
                      let createdAt = row["created_at"] as? String
                else {
                    debugLog("[LocalStorage] ⚠️ Failed to parse cached trip #\(id)")
                    return nil
                }

                // Parse dates - try with and without fractional seconds
                let dateFormatter = ISO8601DateFormatter()
                var startDate = dateFormatter.date(from: startStr)
                if startDate == nil {
                    dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                    startDate = dateFormatter.date(from: startStr)
                }
                guard let startDate = startDate else {
                    debugLog("[LocalStorage] ⚠️ Failed to parse start date for trip #\(id)")
                    return nil
                }

                dateFormatter.formatOptions = [.withInternetDateTime]
                var etaDate = dateFormatter.date(from: etaStr)
                if etaDate == nil {
                    dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                    etaDate = dateFormatter.date(from: etaStr)
                }
                guard let etaDate = etaDate else {
                    debugLog("[LocalStorage] ⚠️ Failed to parse eta date for trip #\(id)")
                    return nil
                }

                // Parse optional completed_at date
                let completedAtDate: Date? = {
                    if let completedAtStr = row["completed_at"] as? String {
                        return ISO8601DateFormatter().date(from: completedAtStr)
                    }
                    return nil
                }()

                // Build activity - use placeholder if activity data is missing (consistent with getCachedTrips)
                // Handle Int64 -> Int conversion for activity fields
                let activity: Activity
                if let activityId = (row["act_id"] as? Int64).map({ Int($0) }) ?? (row["act_id"] as? Int),
                   let activityName = row["act_name"] as? String,
                   let activityIcon = row["act_icon"] as? String,
                   let activityGrace = (row["act_grace"] as? Int64).map({ Int($0) }) ?? (row["act_grace"] as? Int),
                   let colorsStr = row["act_colors"] as? String,
                   let messagesStr = row["act_messages"] as? String,
                   let tipsStr = row["act_tips"] as? String,
                   let activityOrder = (row["act_order"] as? Int64).map({ Int($0) }) ?? (row["act_order"] as? Int),
                   let colorsData = colorsStr.data(using: .utf8),
                   let messagesData = messagesStr.data(using: .utf8),
                   let tipsData = tipsStr.data(using: .utf8),
                   let colors = try? JSONDecoder().decode(Activity.ActivityColors.self, from: colorsData),
                   let messages = try? JSONDecoder().decode(Activity.ActivityMessages.self, from: messagesData),
                   let tips = try? JSONDecoder().decode([String].self, from: tipsData) {
                    activity = Activity(
                        id: activityId,
                        name: activityName,
                        icon: activityIcon,
                        default_grace_minutes: activityGrace,
                        colors: colors,
                        messages: messages,
                        safety_tips: tips,
                        order: activityOrder
                    )
                } else {
                    // Placeholder activity for trips with missing activity data
                    let activityId = (row["activity_id"] as? Int64).map({ Int($0) }) ?? (row["activity_id"] as? Int) ?? 0
                    debugLog("[LocalStorage] ⚠️ Using placeholder activity for trip #\(tripId) '\(title)'")
                    activity = Activity(
                        id: activityId,
                        name: "Activity",
                        icon: "figure.walk",
                        default_grace_minutes: 15,
                        colors: Activity.ActivityColors(primary: "#666666", secondary: "#999999", accent: "#CCCCCC"),
                        messages: Activity.ActivityMessages(
                            start: "Start your trip",
                            checkin: "Check in",
                            checkout: "I'm safe",
                            overdue: "Overdue",
                            encouragement: ["Stay safe!"]
                        ),
                        safety_tips: [],
                        order: 999
                    )
                }

                return Trip(
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
                    completed_at: completedAtDate,
                    last_checkin: row["last_checkin"] as? String,
                    created_at: createdAt,
                    contact1: (row["contact1"] as? Int64).map({ Int($0) }) ?? (row["contact1"] as? Int),
                    contact2: (row["contact2"] as? Int64).map({ Int($0) }) ?? (row["contact2"] as? Int),
                    contact3: (row["contact3"] as? Int64).map({ Int($0) }) ?? (row["contact3"] as? Int),
                    checkin_token: row["checkin_token"] as? String,
                    checkout_token: row["checkout_token"] as? String
                )
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached trip: \(error)")
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
            debugLog("[LocalStorage] Failed to clear cached trips: \(error)")
        }
    }

    /// Remove a specific cached trip
    func removeCachedTrip(tripId: Int) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM cached_trips WHERE id = ?", arguments: [tripId])
            }
            debugLog("[LocalStorage] ✅ Removed cached trip #\(tripId)")
        } catch {
            debugLog("[LocalStorage] Failed to remove cached trip: \(error)")
        }
    }

    /// Update specific fields of a cached trip (for offline state updates)
    func updateCachedTripFields(tripId: Int, updates: [String: Any]) {
        guard let dbQueue = dbQueue else { return }

        // Map Swift field names to SQLite column names
        let columnMapping: [String: String] = [
            "status": "status",
            "eta": "eta",
            "completed_at": "completed_at",
            "last_checkin": "last_checkin",
            "title": "title",
            "activity_id": "activity_id",
            "grace_min": "grace_min",
            "location_text": "location_text",
            "gen_lat": "gen_lat",
            "gen_lon": "gen_lon",
            "notes": "notes",
            "contact1": "contact1",
            "contact2": "contact2",
            "contact3": "contact3"
        ]

        do {
            try dbQueue.write { db in
                var setClauses: [String] = []
                var arguments: [DatabaseValue] = []

                for (key, value) in updates {
                    guard let column = columnMapping[key] else {
                        debugLog("[LocalStorage] ⚠️ Unknown field: \(key)")
                        continue
                    }

                    setClauses.append("\(column) = ?")

                    if let stringValue = value as? String {
                        arguments.append(stringValue.databaseValue)
                    } else if let dateValue = value as? Date {
                        arguments.append(ISO8601DateFormatter().string(from: dateValue).databaseValue)
                    } else if let intValue = value as? Int {
                        arguments.append(intValue.databaseValue)
                    } else if let doubleValue = value as? Double {
                        arguments.append(doubleValue.databaseValue)
                    } else if value is NSNull {
                        arguments.append(.null)
                    } else {
                        debugLog("[LocalStorage] ⚠️ Unsupported value type for \(key)")
                        continue
                    }
                }

                guard !setClauses.isEmpty else {
                    debugLog("[LocalStorage] ⚠️ No valid fields to update")
                    return
                }

                arguments.append(tripId.databaseValue)

                let sql = "UPDATE cached_trips SET \(setClauses.joined(separator: ", ")) WHERE id = ?"
                try db.execute(sql: sql, arguments: StatementArguments(arguments))
                debugLog("[LocalStorage] ✅ Updated trip #\(tripId): \(updates.keys.joined(separator: ", "))")
            }
        } catch {
            debugLog("[LocalStorage] Failed to update cached trip fields: \(error)")
        }
    }

    // MARK: - Pending Actions (Offline Sync)

    /// Check if a similar action is already pending (for duplicate detection)
    func hasPendingAction(type: String, tripId: Int?) -> Bool {
        guard let dbQueue = dbQueue else { return false }

        do {
            return try dbQueue.read { db in
                let count = try Int.fetchOne(db, sql: """
                    SELECT COUNT(*) FROM pending_actions
                    WHERE action_type = ? AND (trip_id = ? OR (trip_id IS NULL AND ? IS NULL))
                """, arguments: [type, tripId, tripId]) ?? 0
                return count > 0
            }
        } catch {
            debugLog("[LocalStorage] Failed to check pending action: \(error)")
            return false
        }
    }

    /// Queue an action to be synced when online
    /// For idempotent actions (checkin, extend), duplicates are skipped
    func queuePendingAction(type: String, tripId: Int?, payload: [String: Any]) {
        guard let dbQueue = dbQueue else { return }

        // Skip duplicate idempotent actions (checkin, extend for the same trip)
        // These actions are idempotent - queueing multiple has no benefit
        if ["checkin", "extend"].contains(type) && hasPendingAction(type: type, tripId: tripId) {
            debugLog("[LocalStorage] ⚠️ Skipping duplicate \(type) action for trip #\(tripId ?? -1)")
            return
        }

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
            debugLog("[LocalStorage] Queued pending action: \(type)")
        } catch {
            debugLog("[LocalStorage] Failed to queue pending action: \(error)")
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
            debugLog("[LocalStorage] Failed to get pending actions: \(error)")
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
            debugLog("[LocalStorage] Failed to remove pending action: \(error)")
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

    /// Clear all pending actions (useful for stuck actions)
    func clearPendingActions() {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM pending_actions")
            }
            debugLog("[LocalStorage] ✅ Cleared all pending actions")
        } catch {
            debugLog("[LocalStorage] ❌ Failed to clear pending actions: \(error)")
        }
    }

    // MARK: - Failed Actions (for user awareness of permanently failed syncs)

    /// Log a permanently failed action for user awareness
    func logFailedAction(type: String, tripId: Int?, error: String) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: """
                    INSERT INTO failed_actions (action_type, trip_id, error, failed_at)
                    VALUES (?, ?, ?, ?)
                """, arguments: [
                    type,
                    tripId,
                    error,
                    ISO8601DateFormatter().string(from: Date())
                ])
            }
            debugLog("[LocalStorage] ⚠️ Logged failed action: \(type) - \(error)")
        } catch {
            debugLog("[LocalStorage] ❌ Failed to log failed action: \(error)")
        }
    }

    /// Get count of failed actions
    func getFailedActionsCount() -> Int {
        guard let dbQueue = dbQueue else { return 0 }

        do {
            return try dbQueue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM failed_actions") ?? 0
            }
        } catch {
            debugLog("[LocalStorage] Failed to get failed actions count: \(error)")
            return 0
        }
    }

    /// Get all failed actions for display
    func getFailedActions() -> [(id: Int, type: String, tripId: Int?, error: String, failedAt: String)] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT * FROM failed_actions ORDER BY failed_at DESC
                """)

                return rows.compactMap { row -> (id: Int, type: String, tripId: Int?, error: String, failedAt: String)? in
                    guard let id = row["id"] as? Int,
                          let type = row["action_type"] as? String,
                          let error = row["error"] as? String,
                          let failedAt = row["failed_at"] as? String
                    else { return nil }

                    return (id: id, type: type, tripId: row["trip_id"] as? Int, error: error, failedAt: failedAt)
                }
            }
        } catch {
            debugLog("[LocalStorage] Failed to get failed actions: \(error)")
            return []
        }
    }

    /// Clear all failed actions (after user acknowledges)
    func clearFailedActions() {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM failed_actions")
            }
            debugLog("[LocalStorage] ✅ Cleared all failed actions")
        } catch {
            debugLog("[LocalStorage] ❌ Failed to clear failed actions: \(error)")
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
            debugLog("[LocalStorage] Failed to save auth tokens: \(error)")
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
            debugLog("[LocalStorage] Failed to get auth tokens: \(error)")
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
            debugLog("[LocalStorage] Failed to clear auth tokens: \(error)")
        }
    }

    // MARK: - Activity Caching

    /// Cache activities from the server
    /// Uses savepoint for atomic operation - if any insert fails, entire operation rolls back
    func cacheActivities(_ activities: [Activity]) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Use savepoint for rollback capability
                try db.inSavepoint {
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
                    return .commit
                }
            }
            debugLog("[LocalStorage] Cached \(activities.count) activities")
        } catch {
            debugLog("[LocalStorage] ❌ Failed to cache activities (rolled back): \(error)")
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
                    // Handle Int64 -> Int conversion (SQLite uses 64-bit integers)
                    guard let id = (row["id"] as? Int64).map({ Int($0) }) ?? (row["id"] as? Int),
                          let name = row["name"] as? String,
                          let icon = row["icon"] as? String,
                          let graceMin = (row["default_grace_minutes"] as? Int64).map({ Int($0) }) ?? (row["default_grace_minutes"] as? Int),
                          let colorsStr = row["colors"] as? String,
                          let messagesStr = row["messages"] as? String,
                          let tipsStr = row["safety_tips"] as? String,
                          let order = (row["order"] as? Int64).map({ Int($0) }) ?? (row["order"] as? Int),
                          let colorsData = colorsStr.data(using: .utf8),
                          let messagesData = messagesStr.data(using: .utf8),
                          let tipsData = tipsStr.data(using: .utf8),
                          let colors = try? JSONDecoder().decode(Activity.ActivityColors.self, from: colorsData),
                          let messages = try? JSONDecoder().decode(Activity.ActivityMessages.self, from: messagesData),
                          let tips = try? JSONDecoder().decode([String].self, from: tipsData)
                    else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse cached activity data")
                        return nil
                    }

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
            debugLog("[LocalStorage] Failed to get cached activities: \(error)")
            return []
        }
    }

    // MARK: - Contact Caching

    /// Cache a single contact
    func cacheContact(_ contact: Contact) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: """
                    INSERT OR REPLACE INTO cached_contacts (id, user_id, name, email, cached_at)
                    VALUES (?, ?, ?, ?, ?)
                """, arguments: [
                    contact.id,
                    contact.user_id,
                    contact.name,
                    contact.email,
                    ISO8601DateFormatter().string(from: Date())
                ])
            }
            debugLog("[LocalStorage] Cached contact: \(contact.name)")
        } catch {
            debugLog("[LocalStorage] Failed to cache contact: \(error)")
        }
    }

    /// Cache multiple contacts from the server
    /// Uses savepoint for atomic operation - if any insert fails, entire operation rolls back
    func cacheContacts(_ contacts: [Contact]) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Use savepoint for rollback capability
                try db.inSavepoint {
                    // Clear existing cache
                    try db.execute(sql: "DELETE FROM cached_contacts")

                    // Insert contacts
                    for contact in contacts {
                        try db.execute(sql: """
                            INSERT INTO cached_contacts (id, user_id, name, email, cached_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, arguments: [
                            contact.id,
                            contact.user_id,
                            contact.name,
                            contact.email,
                            ISO8601DateFormatter().string(from: Date())
                        ])
                    }
                    return .commit
                }
            }
            debugLog("[LocalStorage] Cached \(contacts.count) contacts")
        } catch {
            debugLog("[LocalStorage] ❌ Failed to cache contacts (rolled back): \(error)")
        }
    }

    /// Get cached contacts for offline access
    func getCachedContacts() -> [Contact] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT * FROM cached_contacts ORDER BY name ASC
                """)

                return rows.compactMap { row -> Contact? in
                    // Handle Int64 -> Int conversion (SQLite uses 64-bit integers)
                    guard let id = (row["id"] as? Int64).map({ Int($0) }) ?? (row["id"] as? Int),
                          let userId = (row["user_id"] as? Int64).map({ Int($0) }) ?? (row["user_id"] as? Int),
                          let name = row["name"] as? String,
                          let email = row["email"] as? String
                    else {
                        debugLog("[LocalStorage] ⚠️ Failed to parse cached contact data")
                        return nil
                    }

                    return Contact(id: id, user_id: userId, name: name, email: email)
                }
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached contacts: \(error)")
            return []
        }
    }

    /// Update a cached contact
    func updateCachedContact(contactId: Int, name: String, email: String) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: """
                    UPDATE cached_contacts SET name = ?, email = ?, cached_at = ?
                    WHERE id = ?
                """, arguments: [
                    name,
                    email,
                    ISO8601DateFormatter().string(from: Date()),
                    contactId
                ])
            }
            debugLog("[LocalStorage] ✅ Updated cached contact #\(contactId)")
        } catch {
            debugLog("[LocalStorage] Failed to update cached contact: \(error)")
        }
    }

    /// Remove a cached contact
    func removeCachedContact(contactId: Int) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM cached_contacts WHERE id = ?", arguments: [contactId])
            }
            debugLog("[LocalStorage] ✅ Removed cached contact #\(contactId)")
        } catch {
            debugLog("[LocalStorage] Failed to remove cached contact: \(error)")
        }
    }

    // MARK: - Timeline Caching

    /// Cache timeline events for a trip
    func cacheTimeline(tripId: Int, events: [TimelineEvent]) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                // Clear existing timeline for this trip
                try db.execute(sql: "DELETE FROM cached_timeline WHERE trip_id = ?", arguments: [tripId])

                // Insert new events
                for event in events {
                    try db.execute(sql: """
                        INSERT INTO cached_timeline (trip_id, kind, at, lat, lon, extended_by, cached_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, arguments: [
                        tripId,
                        event.kind,
                        event.at,
                        event.lat,
                        event.lon,
                        event.extended_by,
                        ISO8601DateFormatter().string(from: Date())
                    ])
                }
            }
            debugLog("[LocalStorage] Cached \(events.count) timeline events for trip #\(tripId)")
        } catch {
            debugLog("[LocalStorage] Failed to cache timeline: \(error)")
        }
    }

    /// Get cached timeline events for a trip
    func getCachedTimeline(tripId: Int) -> [TimelineEvent] {
        guard let dbQueue = dbQueue else { return [] }

        do {
            return try dbQueue.read { db in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT kind, at, lat, lon, extended_by FROM cached_timeline
                    WHERE trip_id = ?
                    ORDER BY at ASC
                """, arguments: [tripId])

                return rows.compactMap { row -> TimelineEvent? in
                    guard let kind = row["kind"] as? String,
                          let at = row["at"] as? String
                    else { return nil }

                    return TimelineEvent(
                        kind: kind,
                        at: at,
                        lat: row["lat"] as? Double,
                        lon: row["lon"] as? Double,
                        extended_by: row["extended_by"] as? Int
                    )
                }
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached timeline: \(error)")
            return []
        }
    }

    /// Clear cached timeline for a trip
    func clearCachedTimeline(tripId: Int) {
        guard let dbQueue = dbQueue else { return }

        do {
            try dbQueue.write { db in
                try db.execute(sql: "DELETE FROM cached_timeline WHERE trip_id = ?", arguments: [tripId])
            }
            debugLog("[LocalStorage] ✅ Cleared cached timeline for trip #\(tripId)")
        } catch {
            debugLog("[LocalStorage] Failed to clear cached timeline: \(error)")
        }
    }

    /// Get the age of cached timeline data for a trip (for freshness indicator)
    /// Returns nil if no cached data exists
    func getTimelineCacheAge(tripId: Int) -> TimeInterval? {
        guard let dbQueue = dbQueue else { return nil }

        do {
            return try dbQueue.read { db in
                guard let cachedAtStr = try String.fetchOne(db, sql: """
                    SELECT cached_at FROM cached_timeline WHERE trip_id = ? LIMIT 1
                """, arguments: [tripId]),
                      let cachedAt = ISO8601DateFormatter().date(from: cachedAtStr) else {
                    return nil
                }
                return Date().timeIntervalSince(cachedAt)
            }
        } catch {
            debugLog("[LocalStorage] Failed to get timeline cache age: \(error)")
            return nil
        }
    }

    /// Get the age of cached trip data (for freshness indicator)
    /// Returns nil if trip not cached
    func getTripCacheAge(tripId: Int) -> TimeInterval? {
        guard let dbQueue = dbQueue else { return nil }

        do {
            return try dbQueue.read { db in
                guard let cachedAtStr = try String.fetchOne(db, sql: """
                    SELECT cached_at FROM cached_trips WHERE id = ? LIMIT 1
                """, arguments: [tripId]),
                      let cachedAt = ISO8601DateFormatter().date(from: cachedAtStr) else {
                    return nil
                }
                return Date().timeIntervalSince(cachedAt)
            }
        } catch {
            debugLog("[LocalStorage] Failed to get trip cache age: \(error)")
            return nil
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
                try db.execute(sql: "DELETE FROM cached_contacts")
                try db.execute(sql: "DELETE FROM cached_timeline")
                try db.execute(sql: "DELETE FROM failed_actions")
            }
            debugLog("[LocalStorage] Cleared all data")
        } catch {
            debugLog("[LocalStorage] Failed to clear all data: \(error)")
        }
    }

    // MARK: - Cache TTL/Expiration

    /// Clean up old cached data (called periodically to prevent stale data buildup)
    /// Removes cached trips and timeline entries older than specified days
    func cleanupOldCache(olderThanDays: Int = 30) {
        guard let dbQueue = dbQueue else { return }

        let cutoffDate = Calendar.current.date(byAdding: .day, value: -olderThanDays, to: Date()) ?? Date()
        let cutoffString = ISO8601DateFormatter().string(from: cutoffDate)

        do {
            try dbQueue.write { db in
                // Get IDs of old trips before deleting
                let oldTripIds = try Int.fetchAll(db, sql: """
                    SELECT id FROM cached_trips WHERE cached_at < ?
                """, arguments: [cutoffString])

                if !oldTripIds.isEmpty {
                    // Delete old trips
                    try db.execute(sql: """
                        DELETE FROM cached_trips WHERE cached_at < ?
                    """, arguments: [cutoffString])

                    // Delete associated timeline entries
                    let placeholders = oldTripIds.map { _ in "?" }.joined(separator: ", ")
                    try db.execute(
                        sql: "DELETE FROM cached_timeline WHERE trip_id IN (\(placeholders))",
                        arguments: StatementArguments(oldTripIds)
                    )

                    debugLog("[LocalStorage] 🧹 Cleaned up \(oldTripIds.count) cached trips older than \(olderThanDays) days")
                }
            }
        } catch {
            debugLog("[LocalStorage] Failed to cleanup old cache: \(error)")
        }
    }

    // MARK: - Storage Info (for Privacy View)

    /// Get count of cached trips
    func getCachedTripsCount() -> Int {
        guard let dbQueue = dbQueue else { return 0 }

        do {
            return try dbQueue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM cached_trips") ?? 0
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached trips count: \(error)")
            return 0
        }
    }

    /// Get count of cached activities
    func getCachedActivitiesCount() -> Int {
        guard let dbQueue = dbQueue else { return 0 }

        do {
            return try dbQueue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM cached_activities") ?? 0
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached activities count: \(error)")
            return 0
        }
    }

    /// Get count of cached contacts
    func getCachedContactsCount() -> Int {
        guard let dbQueue = dbQueue else { return 0 }

        do {
            return try dbQueue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM cached_contacts") ?? 0
            }
        } catch {
            debugLog("[LocalStorage] Failed to get cached contacts count: \(error)")
            return 0
        }
    }

    /// Get count of pending offline actions
    func getPendingActionsCount() -> Int {
        guard let dbQueue = dbQueue else { return 0 }

        do {
            return try dbQueue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM pending_actions") ?? 0
            }
        } catch {
            debugLog("[LocalStorage] Failed to get pending actions count: \(error)")
            return 0
        }
    }

    // MARK: - Debug Helpers

    /// Print database schema information for debugging
    func debugSchema() {
        guard let dbQueue = dbQueue else {
            debugLog("[LocalStorage] ⚠️ No database queue available")
            return
        }

        do {
            try dbQueue.read { db in
                debugLog("[LocalStorage] 📊 Database Schema Information")
                debugLog(String(repeating: "=", count: 60))
                debugLog("Schema Version: \(getDatabaseVersion())")
                debugLog("Target Version: \(currentSchemaVersion)")
                debugLog("")

                let tables = ["cached_trips", "cached_activities", "pending_actions", "auth_tokens"]

                for tableName in tables {
                    if try db.tableExists(tableName) {
                        debugLog("Table: \(tableName)")
                        let columns = try db.columns(in: tableName)
                        for column in columns {
                            let nullable = column.isNotNull ? "NOT NULL" : "NULL"
                            debugLog("  - \(column.name): \(column.type) (\(nullable))")
                        }

                        // Get row count
                        let count = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM \(tableName)") ?? 0
                        debugLog("  Rows: \(count)")
                        debugLog("")
                    } else {
                        debugLog("Table: \(tableName) - NOT FOUND")
                        debugLog("")
                    }
                }

                debugLog(String(repeating: "=", count: 60))
            }
        } catch {
            debugLog("[LocalStorage] ⚠️ Failed to inspect schema: \(error)")
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
