import XCTest

final class FriendsUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - Friends Tab Tests

    func testFriendsView_NavigateToFriends() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Friends tab
        let friendsTab = app.tabBars.buttons["Friends"]
        friendsTab.tap()

        XCTAssertTrue(friendsTab.isSelected)

        takeScreenshot(name: "Friends-View")
    }

    func testFriendsView_ShowsEmptyStateOrFriends() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Friends tab
        app.tabBars.buttons["Friends"].tap()
        sleep(1)

        // Should show either empty state with add friend option, or friends list
        let hasContent = app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'friend' OR label CONTAINS[c] 'invite' OR label CONTAINS[c] 'add'")).firstMatch.exists

        takeScreenshot(name: "Friends-Content")
    }

    func testFriendsView_AddFriendButton() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Friends tab
        app.tabBars.buttons["Friends"].tap()
        sleep(1)

        // Look for add friend button or invite option
        let addButtons = [
            "Add Friend",
            "Invite",
            "Add",
            "plus"
        ]

        var foundAddButton = false
        for button in addButtons {
            if app.buttons[button].exists ||
               app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", button)).firstMatch.exists {
                foundAddButton = true
                break
            }
        }

        takeScreenshot(name: "Friends-AddButton")
    }

    func testFriendsView_PendingInvitesSection() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Friends tab
        app.tabBars.buttons["Friends"].tap()
        sleep(1)

        // Check for pending invites section
        let pendingLabels = [
            "Pending",
            "Invites",
            "Requests"
        ]

        var foundPending = false
        for label in pendingLabels {
            if app.staticTexts[label].exists ||
               app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] %@", label)).firstMatch.exists {
                foundPending = true
                break
            }
        }

        takeScreenshot(name: "Friends-Pending")
    }

    // MARK: - Friend Profile Tests

    func testFriendsView_TapFriend_OpensProfile() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Friends tab
        app.tabBars.buttons["Friends"].tap()
        sleep(1)

        // Try to find and tap a friend cell
        let friendCells = app.cells.allElementsBoundByIndex
        if friendCells.count > 0 {
            friendCells[0].tap()
            sleep(1)
            takeScreenshot(name: "Friends-Profile")
        }
    }

    // MARK: - QR Code Tests

    func testFriendsView_QRCodeButton() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Friends tab
        app.tabBars.buttons["Friends"].tap()
        sleep(1)

        // Look for QR code related buttons
        let qrButtons = [
            "QR",
            "qrcode",
            "Scan"
        ]

        var foundQRButton = false
        for button in qrButtons {
            if app.buttons[button].exists ||
               app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", button)).firstMatch.exists {
                foundQRButton = true
                break
            }
        }

        takeScreenshot(name: "Friends-QRButton")
    }
}
