import Foundation
import CoreLocation
import Combine
import UIKit

/// Centralized location manager that handles all location services for the app
class LocationManager: NSObject, ObservableObject {
    // Singleton instance
    static let shared = LocationManager()

    // Published properties
    @Published var currentLocation: CLLocationCoordinate2D?
    @Published var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published var isAuthorized: Bool = false
    @Published var locationError: String?

    // Private properties
    private let locationManager = CLLocationManager()
    private var hasRequestedPermission = false

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters // Reduced accuracy for better performance
        locationManager.distanceFilter = 50 // Update every 50 meters (less frequent)

        // Get initial authorization status
        authorizationStatus = locationManager.authorizationStatus
        updateAuthorizationState()
    }

    /// Request location permission if not already determined
    func requestPermission() {
        guard authorizationStatus == .notDetermined else {
            debugLog("[LocationManager] Permission already determined: \(authorizationStatus.rawValue)")
            return
        }

        hasRequestedPermission = true
        debugLog("[LocationManager] Requesting location permission...")
        locationManager.requestWhenInUseAuthorization()
    }

    /// Start updating user location
    func startUpdatingLocation() {
        guard isAuthorized else {
            debugLog("[LocationManager] Not authorized to update location")
            locationError = "Location access not authorized"

            // Request permission if not yet determined
            if authorizationStatus == .notDetermined {
                requestPermission()
            }
            return
        }

        debugLog("[LocationManager] Starting location updates...")
        locationError = nil
        locationManager.startUpdatingLocation()
    }

    /// Stop updating user location
    func stopUpdatingLocation() {
        debugLog("[LocationManager] Stopping location updates...")
        locationManager.stopUpdatingLocation()
    }

    /// Get current location once
    func getCurrentLocation() async -> CLLocationCoordinate2D? {
        // If we already have a recent location, return it
        if let location = currentLocation {
            return location
        }

        // Otherwise, start updates and wait for a location
        startUpdatingLocation()

        // Wait up to 5 seconds for a location
        for _ in 0..<50 {
            if let location = currentLocation {
                return location
            }
            try? await Task.sleep(nanoseconds: 100_000_000) // 0.1 seconds
        }

        return nil
    }

    /// Open Settings app to location permissions
    func openSettings() {
        guard let settingsURL = URL(string: UIApplication.openSettingsURLString) else { return }
        if UIApplication.shared.canOpenURL(settingsURL) {
            UIApplication.shared.open(settingsURL)
        }
    }

    /// Force refresh authorization state - call this before checking authorization
    func refreshAuthorizationState() {
        updateAuthorizationState()
    }

    private func updateAuthorizationState() {
        let status = locationManager.authorizationStatus
        authorizationStatus = status

        switch status {
        case .authorizedWhenInUse, .authorizedAlways:
            isAuthorized = true
            locationError = nil
            debugLog("[LocationManager] ✅ Location authorized")
        case .denied:
            isAuthorized = false
            locationError = "Location access denied. Enable in Settings."
            debugLog("[LocationManager] ❌ Location denied")
        case .restricted:
            isAuthorized = false
            locationError = "Location access restricted"
            debugLog("[LocationManager] ❌ Location restricted")
        case .notDetermined:
            isAuthorized = false
            locationError = nil
            debugLog("[LocationManager] ⚠️  Location not determined")
        @unknown default:
            isAuthorized = false
            locationError = "Unknown location authorization status"
            debugLog("[LocationManager] ❓ Unknown status")
        }
    }
}

// MARK: - CLLocationManagerDelegate
extension LocationManager: CLLocationManagerDelegate {
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        debugLog("[LocationManager] Authorization changed to: \(manager.authorizationStatus.rawValue)")
        updateAuthorizationState()

        // If just authorized, start updates
        if isAuthorized && hasRequestedPermission {
            startUpdatingLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }

        // Update current location
        DispatchQueue.main.async {
            self.currentLocation = location.coordinate
            self.locationError = nil
            debugLog("[LocationManager] 📍 Location updated: \(location.coordinate.latitude), \(location.coordinate.longitude)")
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        DispatchQueue.main.async {
            if let clError = error as? CLError {
                switch clError.code {
                case .denied:
                    self.locationError = "Location access denied"
                    self.isAuthorized = false
                case .locationUnknown:
                    self.locationError = "Location unavailable"
                default:
                    self.locationError = "Location error: \(clError.localizedDescription)"
                }
            } else {
                self.locationError = "Location error: \(error.localizedDescription)"
            }

            debugLog("[LocationManager] ❌ Location error: \(error.localizedDescription)")
        }
    }
}
