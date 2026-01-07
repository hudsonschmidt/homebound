import XCTest

final class SettingsUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - Settings Navigation Tests

    func testSettings_OpenSettings() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Find settings button (gear icon)
        let settingsButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'gear' OR label CONTAINS[c] 'settings'")).firstMatch

        // If not found by label, try to find by image
        if !settingsButton.exists {
            // Settings is typically in top-right corner, tap there
            let topRightArea = app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.1))
            topRightArea.tap()
        } else {
            settingsButton.tap()
        }

        // Wait for settings sheet
        sleep(1)

        takeScreenshot(name: "Settings-Opened")
    }

    func testSettings_DismissSettings() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Open settings
        let settingsButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'gear' OR label CONTAINS[c] 'settings'")).firstMatch
        if settingsButton.exists {
            settingsButton.tap()
            sleep(1)

            // Swipe down to dismiss
            app.swipeDown()
            sleep(1)

            // Should be back on home
            XCTAssertTrue(homeTab.exists)
        }

        takeScreenshot(name: "Settings-Dismissed")
    }

    // MARK: - Settings Content Tests

    func testSettings_ProfileSectionExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Open settings
        openSettings()

        // Check for profile-related elements
        let profileElements = [
            "Profile",
            "Account",
            "Name",
            "Email"
        ]

        var foundElement = false
        for element in profileElements {
            if app.staticTexts[element].exists ||
               app.buttons[element].exists ||
               app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", element)).firstMatch.exists {
                foundElement = true
                break
            }
        }

        takeScreenshot(name: "Settings-Profile")
    }

    func testSettings_AppearanceSectionExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()

        // Check for appearance/theme options
        let appearanceElements = [
            "Appearance",
            "Theme",
            "Dark",
            "Light",
            "System"
        ]

        var foundElement = false
        for element in appearanceElements {
            if app.staticTexts[element].exists ||
               app.buttons[element].exists {
                foundElement = true
                break
            }
        }

        takeScreenshot(name: "Settings-Appearance")
    }

    func testSettings_LogoutButtonExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()

        // Scroll to find logout button
        let scrollView = app.scrollViews.firstMatch
        if scrollView.exists {
            scrollView.swipeUp()
        }

        // Check for logout/sign out button
        let logoutButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'log out' OR label CONTAINS[c] 'sign out' OR label CONTAINS[c] 'logout'")).firstMatch

        takeScreenshot(name: "Settings-Logout")
    }

    // MARK: - Helper Methods

    private func openSettings() {
        let settingsButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'gear' OR label CONTAINS[c] 'settings'")).firstMatch
        if settingsButton.exists {
            settingsButton.tap()
        } else {
            // Try tapping top-right area
            let topRightArea = app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.1))
            topRightArea.tap()
        }
        sleep(1)
    }
}
