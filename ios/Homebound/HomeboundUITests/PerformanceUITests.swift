import XCTest

final class PerformanceUITests: XCTestCase {

    var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
        app = nil
    }

    // MARK: - Launch Performance Tests

    @MainActor
    func testLaunchPerformance() throws {
        // This measures how long it takes to launch the application
        measure(metrics: [XCTApplicationLaunchMetric()]) {
            XCUIApplication().launch()
        }
    }

    @MainActor
    func testLaunchPerformance_ToFirstFrame() throws {
        // Measure time to first frame
        measure(metrics: [XCTApplicationLaunchMetric(waitUntilResponsive: true)]) {
            XCUIApplication().launch()
        }
    }

    // MARK: - Navigation Performance Tests

    @MainActor
    func testTabSwitchPerformance() throws {
        app.launchArguments = ["--skip-auth"]
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard homeTab.waitForExistence(timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        measure {
            // Switch through all tabs
            app.tabBars.buttons["History"].tap()
            app.tabBars.buttons["Friends"].tap()
            app.tabBars.buttons["Map"].tap()
            app.tabBars.buttons["Home"].tap()
        }
    }

    // MARK: - Scrolling Performance Tests

    @MainActor
    func testScrollPerformance_HistoryView() throws {
        app.launchArguments = ["--skip-auth"]
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard homeTab.waitForExistence(timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to History
        app.tabBars.buttons["History"].tap()
        sleep(1)

        let scrollView = app.scrollViews.firstMatch
        guard scrollView.exists else {
            throw XCTSkip("Scroll view not found")
        }

        measure(metrics: [XCTOSSignpostMetric.scrollDecelerationMetric]) {
            scrollView.swipeUp()
            scrollView.swipeDown()
        }
    }

    // MARK: - Memory Performance Tests

    @MainActor
    func testMemoryUsage_NavigationCycle() throws {
        app.launchArguments = ["--skip-auth"]
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard homeTab.waitForExistence(timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        let metrics: [XCTMetric] = [XCTMemoryMetric(application: app)]

        measure(metrics: metrics) {
            // Perform navigation cycle
            for _ in 0..<5 {
                app.tabBars.buttons["History"].tap()
                app.tabBars.buttons["Friends"].tap()
                app.tabBars.buttons["Map"].tap()
                app.tabBars.buttons["Home"].tap()
            }
        }
    }

    // MARK: - CPU Performance Tests

    @MainActor
    func testCPUUsage_IdleOnHome() throws {
        app.launchArguments = ["--skip-auth"]
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard homeTab.waitForExistence(timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        let metrics: [XCTMetric] = [XCTCPUMetric(application: app)]

        measure(metrics: metrics) {
            // Let app idle for a few seconds
            sleep(3)
        }
    }
}
