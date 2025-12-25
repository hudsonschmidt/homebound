import SwiftUI
import Foundation

// MARK: - Stat Type Definition
enum StatType: String, CaseIterable, Codable {
    case totalTrips = "total_trips"
    case adventureTime = "adventure_time"
    case longestAdventure = "longest_adventure"
    case activitiesTried = "activities_tried"
    case thisMonth = "this_month"
    case uniqueLocations = "unique_locations"
    case mostAdventurousMonth = "most_adventurous_month"
    case averageTripDuration = "average_trip_duration"

    var displayName: String {
        switch self {
        case .totalTrips: return "Total Trips"
        case .adventureTime: return "Adventure Time"
        case .longestAdventure: return "Longest Trip"
        case .activitiesTried: return "Activities"
        case .thisMonth: return "This Month"
        case .uniqueLocations: return "Locations"
        case .mostAdventurousMonth: return "Best Month"
        case .averageTripDuration: return "Avg Duration"
        }
    }

    var icon: String {
        switch self {
        case .totalTrips: return "clock.arrow.trianglehead.counterclockwise.rotate.90"
        case .adventureTime: return "hourglass"
        case .longestAdventure: return "trophy.fill"
        case .activitiesTried: return "chart.bar.fill"
        case .thisMonth: return "calendar"
        case .uniqueLocations: return "map.fill"
        case .mostAdventurousMonth: return "medal.fill" 
        case .averageTripDuration: return "stopwatch.fill"
        }
    }

    var color: Color {
        switch self {
        case .totalTrips: return .red
        case .adventureTime: return .orange
        case .longestAdventure: return .yellow
        case .activitiesTried: return .green
        case .thisMonth: return .blue
        case .uniqueLocations: return .cyan
        case .mostAdventurousMonth: return .purple
        case .averageTripDuration: return .pink
        }
    }
}

// MARK: - Stats Preferences
struct StatsPreferences: Codable {
    var selectedStats: [StatType]

    static let defaultStats: [StatType] = [
        .totalTrips,
        .adventureTime,
        .thisMonth,
        .activitiesTried
    ]

    static let userDefaultsKey = "adventure_stats_preferences"

    static func load() -> StatsPreferences {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let preferences = try? JSONDecoder().decode(StatsPreferences.self, from: data) else {
            return StatsPreferences(selectedStats: defaultStats)
        }
        return preferences
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: StatsPreferences.userDefaultsKey)
        }
    }
}

// MARK: - Achievement Category
enum AchievementCategory: String, CaseIterable {
    case totalTrips
    case adventureTime
    case activitiesTried
    case locations
    case timeBased

    var displayName: String {
        switch self {
        case .totalTrips: return "Total Trips"
        case .adventureTime: return "Adventure Time"
        case .activitiesTried: return "Activities"
        case .locations: return "Locations"
        case .timeBased: return "Time Patterns"
        }
    }

    var icon: String {
        switch self {
        case .totalTrips: return "figure.walk"
        case .adventureTime: return "hourglass"
        case .activitiesTried: return "star.fill"
        case .locations: return "map.fill"
        case .timeBased: return "clock.fill"
        }
    }

    var color: Color {
        switch self {
        case .totalTrips: return .red
        case .adventureTime: return .orange
        case .activitiesTried: return .green
        case .locations: return .teal
        case .timeBased: return .purple
        }
    }
}

// MARK: - Achievement Definition
struct AchievementDefinition: Identifiable {
    let id: String
    let sfSymbol: String
    let title: String
    let description: String
    let category: AchievementCategory
    let threshold: Int
    let unit: String

    var requirement: String {
        "\(threshold) \(unit)"
    }

    static let all: [AchievementDefinition] = [
        // Total Trips (11 achievements)
        AchievementDefinition(
            id: "first_trip", sfSymbol: "flag.fill", title: "First Steps",
            description: "Complete 1 trip",
            category: .totalTrips, threshold: 1, unit: "trips"
        ),
        AchievementDefinition(
            id: "getting_started", sfSymbol: "figure.walk", title: "Getting Started",
            description: "Complete 5 trips",
            category: .totalTrips, threshold: 5, unit: "trips"
        ),
        AchievementDefinition(
            id: "explorer", sfSymbol: "figure.hiking", title: "Explorer",
            description: "Complete 10 trips",
            category: .totalTrips, threshold: 10, unit: "trips"
        ),
        AchievementDefinition(
            id: "pathfinder", sfSymbol: "point.bottomleft.forward.to.point.topright.scurvepath.fill", title: "Pathfinder",
            description: "Complete 25 trips",
            category: .totalTrips, threshold: 25, unit: "trips"
        ),
        AchievementDefinition(
            id: "adventurer", sfSymbol: "mountain.2.fill", title: "Adventurer",
            description: "Complete 50 trips",
            category: .totalTrips, threshold: 50, unit: "trips"
        ),
        AchievementDefinition(
            id: "century", sfSymbol: "trophy.fill", title: "Century",
            description: "Complete 100 trips",
            category: .totalTrips, threshold: 100, unit: "trips"
        ),
        AchievementDefinition(
            id: "dedicated", sfSymbol: "medal.fill", title: "Dedicated",
            description: "Complete 150 trips",
            category: .totalTrips, threshold: 150, unit: "trips"
        ),
        AchievementDefinition(
            id: "committed", sfSymbol: "star.circle.fill", title: "Committed",
            description: "Complete 200 trips",
            category: .totalTrips, threshold: 200, unit: "trips"
        ),
        AchievementDefinition(
            id: "elite", sfSymbol: "rosette", title: "Elite",
            description: "Complete 250 trips",
            category: .totalTrips, threshold: 250, unit: "trips"
        ),
        AchievementDefinition(
            id: "master", sfSymbol: "crown.fill", title: "Master",
            description: "Complete 500 trips",
            category: .totalTrips, threshold: 500, unit: "trips"
        ),
        AchievementDefinition(
            id: "legendary", sfSymbol: "sparkle.magnifyingglass", title: "Legendary",
            description: "Complete 1000 trips",
            category: .totalTrips, threshold: 1000, unit: "trips"
        ),

        // Adventure Time (8 achievements)
        AchievementDefinition(
            id: "first_hour", sfSymbol: "clock", title: "First Hour",
            description: "1 hour",
            category: .adventureTime, threshold: 1, unit: "hours"
        ),
        AchievementDefinition(
            id: "getting_outdoors", sfSymbol: "clock.fill", title: "Getting Out",
            description: "10 hours",
            category: .adventureTime, threshold: 10, unit: "hours"
        ),
        AchievementDefinition(
            id: "timekeeper", sfSymbol: "timer", title: "Time Keeper",
            description: "50 hours",
            category: .adventureTime, threshold: 50, unit: "hours"
        ),
        AchievementDefinition(
            id: "timemaster", sfSymbol: "hourglass", title: "Time Master",
            description: "100 hours",
            category: .adventureTime, threshold: 100, unit: "hours"
        ),
        AchievementDefinition(
            id: "time_devotee", sfSymbol: "hourglass.circle.fill", title: "Devotee",
            description: "250 hours",
            category: .adventureTime, threshold: 250, unit: "hours"
        ),
        AchievementDefinition(
            id: "time_legend", sfSymbol: "hourglass.badge.plus", title: "Time Legend",
            description: "500 hours",
            category: .adventureTime, threshold: 500, unit: "hours"
        ),
        AchievementDefinition(
            id: "time_titan", sfSymbol: "star.fill", title: "Time Titan",
            description: "1000 hours",
            category: .adventureTime, threshold: 1000, unit: "hours"
        ),
        AchievementDefinition(
            id: "eternal", sfSymbol: "infinity", title: "Eternal",
            description: "2500 hours",
            category: .adventureTime, threshold: 2500, unit: "hours"
        ),

        // Activities (6 achievements)
        AchievementDefinition(
            id: "first_activity", sfSymbol: "leaf", title: "Starter",
            description: "Try 1 activity type",
            category: .activitiesTried, threshold: 1, unit: "activities"
        ),
        AchievementDefinition(
            id: "curious", sfSymbol: "sparkle", title: "Curious",
            description: "Try 3 activity types",
            category: .activitiesTried, threshold: 3, unit: "activities"
        ),
        AchievementDefinition(
            id: "diverse", sfSymbol: "star.fill", title: "Diverse",
            description: "Try 5 activity types",
            category: .activitiesTried, threshold: 5, unit: "activities"
        ),
        AchievementDefinition(
            id: "variety", sfSymbol: "sparkles", title: "Variety",
            description: "Try 10 activity types",
            category: .activitiesTried, threshold: 10, unit: "activities"
        ),
        AchievementDefinition(
            id: "well_rounded", sfSymbol: "circle.hexagongrid.fill", title: "Well Rounded",
            description: "Try 15 activity types",
            category: .activitiesTried, threshold: 15, unit: "activities"
        ),
        AchievementDefinition(
            id: "jack_of_all", sfSymbol: "seal.fill", title: "Jack of All",
            description: "Try 20 activity types",
            category: .activitiesTried, threshold: 20, unit: "activities"
        ),

        // Locations (7 achievements)
        AchievementDefinition(
            id: "first_place", sfSymbol: "mappin", title: "First Place",
            description: "Visit 1 location",
            category: .locations, threshold: 1, unit: "locations"
        ),
        AchievementDefinition(
            id: "local", sfSymbol: "mappin.circle.fill", title: "Local",
            description: "Visit 5 locations",
            category: .locations, threshold: 5, unit: "locations"
        ),
        AchievementDefinition(
            id: "explorer_loc", sfSymbol: "map", title: "Explorer",
            description: "Visit 10 locations",
            category: .locations, threshold: 10, unit: "locations"
        ),
        AchievementDefinition(
            id: "wanderer", sfSymbol: "map.fill", title: "Wanderer",
            description: "Visit 25 locations",
            category: .locations, threshold: 25, unit: "locations"
        ),
        AchievementDefinition(
            id: "traveler", sfSymbol: "airplane", title: "Traveler",
            description: "Visit 50 locations",
            category: .locations, threshold: 50, unit: "locations"
        ),
        AchievementDefinition(
            id: "globetrotter", sfSymbol: "globe.americas.fill", title: "Globetrotter",
            description: "Visit 100 locations",
            category: .locations, threshold: 100, unit: "locations"
        ),
        AchievementDefinition(
            id: "world_explorer", sfSymbol: "globe", title: "World Explorer",
            description: "Visit 250 locations",
            category: .locations, threshold: 250, unit: "locations"
        ),

        // Time-Based Patterns (8 achievements)
        AchievementDefinition(
            id: "earlybird", sfSymbol: "sunrise.fill", title: "Early Bird",
            description: "5 trips before 8 AM",
            category: .timeBased, threshold: 5, unit: "trips"
        ),
        AchievementDefinition(
            id: "earlybird_pro", sfSymbol: "sunrise.circle.fill", title: "Dawn Patrol",
            description: "25 trips before 8 AM",
            category: .timeBased, threshold: 25, unit: "trips"
        ),
        AchievementDefinition(
            id: "nightowl", sfSymbol: "moon.stars.fill", title: "Night Owl",
            description: "5 trips after 8 PM",
            category: .timeBased, threshold: 5, unit: "trips"
        ),
        AchievementDefinition(
            id: "nightowl_pro", sfSymbol: "moon.circle.fill", title: "Nocturnal",
            description: "25 trips after 8 PM",
            category: .timeBased, threshold: 25, unit: "trips"
        ),
        AchievementDefinition(
            id: "weekendwarrior", sfSymbol: "sun.max.fill", title: "Weekender",
            description: "10 weekend trips",
            category: .timeBased, threshold: 10, unit: "trips"
        ),
        AchievementDefinition(
            id: "weekendwarrior_pro", sfSymbol: "sun.max.circle.fill", title: "Weekend Pro",
            description: "50 weekend trips",
            category: .timeBased, threshold: 50, unit: "trips"
        ),
        AchievementDefinition(
            id: "consistent", sfSymbol: "calendar", title: "Consistent",
            description: "Trips in 5 months",
            category: .timeBased, threshold: 5, unit: "months"
        ),
        AchievementDefinition(
            id: "year_round", sfSymbol: "calendar.badge.checkmark", title: "Year Round",
            description: "Trips in 12 months",
            category: .timeBased, threshold: 12, unit: "months"
        ),
    ]

    static func achievements(for category: AchievementCategory) -> [AchievementDefinition] {
        all.filter { $0.category == category }
    }
}

// MARK: - Stats Calculator
struct TripStatsCalculator {
    let trips: [Trip]

    // Helper: Filter only completed trips with valid completed_at
    var completedTrips: [Trip] {
        trips.filter { trip in
            trip.status == "completed" && trip.completed_at != nil
        }
    }

    // MARK: - Individual Stat Calculations

    func totalTrips() -> String {
        return "\(completedTrips.count)"
    }

    func totalAdventureTime() -> String {
        let totalSeconds = completedTrips.reduce(0.0) { total, trip in
            guard let completedAt = trip.completed_at else { return total }
            return total + completedAt.timeIntervalSince(trip.start_at)
        }
        let hours = Int(totalSeconds) / 3600
        let days = hours / 24

        if days > 0 {
            return "\(days)d \(hours % 24)h"
        } else if hours > 0 {
            return "\(hours)h"
        } else {
            return "\(Int(totalSeconds) / 60)m"
        }
    }

    func longestAdventure() -> String {
        guard !completedTrips.isEmpty else { return "0h" }

        let longest = completedTrips.max { trip1, trip2 in
            guard let completed1 = trip1.completed_at, let completed2 = trip2.completed_at else {
                return false
            }
            let duration1 = completed1.timeIntervalSince(trip1.start_at)
            let duration2 = completed2.timeIntervalSince(trip2.start_at)
            return duration1 < duration2
        }

        guard let trip = longest, let completedAt = trip.completed_at else { return "0h" }

        let duration = completedAt.timeIntervalSince(trip.start_at)
        let hours = Int(duration) / 3600
        let days = hours / 24

        if days > 0 {
            return "\(days)d \(hours % 24)h"
        } else {
            return "\(hours)h"
        }
    }

    func activitiesTried() -> String {
        let uniqueActivities = Set(completedTrips.map { $0.activity_type })
        return "\(uniqueActivities.count)"
    }

    func thisMonth() -> String {
        let calendar = Calendar.current
        let now = Date()

        let thisMonthTrips = completedTrips.filter { trip in
            calendar.isDate(trip.start_at, equalTo: now, toGranularity: .month)
        }

        return "\(thisMonthTrips.count)"
    }

    func uniqueLocations() -> String {
        let locations = completedTrips.compactMap { $0.location_text }.filter { !$0.isEmpty }
        let uniqueLocations = Set(locations)
        return "\(uniqueLocations.count)"
    }

    func mostAdventurousMonth() -> String {
        guard !completedTrips.isEmpty else { return "—" }

        let calendar = Calendar.current
        let monthCounts = Dictionary(grouping: completedTrips) { trip in
            calendar.component(.month, from: trip.start_at)
        }.mapValues { $0.count }

        guard let maxMonth = monthCounts.max(by: { $0.value < $1.value }) else {
            return "—"
        }

        let monthName = calendar.monthSymbols[maxMonth.key - 1]
        return String(monthName.prefix(3))
    }

    func averageTripDuration() -> String {
        guard !completedTrips.isEmpty else { return "0h" }

        let totalSeconds = completedTrips.reduce(0.0) { total, trip in
            guard let completedAt = trip.completed_at else { return total }
            return total + completedAt.timeIntervalSince(trip.start_at)
        }

        let avgSeconds = totalSeconds / Double(completedTrips.count)
        let hours = Int(avgSeconds) / 3600
        let minutes = (Int(avgSeconds) % 3600) / 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }

    // MARK: - Get Value for Stat Type

    func value(for statType: StatType) -> String {
        switch statType {
        case .totalTrips: return totalTrips()
        case .adventureTime: return totalAdventureTime()
        case .longestAdventure: return longestAdventure()
        case .activitiesTried: return activitiesTried()
        case .thisMonth: return thisMonth()
        case .uniqueLocations: return uniqueLocations()
        case .mostAdventurousMonth: return mostAdventurousMonth()
        case .averageTripDuration: return averageTripDuration()
        }
    }

    // MARK: - Achievement Checking

    func hasEarned(_ achievement: AchievementDefinition) -> Bool {
        // Debug mode: unlock all achievements
        if UserDefaults.standard.bool(forKey: "debugUnlockAllAchievements") {
            return true
        }
        return currentValue(for: achievement) >= achievement.threshold
    }

    func currentValue(for achievement: AchievementDefinition) -> Int {
        switch achievement.category {
        case .totalTrips:
            return completedTrips.count
        case .adventureTime:
            return totalAdventureHours
        case .activitiesTried:
            return uniqueActivityCount
        case .locations:
            return uniqueLocationCount
        case .timeBased:
            return timeBasedValue(for: achievement)
        }
    }

    private func timeBasedValue(for achievement: AchievementDefinition) -> Int {
        switch achievement.id {
        case "earlybird", "earlybird_pro": return earlyMorningTripsCount
        case "nightowl", "nightowl_pro": return nightTripsCount
        case "weekendwarrior", "weekendwarrior_pro": return weekendTripsCount
        case "consistent", "year_round": return uniqueMonthsWithTrips
        default: return 0
        }
    }

    var earnedAchievementsCount: Int {
        AchievementDefinition.all.filter { hasEarned($0) }.count
    }

    func earnedCount(for category: AchievementCategory) -> Int {
        AchievementDefinition.achievements(for: category).filter { hasEarned($0) }.count
    }

    func earnedDate(for achievement: AchievementDefinition) -> Date? {
        guard hasEarned(achievement) else { return nil }
        // Debug mode: return current date
        if UserDefaults.standard.bool(forKey: "debugUnlockAllAchievements") {
            return Date()
        }
        // Return the date of the Nth completed trip that met the threshold
        let sortedDates = completedTrips.compactMap { $0.completed_at }.sorted()
        let index = min(achievement.threshold - 1, sortedDates.count - 1)
        return index >= 0 ? sortedDates[index] : nil
    }

    // MARK: - Helper Properties for Achievements View

    var totalAdventureHours: Int {
        let totalSeconds = completedTrips.reduce(0.0) { total, trip in
            guard let completedAt = trip.completed_at else { return total }
            return total + completedAt.timeIntervalSince(trip.start_at)
        }
        return Int(totalSeconds) / 3600
    }

    var uniqueActivityCount: Int {
        Set(completedTrips.map { $0.activity_type }).count
    }

    var uniqueLocationCount: Int {
        let locations = completedTrips.compactMap { $0.location_text }.filter { !$0.isEmpty }
        return Set(locations).count
    }

    // MARK: - Time-Based Stats

    /// Trips starting before 8 AM
    var earlyMorningTripsCount: Int {
        completedTrips.filter { trip in
            let hour = Calendar.current.component(.hour, from: trip.start_at)
            return hour < 8
        }.count
    }

    /// Trips starting after 8 PM
    var nightTripsCount: Int {
        completedTrips.filter { trip in
            let hour = Calendar.current.component(.hour, from: trip.start_at)
            return hour >= 20
        }.count
    }

    /// Trips on Saturday or Sunday
    var weekendTripsCount: Int {
        completedTrips.filter { trip in
            let weekday = Calendar.current.component(.weekday, from: trip.start_at)
            return weekday == 1 || weekday == 7 // Sunday = 1, Saturday = 7
        }.count
    }

    /// Count of unique months with completed trips
    var uniqueMonthsWithTrips: Int {
        let calendar = Calendar.current
        let monthYears = completedTrips.map { trip -> String in
            let year = calendar.component(.year, from: trip.start_at)
            let month = calendar.component(.month, from: trip.start_at)
            return "\(year)-\(month)"
        }
        return Set(monthYears).count
    }
}
