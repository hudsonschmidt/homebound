import Foundation
import CoreLocation
import Combine

/// Manages live location sharing for active trips.
/// When enabled for a trip, sends location updates to the server every 30 seconds.
@MainActor
final class LiveLocationManager: NSObject, ObservableObject {

    static let shared = LiveLocationManager()

    // MARK: - Published State

    @Published private(set) var isSharing: Bool = false
    @Published private(set) var currentTripId: Int?
    @Published private(set) var lastUpdateTime: Date?
    @Published private(set) var lastError: String?

    // MARK: - Private Properties

    private let locationManager = CLLocationManager()
    private var updateTimer: Timer?
    private(set) var lastLocation: CLLocation?
    private var lastSentLocation: CLLocation?  // Track last sent location for deduplication
    private let updateInterval: TimeInterval = 30  // seconds between updates
    private let minimumDistanceForUpdate: CLLocationDistance = 10  // meters
    private var retryCount: Int = 0  // Track failed update retries
    private let maxRetries = 3  // Maximum retry attempts before giving up

    // MARK: - Initialization

    private override init() {
        super.init()
        setupLocationManager()
    }

    private func setupLocationManager() {
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        // Note: allowsBackgroundLocationUpdates is set when starting updates
        // to avoid crash when background mode isn't properly configured
        locationManager.pausesLocationUpdatesAutomatically = false
    }

    // MARK: - Public Methods

    /// Start sharing live location for a specific trip.
    /// Works with both "Always" and "While Using" permissions.
    /// With "While Using", location updates only work when app is in foreground.
    func startSharing(forTripId tripId: Int) {
        guard !isSharing else {
            debugLog("[LiveLocation] Already sharing for trip \(currentTripId ?? 0)")
            return
        }

        // Check location authorization - allow both Always and WhenInUse
        let authStatus = locationManager.authorizationStatus
        guard authStatus == .authorizedAlways || authStatus == .authorizedWhenInUse else {
            lastError = "Location permission required."
            debugLog("[LiveLocation] ❌ Requires location permission, got: \(authStatus.rawValue)")
            return
        }

        debugLog("[LiveLocation] ✅ Starting live location sharing for trip \(tripId) (auth: \(authStatus == .authorizedAlways ? "Always" : "WhenInUse"))")
        currentTripId = tripId
        isSharing = true
        lastError = nil

        // Only enable background location updates if we have Always authorization
        if authStatus == .authorizedAlways {
            locationManager.allowsBackgroundLocationUpdates = true
            locationManager.showsBackgroundLocationIndicator = true
        } else {
            debugLog("[LiveLocation] ⚠️ Running with 'While Using' only - background updates disabled")
        }

        // Start location updates
        locationManager.startUpdatingLocation()

        // Start periodic update timer
        updateTimer = Timer.scheduledTimer(withTimeInterval: updateInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.sendLocationUpdate()
            }
        }

        // Send initial update immediately
        Task {
            await sendLocationUpdate()
        }
    }

    /// Stop sharing live location.
    func stopSharing() {
        guard isSharing else { return }

        debugLog("[LiveLocation] Stopping live location sharing for trip \(currentTripId ?? 0)")

        updateTimer?.invalidate()
        updateTimer = nil
        locationManager.stopUpdatingLocation()

        // Disable background location updates
        locationManager.allowsBackgroundLocationUpdates = false
        locationManager.showsBackgroundLocationIndicator = false

        isSharing = false
        currentTripId = nil
        lastLocation = nil
        lastSentLocation = nil
        retryCount = 0
    }

    /// Request location permission if needed.
    func requestPermissionIfNeeded() {
        let authStatus = locationManager.authorizationStatus

        switch authStatus {
        case .notDetermined:
            // Request "when in use" first, then user can upgrade to "always" in settings
            locationManager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse:
            // Need to upgrade to "always" for background updates
            locationManager.requestAlwaysAuthorization()
        default:
            break
        }
    }

    /// Check if we have sufficient authorization for live location (either Always or WhenInUse).
    var hasRequiredAuthorization: Bool {
        let status = locationManager.authorizationStatus
        return status == .authorizedAlways || status == .authorizedWhenInUse
    }

    /// Check if we have "Always" authorization for background location updates.
    var hasBackgroundAuthorization: Bool {
        locationManager.authorizationStatus == .authorizedAlways
    }

    // MARK: - Private Methods

    private func sendLocationUpdate() async {
        guard isSharing, let tripId = currentTripId, let location = lastLocation else {
            debugLog("[LiveLocation] ⚠️ Cannot send update: isSharing=\(isSharing), tripId=\(currentTripId ?? 0), hasLocation=\(lastLocation != nil)")
            return
        }

        // Skip if location hasn't changed significantly (saves battery/bandwidth)
        if let lastSent = lastSentLocation,
           location.distance(from: lastSent) < minimumDistanceForUpdate {
            debugLog("[LiveLocation] ⏭️ Skipping update - location hasn't changed significantly")
            return
        }

        debugLog("[LiveLocation] Sending location update: \(location.coordinate.latitude), \(location.coordinate.longitude)")

        do {
            let success = try await Session.shared.updateLiveLocation(
                tripId: tripId,
                latitude: location.coordinate.latitude,
                longitude: location.coordinate.longitude,
                altitude: location.altitude,
                horizontalAccuracy: location.horizontalAccuracy,
                speed: location.speed >= 0 ? location.speed : nil
            )

            if success {
                lastUpdateTime = Date()
                lastSentLocation = location  // Track for deduplication
                lastError = nil
                retryCount = 0  // Reset retry count on success
                debugLog("[LiveLocation] ✅ Location update sent successfully")
            } else {
                lastError = "Failed to send location update"
                debugLog("[LiveLocation] ❌ Location update failed")
                await retryIfNeeded()
            }
        } catch {
            lastError = error.localizedDescription
            debugLog("[LiveLocation] ❌ Error sending location: \(error)")
            await retryIfNeeded()
        }
    }

    /// Retry sending location update with exponential backoff
    private func retryIfNeeded() async {
        guard retryCount < maxRetries else {
            debugLog("[LiveLocation] Max retries reached, will try again at next interval")
            retryCount = 0
            return
        }

        let delay = pow(2.0, Double(retryCount))
        retryCount += 1
        debugLog("[LiveLocation] Will retry in \(delay)s (attempt \(retryCount)/\(maxRetries))")

        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
        await sendLocationUpdate()
    }
}

// MARK: - CLLocationManagerDelegate

extension LiveLocationManager: CLLocationManagerDelegate {

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }

        Task { @MainActor in
            self.lastLocation = location
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            self.lastError = error.localizedDescription
            debugLog("[LiveLocation] ❌ Location error: \(error)")
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus

        Task { @MainActor in
            debugLog("[LiveLocation] Authorization changed: \(status.rawValue)")

            // Only stop sharing if permission is completely revoked
            if (status == .denied || status == .restricted) && self.isSharing {
                self.stopSharing()
                self.lastError = "Location permission revoked"
                return
            }

            // If upgraded to Always while sharing, enable background mode
            if status == .authorizedAlways && self.isSharing {
                self.locationManager.allowsBackgroundLocationUpdates = true
                self.locationManager.showsBackgroundLocationIndicator = true
                debugLog("[LiveLocation] ✅ Upgraded to 'Always' - background updates enabled")
            }
        }
    }
}
