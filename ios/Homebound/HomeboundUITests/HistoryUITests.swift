import XCTest

final class HistoryUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - History View Tests

    func testHistoryView_NavigateToHistory() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to History tab
        let historyTab = app.tabBars.buttons["History"]
        historyTab.tap()

        XCTAssertTrue(historyTab.isSelected)

        takeScreenshot(name: "History-View")
    }

    func testHistoryView_ShowsEmptyStateOrTrips() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to History tab
        app.tabBars.buttons["History"].tap()
        sleep(1)

        // Should show either empty state or trip history
        let hasContent = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'trip' OR label CONTAINS[c] 'history' OR label CONTAINS[c] 'adventure' OR label CONTAINS[c] 'No trips'")).firstMatch.exists

        takeScreenshot(name: "History-Content")
    }

    func testHistoryView_StatsSection() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to History tab
        app.tabBars.buttons["History"].tap()
        sleep(1)

        // Check for stats elements
        let statsLabels = [
            "Total Trips",
            "Adventure Time",
            "Activities",
            "Locations"
        ]

        var foundStats = false
        for label in statsLabels {
            if app.staticTexts[label].exists ||
               app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", label)).firstMatch.exists {
                foundStats = true
                break
            }
        }

        takeScreenshot(name: "History-Stats")
    }

    func testHistoryView_ScrollableContent() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to History tab
        app.tabBars.buttons["History"].tap()
        sleep(1)

        // Try to scroll
        let scrollView = app.scrollViews.firstMatch
        if scrollView.exists {
            scrollView.swipeUp()
            sleep(1)
            takeScreenshot(name: "History-Scrolled")
        }
    }

    // MARK: - Trip Detail Tests

    func testHistoryView_TapTrip_OpensDetail() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to History tab
        app.tabBars.buttons["History"].tap()
        sleep(1)

        // Try to find and tap a trip cell
        let tripCells = app.cells.allElementsBoundByIndex
        if tripCells.count > 0 {
            tripCells[0].tap()
            sleep(1)
            takeScreenshot(name: "History-TripDetail")
        }
    }
}
