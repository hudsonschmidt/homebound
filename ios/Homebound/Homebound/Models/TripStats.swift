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
        case .totalTrips: return "map.fill"
        case .adventureTime: return "clock.fill"
        case .longestAdventure: return "trophy.fill"
        case .activitiesTried: return "star.fill"
        case .thisMonth: return "calendar"
        case .uniqueLocations: return "location.fill"
        case .mostAdventurousMonth: return "chart.bar.fill"
        case .averageTripDuration: return "speedometer"
        }
    }

    var color: Color {
        switch self {
        case .totalTrips: return Color.hbBrand
        case .adventureTime: return .orange
        case .longestAdventure: return .yellow
        case .activitiesTried: return Color.hbTeal
        case .thisMonth: return .green
        case .uniqueLocations: return .red
        case .mostAdventurousMonth: return .blue
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
        let uniqueActivities = Set(trips.map { $0.activity_type })
        return "\(uniqueActivities.count)"
    }

    func thisMonth() -> String {
        let calendar = Calendar.current
        let now = Date()

        let thisMonthTrips = trips.filter { trip in
            calendar.isDate(trip.start_at, equalTo: now, toGranularity: .month)
        }

        return "\(thisMonthTrips.count)"
    }

    func uniqueLocations() -> String {
        let locations = trips.compactMap { $0.location_text }.filter { !$0.isEmpty }
        let uniqueLocations = Set(locations)
        return "\(uniqueLocations.count)"
    }

    func mostAdventurousMonth() -> String {
        guard !trips.isEmpty else { return "—" }

        let calendar = Calendar.current
        let monthCounts = Dictionary(grouping: trips) { trip in
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

    // MARK: - Achievement Badges

    func achievementBadge(for statType: StatType) -> String? {
        switch statType {
        case .totalTrips:
            let count = trips.count
            if count >= 100 { return "💯" }
            if count >= 50 { return "🌟" }
            if count >= 10 { return "🏆" }
        case .adventureTime:
            let totalSeconds = trips.reduce(0.0) { total, trip in
                total + trip.eta_at.timeIntervalSince(trip.start_at)
            }
            let hours = Int(totalSeconds) / 3600
            if hours >= 500 { return "⭐️" }
            if hours >= 100 { return "🎖" }
            if hours >= 50 { return "🏅" }
        case .activitiesTried:
            let count = Set(trips.map { $0.activity_type }).count
            if count >= 10 { return "🌈" }
            if count >= 5 { return "✨" }
        default:
            break
        }
        return nil
    }
}
