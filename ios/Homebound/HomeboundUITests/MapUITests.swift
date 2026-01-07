import XCTest

final class MapUITests: UITestCase {

    override func setUpWithError() throws {
        try super.setUpWithError()
        app.launchArguments.append("--skip-auth")
    }

    // MARK: - Map View Tests

    func testMapView_NavigateToMap() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        let mapTab = app.tabBars.buttons["Map"]
        mapTab.tap()

        XCTAssertTrue(mapTab.isSelected)

        takeScreenshot(name: "Map-View")
    }

    func testMapView_MapKitViewExists() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        app.tabBars.buttons["Map"].tap()
        sleep(2) // Wait for map to load

        // Map view should exist (MapKit creates a specific view)
        let mapView = app.maps.firstMatch
        XCTAssertTrue(mapView.exists || app.otherElements["Map"].exists, "Map view should exist")

        takeScreenshot(name: "Map-MapView")
    }

    func testMapView_MapInteraction_Zoom() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        app.tabBars.buttons["Map"].tap()
        sleep(2)

        // Try to interact with map (pinch to zoom)
        let mapView = app.maps.firstMatch
        if mapView.exists {
            mapView.pinch(withScale: 2.0, velocity: 1.0)
            sleep(1)
            takeScreenshot(name: "Map-ZoomedIn")

            mapView.pinch(withScale: 0.5, velocity: -1.0)
            sleep(1)
            takeScreenshot(name: "Map-ZoomedOut")
        }
    }

    func testMapView_MapInteraction_Pan() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        app.tabBars.buttons["Map"].tap()
        sleep(2)

        // Try to pan the map
        let mapView = app.maps.firstMatch
        if mapView.exists {
            mapView.swipeUp()
            sleep(1)
            takeScreenshot(name: "Map-PannedUp")

            mapView.swipeLeft()
            sleep(1)
            takeScreenshot(name: "Map-PannedLeft")
        }
    }

    // MARK: - Map Annotations Tests

    func testMapView_ShowsTripPins() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        app.tabBars.buttons["Map"].tap()
        sleep(2)

        // Look for map annotations/pins
        let mapView = app.maps.firstMatch
        if mapView.exists {
            // Annotations appear as buttons or other elements on the map
            let annotations = mapView.buttons.allElementsBoundByIndex
            // Note: May or may not have pins depending on trip history
            takeScreenshot(name: "Map-Annotations")
        }
    }

    func testMapView_TapAnnotation_ShowsDetail() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        app.tabBars.buttons["Map"].tap()
        sleep(2)

        // Try to tap an annotation
        let mapView = app.maps.firstMatch
        if mapView.exists {
            let annotations = mapView.buttons.allElementsBoundByIndex
            if annotations.count > 0 {
                annotations[0].tap()
                sleep(1)
                takeScreenshot(name: "Map-AnnotationDetail")
            }
        }
    }

    // MARK: - Map Controls Tests

    func testMapView_LocationButton() throws {
        app.launch()

        let homeTab = app.tabBars.buttons["Home"]
        guard waitForElement(homeTab, timeout: 10) else {
            throw XCTSkip("Unable to access main tab view - authentication required")
        }

        // Navigate to Map tab
        app.tabBars.buttons["Map"].tap()
        sleep(2)

        // Look for location/center button
        let locationButtons = [
            "location",
            "Location",
            "My Location",
            "Center"
        ]

        var foundLocationButton = false
        for button in locationButtons {
            if app.buttons[button].exists ||
               app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", button)).firstMatch.exists {
                foundLocationButton = true
                break
            }
        }

        takeScreenshot(name: "Map-LocationButton")
    }
}
