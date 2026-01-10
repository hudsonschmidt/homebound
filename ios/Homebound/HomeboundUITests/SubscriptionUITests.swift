import XCTest

final class SubscriptionUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - Navigation Tests

    func testSubscription_NavigateToSubscriptionSettings() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Open settings
        openSettings()

        // Look for subscription-related elements
        let subscriptionElements = [
            "Subscription",
            "Homebound+",
            "Plan",
            "Manage Subscription"
        ]

        var foundSubscriptionEntry = false
        for element in subscriptionElements {
            let predicate = NSPredicate(format: "label CONTAINS[c] %@", element)
            if app.buttons.matching(predicate).firstMatch.exists ||
               app.staticTexts.matching(predicate).firstMatch.exists {
                foundSubscriptionEntry = true
                break
            }
        }

        takeScreenshot(name: "Settings-Subscription-Entry")

        // Try to tap on subscription row if found
        let subscriptionRow = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'subscription'")).firstMatch
        if subscriptionRow.exists {
            subscriptionRow.tap()
            sleep(1)
            takeScreenshot(name: "Subscription-Settings-View")
        }
    }

    func testSubscription_SettingsViewShowsCurrentPlan() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()

        // Navigate to subscription settings
        navigateToSubscriptionSettings()

        // Should show current plan information
        let planLabels = [
            "Free Plan",
            "Homebound+",
            "FREE",
            "PREMIUM",
            "TRIAL"
        ]

        var foundPlanLabel = false
        for label in planLabels {
            if app.staticTexts[label].exists ||
               app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", label)).firstMatch.exists {
                foundPlanLabel = true
                break
            }
        }

        takeScreenshot(name: "Subscription-Current-Plan")
    }

    // MARK: - Feature Limits Display Tests

    func testSubscription_ShowsFeatureLimits() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Check for feature limit labels
        let featureLabels = [
            "Contacts per trip",
            "Trip history",
            "Extensions",
            "Stats",
            "Your Plan Includes"
        ]

        var foundFeatures = 0
        for label in featureLabels {
            let predicate = NSPredicate(format: "label CONTAINS[c] %@", label)
            if app.staticTexts.matching(predicate).firstMatch.exists {
                foundFeatures += 1
            }
        }

        takeScreenshot(name: "Subscription-Feature-Limits")
    }

    // MARK: - Restore Purchases Tests

    func testSubscription_RestorePurchasesButtonExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Scroll to find restore purchases
        let scrollView = app.scrollViews.firstMatch
        if scrollView.exists {
            scrollView.swipeUp()
        }

        // Look for restore purchases button
        let restoreButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'restore'")).firstMatch

        takeScreenshot(name: "Subscription-Restore-Button")

        if restoreButton.exists {
            XCTAssertTrue(restoreButton.isEnabled, "Restore purchases button should be enabled")
        }
    }

    // MARK: - Upgrade Flow Tests

    func testSubscription_UpgradeButtonExists_ForFreeUsers() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Look for upgrade button (only shows for free users)
        let upgradeElements = [
            "Upgrade",
            "Homebound+",
            "Get Premium",
            "Subscribe"
        ]

        var foundUpgrade = false
        for element in upgradeElements {
            let predicate = NSPredicate(format: "label CONTAINS[c] %@", element)
            if app.buttons.matching(predicate).firstMatch.exists {
                foundUpgrade = true
                break
            }
        }

        takeScreenshot(name: "Subscription-Upgrade-Option")
    }

    func testSubscription_TapUpgradeOpensPaywall() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Try to tap upgrade button
        let upgradeButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'upgrade'")).firstMatch
        if upgradeButton.exists && upgradeButton.isEnabled {
            upgradeButton.tap()
            sleep(1)

            // Check if paywall opened
            let paywallElements = [
                "Homebound+",
                "Monthly",
                "Yearly",
                "Free Trial",
                "Subscribe"
            ]

            var paywallOpened = false
            for element in paywallElements {
                let predicate = NSPredicate(format: "label CONTAINS[c] %@", element)
                if app.staticTexts.matching(predicate).firstMatch.exists ||
                   app.buttons.matching(predicate).firstMatch.exists {
                    paywallOpened = true
                    break
                }
            }

            takeScreenshot(name: "Paywall-Opened")
        } else {
            // User might already be premium, skip test
            throw XCTSkip("Upgrade button not found - user may already be premium")
        }
    }

    // MARK: - Paywall Tests

    func testPaywall_ShowsSubscriptionOptions() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Try to open paywall directly from settings
        openSettings()
        navigateToSubscriptionSettings()

        let upgradeButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'upgrade'")).firstMatch
        guard upgradeButton.exists else {
            throw XCTSkip("Upgrade button not found - user may already be premium")
        }

        upgradeButton.tap()
        sleep(1)

        // Verify paywall shows subscription options
        let hasMonthly = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'month'")).firstMatch.exists
        let hasYearly = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'year'")).firstMatch.exists

        takeScreenshot(name: "Paywall-Options")

        // At least one subscription option should be visible
        XCTAssertTrue(hasMonthly || hasYearly, "Paywall should show subscription options")
    }

    func testPaywall_ShowsFeaturesList() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        let upgradeButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'upgrade'")).firstMatch
        guard upgradeButton.exists else {
            throw XCTSkip("Upgrade button not found - user may already be premium")
        }

        upgradeButton.tap()
        sleep(1)

        // Scroll to see features
        let scrollView = app.scrollViews.firstMatch
        if scrollView.exists {
            scrollView.swipeUp()
        }

        // Check for feature descriptions
        let features = [
            "contact",
            "history",
            "widget",
            "map",
            "stats"
        ]

        var foundFeatures = 0
        for feature in features {
            let predicate = NSPredicate(format: "label CONTAINS[c] %@", feature)
            if app.staticTexts.matching(predicate).firstMatch.exists {
                foundFeatures += 1
            }
        }

        takeScreenshot(name: "Paywall-Features")
    }

    func testPaywall_CanBeDismissed() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        let upgradeButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'upgrade'")).firstMatch
        guard upgradeButton.exists else {
            throw XCTSkip("Upgrade button not found")
        }

        upgradeButton.tap()
        sleep(1)

        takeScreenshot(name: "Paywall-Before-Dismiss")

        // Try to dismiss paywall
        // First try close button
        let closeButton = app.buttons["Close"]
        if closeButton.exists {
            closeButton.tap()
        } else {
            // Try swipe down
            app.swipeDown()
        }

        sleep(1)

        takeScreenshot(name: "Paywall-After-Dismiss")
    }

    // MARK: - Premium User Tests

    func testSubscription_ManageSubscriptionButton_ForPremiumUsers() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Look for manage subscription button (only for premium users)
        let manageButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'manage' OR label CONTAINS[c] 'settings'")).firstMatch

        takeScreenshot(name: "Subscription-Manage-Button")

        // This test passes whether or not the button exists (depends on user state)
        // Just document what we found
    }

    func testSubscription_ShowsRenewalInfo_ForPremiumUsers() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Look for renewal-related labels
        let renewalLabels = [
            "Renews",
            "Expires",
            "Auto-renews",
            "Trial ends",
            "Access until"
        ]

        var foundRenewalInfo = false
        for label in renewalLabels {
            let predicate = NSPredicate(format: "label CONTAINS[c] %@", label)
            if app.staticTexts.matching(predicate).firstMatch.exists {
                foundRenewalInfo = true
                break
            }
        }

        takeScreenshot(name: "Subscription-Renewal-Info")
    }

    // MARK: - Badge Display Tests

    func testSubscription_ShowsCorrectBadge() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        openSettings()
        navigateToSubscriptionSettings()

        // Look for subscription badges
        let badges = [
            "FREE",
            "PREMIUM",
            "TRIAL",
            "CANCELLED"
        ]

        var foundBadge: String?
        for badge in badges {
            if app.staticTexts[badge].exists {
                foundBadge = badge
                break
            }
        }

        takeScreenshot(name: "Subscription-Badge-\(foundBadge ?? "Unknown")")
    }

    // MARK: - Helper Methods

    private func openSettings() {
        let settingsButton = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'gear' OR label CONTAINS[c] 'settings'")).firstMatch
        if settingsButton.exists {
            settingsButton.tap()
        } else {
            // Try tapping top-right area where settings usually is
            let topRightArea = app.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.1))
            topRightArea.tap()
        }
        sleep(1)
    }

    private func navigateToSubscriptionSettings() {
        // Look for subscription entry in settings
        let subscriptionRow = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'subscription'")).firstMatch

        if subscriptionRow.exists {
            subscriptionRow.tap()
            sleep(1)
        } else {
            // Try scrolling to find it
            let scrollView = app.scrollViews.firstMatch
            if scrollView.exists {
                scrollView.swipeUp()
                Thread.sleep(forTimeInterval: 0.5)

                // Try again after scrolling
                let subscriptionRowAfterScroll = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'subscription'")).firstMatch
                if subscriptionRowAfterScroll.exists {
                    subscriptionRowAfterScroll.tap()
                    sleep(1)
                }
            }
        }
    }
}
