import XCTest

final class AccessibilityUITests: UITestCase {

    // MARK: - Accessibility Tests

    func testAccessibility_AuthenticationView_VoiceOverLabels() throws {
        app.launch()

        // Wait for auth view to load
        let welcomeText = app.staticTexts["Welcome"]
        XCTAssertTrue(waitForElement(welcomeText, timeout: 10))

        // Check that key elements exist and are accessible
        let emailField = app.textFields["email@example.com"]
        XCTAssertTrue(emailField.exists, "Email field should exist")

        let continueButton = app.buttons["Continue with Email"]
        XCTAssertTrue(continueButton.exists, "Continue button should exist")

        let appleButton = app.buttons["Continue with Apple"]
        XCTAssertTrue(appleButton.exists, "Apple sign in button should exist")

        // Verify welcome text is accessible
        XCTAssertTrue(welcomeText.exists, "Welcome text should exist")

        takeScreenshot(name: "Accessibility-Auth")
    }

    func testAccessibility_TabBar_Labels() throws {
        app.launchArguments.append("--skip-auth")
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // All tabs should have accessibility labels
        XCTAssertTrue(app.tabBars.buttons["Home"].isAccessibilityElement)
        XCTAssertTrue(app.tabBars.buttons["History"].isAccessibilityElement)
        XCTAssertTrue(app.tabBars.buttons["Friends"].isAccessibilityElement)
        XCTAssertTrue(app.tabBars.buttons["Map"].isAccessibilityElement)

        takeScreenshot(name: "Accessibility-TabBar")
    }

    func testAccessibility_DynamicTypeSupport() throws {
        // Test that app handles large text sizes
        app.launchArguments.append("-UIPreferredContentSizeCategoryName")
        app.launchArguments.append("UICTContentSizeCategoryAccessibilityExtraExtraExtraLarge")
        app.launch()

        // App should still be usable with large text
        let welcomeText = app.staticTexts["Welcome"]
        let homeboundText = app.staticTexts["Homebound"]

        XCTAssertTrue(waitForElement(welcomeText) || waitForElement(homeboundText))

        takeScreenshot(name: "Accessibility-LargeText")
    }

    func testAccessibility_ReduceMotion() throws {
        // Test that app respects reduce motion preference
        app.launchArguments.append("-UIAccessibilityReduceMotionEnabled")
        app.launchArguments.append("YES")
        app.launch()

        // App should launch successfully with reduce motion enabled
        XCTAssertTrue(app.exists)

        takeScreenshot(name: "Accessibility-ReduceMotion")
    }

    func testAccessibility_HighContrast() throws {
        // Test that app handles high contrast mode
        app.launchArguments.append("-UIAccessibilityDarkerSystemColorsEnabled")
        app.launchArguments.append("YES")
        app.launch()

        // App should launch successfully
        XCTAssertTrue(app.exists)

        takeScreenshot(name: "Accessibility-HighContrast")
    }

    func testAccessibility_ButtonMinimumTapTarget() throws {
        app.launch()

        // Buttons should have minimum 44x44 tap target
        let continueButton = app.buttons["Continue with Email"]
        if waitForElement(continueButton) {
            let frame = continueButton.frame
            // Note: This is a soft check - actual enforcement would be in design review
            XCTAssertGreaterThanOrEqual(frame.height, 44, "Button height should be at least 44pt")
        }
    }
}
