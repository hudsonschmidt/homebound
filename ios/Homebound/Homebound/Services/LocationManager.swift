import Foundation
import CoreLocation
import Combine
import UIKit

/// Centralized location manager that handles all location services for the app
@MainActor
class LocationManager: NSObject, ObservableObject {
    // Singleton instance
    static let shared = LocationManager()

    // Published properties
    @Published var currentLocation: CLLocationCoordinate2D?
    @Published var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published var isAuthorized: Bool = false
    @Published var locationError: String?
    @Published var lastLocationTime: Date?

    // Private properties
    private let locationManager = CLLocationManager()
    private var hasRequestedPermission = false
    private let maxLocationAge: TimeInterval = 60  // Location is stale after 60 seconds

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
        debugLog("[LocationManager] getCurrentLocation called, isAuthorized=\(isAuthorized), status=\(authorizationStatus.rawValue)")

        // First, check if LiveLocationManager has a fresh location (it's already tracking during active trips)
        if LiveLocationManager.shared.isSharing,
           let liveLocation = LiveLocationManager.shared.lastLocation?.coordinate {
            debugLog("[LocationManager] ✅ Using LiveLocationManager location: \(liveLocation.latitude), \(liveLocation.longitude)")
            return liveLocation
        }

        // Refresh authorization state first to ensure we have the latest
        refreshAuthorizationState()

        // Only return cached location if it's fresh (< maxLocationAge seconds old)
        if let location = currentLocation,
           let lastTime = lastLocationTime,
           Date().timeIntervalSince(lastTime) < maxLocationAge {
            debugLog("[LocationManager] Returning cached location (age: \(Int(Date().timeIntervalSince(lastTime)))s): \(location.latitude), \(location.longitude)")
            return location
        }

        // If we have a stale location, log it and fetch fresh
        if currentLocation != nil {
            debugLog("[LocationManager] ⚠️ Cached location is stale, fetching fresh...")
        }

        // Check authorization - if not determined, try requesting
        if !isAuthorized {
            if authorizationStatus == .notDetermined {
                debugLog("[LocationManager] Authorization not determined - requesting permission...")
                requestPermission()
                // Wait up to 2 seconds for user to respond to permission dialog
                for _ in 0..<20 {
                    try? await Task.sleep(nanoseconds: 100_000_000) // 0.1 seconds
                    refreshAuthorizationState()
                    if authorizationStatus != .notDetermined {
                        break
                    }
                }
            }

            // Re-check after potential authorization
            guard isAuthorized else {
                debugLog("[LocationManager] ❌ Cannot get location - not authorized (status=\(authorizationStatus.rawValue))")
                return nil
            }
        }

        // Start continuous location updates (more reliable than requestLocation for first fix)
        debugLog("[LocationManager] Starting location updates...")
        locationManager.startUpdatingLocation()

        // Wait up to 10 seconds for a location (increased from 5 for better reliability)
        for i in 0..<100 {
            if let location = currentLocation {
                debugLog("[LocationManager] ✅ Got location after \(i * 100)ms: \(location.latitude), \(location.longitude)")
                // Stop updates since we got what we needed
                locationManager.stopUpdatingLocation()
                return location
            }
            try? await Task.sleep(nanoseconds: 100_000_000) // 0.1 seconds
        }

        // Stop updates on timeout
        locationManager.stopUpdatingLocation()
        debugLog("[LocationManager] ❌ Timeout waiting for location after 10 seconds")
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
    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            debugLog("[LocationManager] Authorization changed to: \(status.rawValue)")
            self.updateAuthorizationState()

            // If just authorized, start updates
            if self.isAuthorized && self.hasRequestedPermission {
                self.startUpdatingLocation()
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }

        Task { @MainActor in
            self.currentLocation = location.coordinate
            self.lastLocationTime = Date()
            self.locationError = nil
            debugLog("[LocationManager] 📍 Location updated: \(location.coordinate.latitude), \(location.coordinate.longitude)")
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let errorDescription = error.localizedDescription
        let clError = error as? CLError

        Task { @MainActor in
            if let clError = clError {
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
                self.locationError = "Location error: \(errorDescription)"
            }

            debugLog("[LocationManager] ❌ Location error: \(errorDescription)")
        }
    }
}
