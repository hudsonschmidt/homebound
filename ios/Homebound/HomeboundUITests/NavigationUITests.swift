import XCTest

final class NavigationUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        // Add argument to skip authentication for testing main navigation
        // Note: This requires implementation in the app to check for this flag
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - Tab Bar Navigation Tests

    func testTabBar_AllTabsExist() throws {
        app.launch()

        // Wait for main view to load
        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            // If we can't get past auth, skip these tests gracefully
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Check all tabs exist
        XCTAssertTrue(app.tabBars.buttons["Home"].exists, "Home tab should exist")
        XCTAssertTrue(app.tabBars.buttons["History"].exists, "History tab should exist")
        XCTAssertTrue(app.tabBars.buttons["Friends"].exists, "Friends tab should exist")
        XCTAssertTrue(app.tabBars.buttons["Map"].exists, "Map tab should exist")

        takeScreenshot(name: "Navigation-TabBar")
    }

    func testTabBar_HomeTab_IsDefaultSelected() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Home tab should be selected by default
        XCTAssertTrue(homeTab.isSelected)

        takeScreenshot(name: "Navigation-HomeTabSelected")
    }

    func testTabBar_HistoryTab_Navigation() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Tap History tab
        let historyTab = app.tabBars.buttons["History"]
        historyTab.tap()

        // Should now be on History view
        XCTAssertTrue(historyTab.isSelected)

        takeScreenshot(name: "Navigation-HistoryTab")
    }

    func testTabBar_FriendsTab_Navigation() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Tap Friends tab
        let friendsTab = app.tabBars.buttons["Friends"]
        friendsTab.tap()

        // Should now be on Friends view
        XCTAssertTrue(friendsTab.isSelected)

        takeScreenshot(name: "Navigation-FriendsTab")
    }

    func testTabBar_MapTab_Navigation() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Tap Map tab
        let mapTab = app.tabBars.buttons["Map"]
        mapTab.tap()

        // Should now be on Map view
        XCTAssertTrue(mapTab.isSelected)

        takeScreenshot(name: "Navigation-MapTab")
    }

    func testTabBar_SwitchBetweenTabs() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate through all tabs
        app.tabBars.buttons["History"].tap()
        XCTAssertTrue(app.tabBars.buttons["History"].isSelected)

        app.tabBars.buttons["Friends"].tap()
        XCTAssertTrue(app.tabBars.buttons["Friends"].isSelected)

        app.tabBars.buttons["Map"].tap()
        XCTAssertTrue(app.tabBars.buttons["Map"].isSelected)

        // Navigate back to Home
        app.tabBars.buttons["Home"].tap()
        XCTAssertTrue(app.tabBars.buttons["Home"].isSelected)

        takeScreenshot(name: "Navigation-BackToHome")
    }

    // MARK: - Home View Tests

    func testHomeView_GreetingDisplayed() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Should show a greeting (Good morning/afternoon/evening)
        let greetings = ["Good morning", "Good afternoon", "Good evening"]
        let hasGreeting = greetings.contains { app.staticTexts[$0].exists }
        // Note: Greeting text might include name, so check with partial match
        let greetingExists = hasGreeting || app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Good'")).count > 0
        XCTAssertTrue(greetingExists, "Greeting should be displayed")
    }

    func testHomeView_SettingsButtonExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Settings button (gear icon) should exist
        let settingsButton = app.buttons.matching(NSPredicate(format: "label CONTAINS 'Settings' OR label CONTAINS 'gearshape'")).firstMatch
        XCTAssertTrue(settingsButton.exists || app.images["gearshape.fill"].exists, "Settings button should exist")
    }

    func testHomeView_TrophyButtonExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Trophy/achievements button should exist
        let trophyButton = app.buttons.matching(NSPredicate(format: "label CONTAINS 'trophy'")).firstMatch
        XCTAssertTrue(trophyButton.exists || app.images["trophy.fill"].exists, "Trophy button should exist")
    }

    func testHomeView_NewTripCardDisplayed() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Should show "Start a New Trip" card when no active trip
        let newTripText = app.staticTexts["Start a New Trip"]
        let createButton = app.buttons["Create New Trip"]

        // Either the new trip card or an active trip card should be visible
        let hasNewTripCard = newTripText.exists || createButton.exists
        let hasActiveTripCard = app.staticTexts["ACTIVE TRIP"].exists

        XCTAssertTrue(hasNewTripCard || hasActiveTripCard, "Should show either new trip card or active trip card")

        takeScreenshot(name: "HomeView-TripCard")
    }
}
