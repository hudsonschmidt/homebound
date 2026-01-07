import XCTest
@testable import Homebound

final class TripStatsTests: XCTestCase {

    // MARK: - StatType Tests

    func testStatType_AllCases() {
        let allCases = StatType.allCases

        XCTAssertEqual(allCases.count, 8)
        XCTAssertTrue(allCases.contains(.totalTrips))
        XCTAssertTrue(allCases.contains(.adventureTime))
        XCTAssertTrue(allCases.contains(.longestAdventure))
        XCTAssertTrue(allCases.contains(.activitiesTried))
        XCTAssertTrue(allCases.contains(.thisMonth))
        XCTAssertTrue(allCases.contains(.uniqueLocations))
        XCTAssertTrue(allCases.contains(.mostAdventurousMonth))
        XCTAssertTrue(allCases.contains(.averageTripDuration))
    }

    func testStatType_DisplayName() {
        XCTAssertEqual(StatType.totalTrips.displayName, "Total Trips")
        XCTAssertEqual(StatType.adventureTime.displayName, "Adventure Time")
        XCTAssertEqual(StatType.longestAdventure.displayName, "Longest Trip")
        XCTAssertEqual(StatType.activitiesTried.displayName, "Activities")
    }

    func testStatType_Icon() {
        XCTAssertEqual(StatType.totalTrips.icon, "clock.arrow.trianglehead.counterclockwise.rotate.90")
        XCTAssertEqual(StatType.adventureTime.icon, "hourglass")
        XCTAssertEqual(StatType.longestAdventure.icon, "trophy.fill")
    }

    func testStatType_Color() {
        XCTAssertNotNil(StatType.totalTrips.color)
        XCTAssertNotNil(StatType.adventureTime.color)
    }

    // MARK: - TripStatsCalculator - Total Trips Tests

    func testCalculator_TotalTrips_EmptyArray() {
        let calculator = TripStatsCalculator(trips: [])
        XCTAssertEqual(calculator.totalTrips(), "0")
    }

    func testCalculator_TotalTrips_WithCompletedTrips() {
        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24),
            makeCompletedTrip(id: 2, hoursAgo: 48),
            makeCompletedTrip(id: 3, hoursAgo: 72)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.totalTrips(), "3")
    }

    func testCalculator_TotalTrips_ExcludesNonCompleted() {
        let completedTrip = makeCompletedTrip(id: 1, hoursAgo: 24)
        let activeTrip = TestFixtures.makeTrip(id: 2, status: "active")
        let plannedTrip = TestFixtures.makeTrip(id: 3, status: "planned")

        let calculator = TripStatsCalculator(trips: [completedTrip, activeTrip, plannedTrip])
        XCTAssertEqual(calculator.totalTrips(), "1")
    }

    // MARK: - TripStatsCalculator - Adventure Time Tests

    func testCalculator_TotalAdventureTime_Hours() {
        // 2-hour trip
        let trip = makeCompletedTrip(id: 1, hoursAgo: 24, durationHours: 2)

        let calculator = TripStatsCalculator(trips: [trip])
        XCTAssertEqual(calculator.totalAdventureTime(), "2h")
    }

    func testCalculator_TotalAdventureTime_Days() {
        // 26-hour trip
        let trip = makeCompletedTrip(id: 1, hoursAgo: 48, durationHours: 26)

        let calculator = TripStatsCalculator(trips: [trip])
        XCTAssertEqual(calculator.totalAdventureTime(), "1d 2h")
    }

    func testCalculator_TotalAdventureTime_Minutes() {
        // 30-minute trip
        let startDate = Date().addingTimeInterval(-3600)
        let completedDate = startDate.addingTimeInterval(1800) // 30 minutes

        let trip = Trip(
            id: 1, user_id: 100, title: "Short Trip",
            activity: TestFixtures.makeActivity(),
            start_at: startDate, eta_at: completedDate,
            grace_minutes: 30, location_text: nil,
            location_lat: nil, location_lng: nil, notes: nil,
            status: "completed", completed_at: completedDate,
            last_checkin: nil, created_at: "",
            contact1: nil, contact2: nil, contact3: nil,
            checkin_token: nil, checkout_token: nil
        )

        let calculator = TripStatsCalculator(trips: [trip])
        XCTAssertEqual(calculator.totalAdventureTime(), "30m")
    }

    // MARK: - TripStatsCalculator - Longest Adventure Tests

    func testCalculator_LongestAdventure_ReturnsMaxDuration() {
        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24, durationHours: 2),
            makeCompletedTrip(id: 2, hoursAgo: 48, durationHours: 5),
            makeCompletedTrip(id: 3, hoursAgo: 72, durationHours: 3)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.longestAdventure(), "5h")
    }

    func testCalculator_LongestAdventure_EmptyTrips() {
        let calculator = TripStatsCalculator(trips: [])
        XCTAssertEqual(calculator.longestAdventure(), "0h")
    }

    // MARK: - TripStatsCalculator - Activities Tried Tests

    func testCalculator_ActivitiesTried_CountsUnique() {
        let hikingActivity = TestFixtures.makeActivity(id: 1, name: "Hiking")
        let bikingActivity = TestFixtures.makeActivity(id: 2, name: "Biking")

        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24, activity: hikingActivity),
            makeCompletedTrip(id: 2, hoursAgo: 48, activity: hikingActivity),
            makeCompletedTrip(id: 3, hoursAgo: 72, activity: bikingActivity)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.activitiesTried(), "2")
    }

    // MARK: - TripStatsCalculator - Unique Locations Tests

    func testCalculator_UniqueLocations_CountsUnique() {
        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24, locationText: "Mt. Tamalpais"),
            makeCompletedTrip(id: 2, hoursAgo: 48, locationText: "Mt. Tamalpais"),
            makeCompletedTrip(id: 3, hoursAgo: 72, locationText: "Muir Woods")
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.uniqueLocations(), "2")
    }

    func testCalculator_UniqueLocations_IgnoresEmpty() {
        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24, locationText: "Mt. Tamalpais"),
            makeCompletedTrip(id: 2, hoursAgo: 48, locationText: ""),
            makeCompletedTrip(id: 3, hoursAgo: 72, locationText: nil)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.uniqueLocations(), "1")
    }

    // MARK: - TripStatsCalculator - This Month Tests

    func testCalculator_ThisMonth_FiltersCurrentMonth() {
        let calendar = Calendar.current
        let now = Date()
        let lastMonth = calendar.date(byAdding: .month, value: -1, to: now)!

        let thisMonthTrip = makeCompletedTrip(id: 1, startDate: now.addingTimeInterval(-3600))
        let lastMonthTrip = makeCompletedTrip(id: 2, startDate: lastMonth)

        let calculator = TripStatsCalculator(trips: [thisMonthTrip, lastMonthTrip])
        XCTAssertEqual(calculator.thisMonth(), "1")
    }

    // MARK: - TripStatsCalculator - Most Adventurous Month Tests

    func testCalculator_MostAdventurousMonth_ReturnsMax() {
        // Create trips across different months
        let calendar = Calendar.current
        var components = DateComponents()
        components.year = 2025
        components.day = 15
        components.hour = 12

        // January trips
        components.month = 1
        let jan1 = calendar.date(from: components)!
        let jan2 = calendar.date(from: components)!.addingTimeInterval(86400)

        // February trip
        components.month = 2
        let feb1 = calendar.date(from: components)!

        let trips = [
            makeCompletedTrip(id: 1, startDate: jan1),
            makeCompletedTrip(id: 2, startDate: jan2),
            makeCompletedTrip(id: 3, startDate: feb1)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.mostAdventurousMonth(), "Jan")
    }

    func testCalculator_MostAdventurousMonth_EmptyTrips() {
        let calculator = TripStatsCalculator(trips: [])
        XCTAssertEqual(calculator.mostAdventurousMonth(), "—")
    }

    // MARK: - TripStatsCalculator - Average Trip Duration Tests

    func testCalculator_AverageTripDuration() {
        // Two 2-hour trips = average 2h 0m
        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24, durationHours: 2),
            makeCompletedTrip(id: 2, hoursAgo: 48, durationHours: 2)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.averageTripDuration(), "2h 0m")
    }

    func testCalculator_AverageTripDuration_Empty() {
        let calculator = TripStatsCalculator(trips: [])
        XCTAssertEqual(calculator.averageTripDuration(), "0h")
    }

    // MARK: - TripStatsCalculator - Time-Based Stats Tests

    func testCalculator_EarlyMorningTripsCount() {
        let calendar = Calendar.current
        var earlyComponents = calendar.dateComponents(in: .current, from: Date())
        earlyComponents.hour = 6 // Before 8 AM

        var lateComponents = calendar.dateComponents(in: .current, from: Date())
        lateComponents.hour = 10 // After 8 AM

        let earlyTrip = makeCompletedTrip(id: 1, startDate: calendar.date(from: earlyComponents)!)
        let lateTrip = makeCompletedTrip(id: 2, startDate: calendar.date(from: lateComponents)!)

        let calculator = TripStatsCalculator(trips: [earlyTrip, lateTrip])
        XCTAssertEqual(calculator.earlyMorningTripsCount, 1)
    }

    func testCalculator_NightTripsCount() {
        let calendar = Calendar.current
        var nightComponents = calendar.dateComponents(in: .current, from: Date())
        nightComponents.hour = 21 // After 8 PM (20:00)

        var dayComponents = calendar.dateComponents(in: .current, from: Date())
        dayComponents.hour = 14 // Before 8 PM

        let nightTrip = makeCompletedTrip(id: 1, startDate: calendar.date(from: nightComponents)!)
        let dayTrip = makeCompletedTrip(id: 2, startDate: calendar.date(from: dayComponents)!)

        let calculator = TripStatsCalculator(trips: [nightTrip, dayTrip])
        XCTAssertEqual(calculator.nightTripsCount, 1)
    }

    func testCalculator_WeekendTripsCount() {
        let calendar = Calendar.current

        // Find a Saturday
        var saturday = Date()
        while calendar.component(.weekday, from: saturday) != 7 {
            saturday = calendar.date(byAdding: .day, value: 1, to: saturday)!
        }

        // Find a weekday
        var weekday = Date()
        while calendar.component(.weekday, from: weekday) == 1 || calendar.component(.weekday, from: weekday) == 7 {
            weekday = calendar.date(byAdding: .day, value: 1, to: weekday)!
        }

        let saturdayTrip = makeCompletedTrip(id: 1, startDate: saturday)
        let weekdayTrip = makeCompletedTrip(id: 2, startDate: weekday)

        let calculator = TripStatsCalculator(trips: [saturdayTrip, weekdayTrip])
        XCTAssertEqual(calculator.weekendTripsCount, 1)
    }

    func testCalculator_UniqueMonthsWithTrips() {
        let calendar = Calendar.current
        var components = DateComponents()
        components.year = 2025
        components.day = 15
        components.hour = 12

        // January
        components.month = 1
        let jan = calendar.date(from: components)!

        // February
        components.month = 2
        let feb = calendar.date(from: components)!

        // Also January (should not add to count)
        components.month = 1
        components.day = 20
        let jan2 = calendar.date(from: components)!

        let trips = [
            makeCompletedTrip(id: 1, startDate: jan),
            makeCompletedTrip(id: 2, startDate: feb),
            makeCompletedTrip(id: 3, startDate: jan2)
        ]

        let calculator = TripStatsCalculator(trips: trips)
        XCTAssertEqual(calculator.uniqueMonthsWithTrips, 2)
    }

    // MARK: - Achievement Tests

    func testAchievementDefinition_All_ContainsExpectedCount() {
        let allAchievements = AchievementDefinition.all
        XCTAssertEqual(allAchievements.count, 40)
    }

    func testAchievementDefinition_AchievementsForCategory() {
        let totalTripsAchievements = AchievementDefinition.achievements(for: .totalTrips)
        XCTAssertEqual(totalTripsAchievements.count, 11)

        let adventureTimeAchievements = AchievementDefinition.achievements(for: .adventureTime)
        XCTAssertEqual(adventureTimeAchievements.count, 8)
    }

    func testAchievementDefinition_Requirement() {
        let achievement = AchievementDefinition.all.first!
        XCTAssertEqual(achievement.requirement, "1 trips")
    }

    func testCalculator_HasEarned_True() {
        let trips = (1...5).map { makeCompletedTrip(id: $0, hoursAgo: Double($0) * 24) }
        let calculator = TripStatsCalculator(trips: trips)

        // "First Steps" achievement = 1 trip
        let firstSteps = AchievementDefinition.all.first { $0.id == "first_trip" }!
        XCTAssertTrue(calculator.hasEarned(firstSteps))

        // "Getting Started" achievement = 5 trips
        let gettingStarted = AchievementDefinition.all.first { $0.id == "getting_started" }!
        XCTAssertTrue(calculator.hasEarned(gettingStarted))
    }

    func testCalculator_HasEarned_False() {
        let trips = [makeCompletedTrip(id: 1, hoursAgo: 24)]
        let calculator = TripStatsCalculator(trips: trips)

        // "Explorer" achievement = 10 trips
        let explorer = AchievementDefinition.all.first { $0.id == "explorer" }!
        XCTAssertFalse(calculator.hasEarned(explorer))
    }

    func testCalculator_CurrentValue_TotalTrips() {
        let trips = (1...7).map { makeCompletedTrip(id: $0, hoursAgo: Double($0) * 24) }
        let calculator = TripStatsCalculator(trips: trips)

        let achievement = AchievementDefinition.all.first { $0.category == .totalTrips }!
        XCTAssertEqual(calculator.currentValue(for: achievement), 7)
    }

    func testCalculator_CurrentValue_AdventureTime() {
        // Two 5-hour trips = 10 hours total
        let trips = [
            makeCompletedTrip(id: 1, hoursAgo: 24, durationHours: 5),
            makeCompletedTrip(id: 2, hoursAgo: 48, durationHours: 5)
        ]
        let calculator = TripStatsCalculator(trips: trips)

        let achievement = AchievementDefinition.all.first { $0.category == .adventureTime }!
        XCTAssertEqual(calculator.currentValue(for: achievement), 10)
    }

    func testCalculator_EarnedDate_ReturnsCorrectDate() {
        let trips = (1...5).map { makeCompletedTrip(id: $0, hoursAgo: Double($0) * 24) }
        let calculator = TripStatsCalculator(trips: trips)

        // "Getting Started" = 5 trips
        let achievement = AchievementDefinition.all.first { $0.id == "getting_started" }!
        let earnedDate = calculator.earnedDate(for: achievement)

        XCTAssertNotNil(earnedDate)
    }

    // MARK: - AchievementCategory Tests

    func testAchievementCategory_AllCases() {
        XCTAssertEqual(AchievementCategory.allCases.count, 5)
    }

    func testAchievementCategory_DisplayName() {
        XCTAssertEqual(AchievementCategory.totalTrips.displayName, "Total Trips")
        XCTAssertEqual(AchievementCategory.adventureTime.displayName, "Adventure Time")
        XCTAssertEqual(AchievementCategory.activitiesTried.displayName, "Activities")
        XCTAssertEqual(AchievementCategory.locations.displayName, "Locations")
        XCTAssertEqual(AchievementCategory.timeBased.displayName, "Time Patterns")
    }

    // MARK: - Helper Methods

    private func makeCompletedTrip(
        id: Int,
        hoursAgo: Double = 24,
        durationHours: Double = 2,
        activity: Activity? = nil,
        locationText: String? = "Test Location",
        startDate: Date? = nil
    ) -> Trip {
        let start = startDate ?? Date().addingTimeInterval(-hoursAgo * 3600)
        let completed = start.addingTimeInterval(durationHours * 3600)

        return Trip(
            id: id, user_id: 100, title: "Trip \(id)",
            activity: activity ?? TestFixtures.makeActivity(),
            start_at: start, eta_at: completed,
            grace_minutes: 30, location_text: locationText,
            location_lat: 37.9235, location_lng: -122.5965, notes: nil,
            status: "completed", completed_at: completed,
            last_checkin: nil, created_at: "",
            contact1: nil, contact2: nil, contact3: nil,
            checkin_token: nil, checkout_token: nil
        )
    }
}
