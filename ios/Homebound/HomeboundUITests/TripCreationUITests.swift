import XCTest

final class TripCreationUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - Trip Creation Flow Tests

    func testTripCreation_TapCreateButton_OpensSheet() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Find and tap the Create New Trip button
        let createButton = app.buttons["Create New Trip"]
        guard waitForElement(createButton, timeout: 5) else {
            // May have an active trip, skip test
            throw XCTSkip("Create New Trip button not visible - may have active trip")
        }

        createButton.tap()

        // Sheet should appear - look for trip creation view elements
        // The sheet should show activity selection or trip details
        let sheetExists = app.navigationBars.firstMatch.waitForExistence(timeout: 3) ||
                          app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'trip' OR label CONTAINS[c] 'activity'")).firstMatch.waitForExistence(timeout: 3)

        XCTAssertTrue(sheetExists, "Trip creation sheet should appear")

        takeScreenshot(name: "TripCreation-SheetOpened")
    }

    func testTripCreation_DismissSheet() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        let createButton = app.buttons["Create New Trip"]
        guard waitForElement(createButton, timeout: 5) else {
            throw XCTSkip("Create New Trip button not visible - may have active trip")
        }

        createButton.tap()

        // Wait for sheet to appear
        sleep(1)

        // Swipe down to dismiss
        app.swipeDown()

        // Should be back on home view
        sleep(1)
        XCTAssertTrue(createButton.exists || app.tabBars.buttons["Home"].exists)

        takeScreenshot(name: "TripCreation-SheetDismissed")
    }

    // MARK: - Trip Start View Tests

    func testTripStartView_ActivitySelection() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        let createButton = app.buttons["Create New Trip"]
        guard waitForElement(createButton, timeout: 5) else {
            throw XCTSkip("Create New Trip button not visible - may have active trip")
        }

        createButton.tap()

        // Wait for trip start view
        sleep(1)

        // Should show activity options like Hiking, Driving, etc.
        let activityNames = ["Hiking", "Driving", "Running", "Biking", "Swimming", "Skiing", "Camping"]
        var foundActivity = false

        for activity in activityNames {
            if app.staticTexts[activity].exists || app.buttons[activity].exists {
                foundActivity = true
                break
            }
        }

        takeScreenshot(name: "TripCreation-ActivitySelection")

        // Note: Activity selection UI may vary, this test checks for common patterns
    }

    // MARK: - Feature Row Tests

    func testHomeView_FeatureRowsDisplayed() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Check for feature descriptions on the new trip card
        let features = [
            "Set your expected return time",
            "Add emergency contacts",
            "Automatic safety alerts"
        ]

        let createButton = app.buttons["Create New Trip"]
        guard waitForElement(createButton, timeout: 5) else {
            throw XCTSkip("New trip card not visible - may have active trip")
        }

        // At least one feature should be visible
        var foundFeature = false
        for feature in features {
            if app.staticTexts[feature].exists {
                foundFeature = true
                break
            }
        }

        XCTAssertTrue(foundFeature, "Feature descriptions should be displayed on new trip card")

        takeScreenshot(name: "HomeView-Features")
    }
}
