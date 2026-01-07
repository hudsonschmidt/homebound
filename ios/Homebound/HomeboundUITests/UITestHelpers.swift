import XCTest

/// Base class providing common helper methods for UI tests
class UITestCase: XCTestCase {

    var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
    }

    override func tearDownWithError() throws {
        app = nil
    }

    // MARK: - Helper Methods

    /// Wait for an element to exist with a timeout
    func waitForElement(_ element: XCUIElement, timeout: TimeInterval = 5) -> Bool {
        element.waitForExistence(timeout: timeout)
    }

    /// Tap an element if it exists
    func tapIfExists(_ element: XCUIElement) {
        if element.exists {
            element.tap()
        }
    }

    /// Clear text from a text field
    func clearTextField(_ textField: XCUIElement) {
        guard textField.exists else { return }
        textField.tap()

        if let stringValue = textField.value as? String, !stringValue.isEmpty {
            let deleteString = String(repeating: XCUIKeyboardKey.delete.rawValue, count: stringValue.count)
            textField.typeText(deleteString)
        }
    }

    /// Dismiss keyboard if visible
    func dismissKeyboard() {
        if app.keyboards.count > 0 {
            app.toolbars.buttons["Done"].tap()
        }
    }

    /// Take a screenshot with a given name
    func takeScreenshot(name: String) {
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// Wait for loading to complete
    func waitForLoadingToComplete(timeout: TimeInterval = 10) {
        let progressView = app.activityIndicators.firstMatch
        if progressView.exists {
            let predicate = NSPredicate(format: "exists == false")
            expectation(for: predicate, evaluatedWith: progressView)
            waitForExpectations(timeout: timeout)
        }
    }

    /// Check if app is showing authentication view
    var isOnAuthenticationView: Bool {
        app.staticTexts["Welcome"].exists ||
        app.staticTexts["Homebound"].exists && app.textFields["email@example.com"].exists
    }

    /// Check if app is showing main tab view
    var isOnMainTabView: Bool {
        app.tabBars.buttons["Home"].exists
    }
}
