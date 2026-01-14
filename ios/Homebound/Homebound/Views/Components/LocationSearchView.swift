import SwiftUI
import MapKit
import CoreLocation
import Combine

// MARK: - Location Search View
struct LocationSearchView: View {
    @Binding var selectedLocation: String
    @Binding var selectedCoordinates: CLLocationCoordinate2D?
    @Binding var isPresented: Bool

    @StateObject private var searchCompleter = LocationSearchCompleter()
    @ObservedObject private var locationManager = LocationManager.shared
    @State private var searchText = ""
    @State private var showingNearby = true
    @State private var isGettingCurrentLocation = false
    @State private var showLocationDeniedAlert = false

    // Selection state
    @State private var isSelectingResult = false
    @State private var showSelectionError = false
    @State private var selectionErrorMessage = ""

    // Map picker state
    @State private var showingMapPicker = false
    @State private var mapPinCoordinate: CLLocationCoordinate2D?
    @State private var mapSelectedAddress: String = ""
    @State private var isReverseGeocoding = false
    @State private var mapCameraPosition: MapCameraPosition = .automatic

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search Bar
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)

                    TextField("Search places...", text: $searchText)
                        .textFieldStyle(.plain)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .onChange(of: searchText) { _, newValue in
                            searchCompleter.searchQuery = newValue
                            showingNearby = newValue.isEmpty
                        }

                    if !searchText.isEmpty {
                        Button(action: {
                            searchText = ""
                            showingNearby = true
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
                .background(Color(.secondarySystemBackground))
                .cornerRadius(12)
                .padding()

                // Results List
                List {
                    if showingNearby {
                        // Current Location Option
                        Section {
                            Button(action: handleCurrentLocationTap) {
                                HStack {
                                    ZStack {
                                        Circle()
                                            .fill(Color.hbBrand)
                                            .frame(width: 40, height: 40)

                                        if isGettingCurrentLocation {
                                            ProgressView()
                                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                                .scaleEffect(0.8)
                                        } else {
                                            Image(systemName: locationManager.isAuthorized ? "location.fill" : "location.slash.fill")
                                                .foregroundStyle(.white)
                                                .font(.system(size: 18))
                                        }
                                    }

                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("Current Location")
                                            .font(.subheadline)
                                            .fontWeight(.medium)
                                            .foregroundStyle(.primary)

                                        if let error = locationManager.locationError {
                                            Text(error)
                                                .font(.caption)
                                                .foregroundStyle(.red)
                                        } else if isGettingCurrentLocation {
                                            Text("Getting your location...")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        } else if locationManager.isAuthorized {
                                            Text("Use your current location")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        } else {
                                            Text("Tap to enable location")
                                                .font(.caption)
                                                .foregroundStyle(.orange)
                                        }
                                    }

                                    Spacer()
                                }
                            }
                            .disabled(isGettingCurrentLocation)
                        }

                        // Map Picker Section
                        Section {
                            DisclosureGroup(isExpanded: $showingMapPicker) {
                                VStack(spacing: 12) {
                                    // Map view
                                    MapReader { proxy in
                                        Map(position: $mapCameraPosition) {
                                            // User location
                                            UserAnnotation()

                                            // Selected pin
                                            if let coordinate = mapPinCoordinate {
                                                Annotation("", coordinate: coordinate) {
                                                    Image(systemName: "mappin.circle.fill")
                                                        .font(.title)
                                                        .foregroundStyle(Color.hbBrand)
                                                        .background(
                                                            Circle()
                                                                .fill(.white)
                                                                .frame(width: 24, height: 24)
                                                        )
                                                }
                                            }
                                        }
                                        .mapStyle(.standard)
                                        .mapControls {
                                            MapUserLocationButton()
                                        }
                                        .frame(height: 200)
                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                        .onTapGesture { position in
                                            if let coordinate = proxy.convert(position, from: .local) {
                                                mapPinCoordinate = coordinate
                                                mapCameraPosition = .region(MKCoordinateRegion(
                                                    center: coordinate,
                                                    span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                                                ))
                                                Task {
                                                    await reverseGeocodeMapPin(coordinate)
                                                }
                                            }
                                        }
                                    }

                                    // Address preview
                                    if isReverseGeocoding {
                                        HStack {
                                            ProgressView()
                                                .scaleEffect(0.8)
                                            Text("Getting address...")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    } else if !mapSelectedAddress.isEmpty {
                                        Text(mapSelectedAddress)
                                            .font(.subheadline)
                                            .foregroundStyle(.primary)
                                            .multilineTextAlignment(.center)
                                    } else if mapPinCoordinate == nil {
                                        Text("Tap on the map to select a location")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    // Use this location button
                                    if mapPinCoordinate != nil && !mapSelectedAddress.isEmpty && !isReverseGeocoding {
                                        Button(action: {
                                            selectedLocation = mapSelectedAddress
                                            selectedCoordinates = mapPinCoordinate
                                            isPresented = false
                                        }) {
                                            Text("Use this location")
                                                .font(.subheadline)
                                                .fontWeight(.semibold)
                                                .foregroundStyle(.white)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 12)
                                                .background(Color.hbBrand)
                                                .cornerRadius(10)
                                        }
                                    }
                                }
                                .padding(.vertical, 8)
                            } label: {
                                HStack {
                                    ZStack {
                                        Circle()
                                            .fill(Color.hbBrand.opacity(0.2))
                                            .frame(width: 40, height: 40)

                                        Image(systemName: "map")
                                            .foregroundStyle(Color.hbBrand)
                                            .font(.system(size: 18))
                                    }

                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("Select on Map")
                                            .font(.subheadline)
                                            .fontWeight(.medium)
                                            .foregroundStyle(.primary)

                                        Text("Tap to choose a location visually")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            .tint(.primary)
                        }

                    } else {
                        // Search Results
                        if searchCompleter.isSearching {
                            // Show loading indicator while search is in progress
                            HStack {
                                Spacer()
                                VStack(spacing: 12) {
                                    ProgressView()
                                        .scaleEffect(1.2)

                                    Text("Searching...")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 40)
                                Spacer()
                            }
                            .listRowBackground(Color.clear)
                        } else if searchCompleter.searchResults.isEmpty && !searchText.isEmpty {
                            // No results found (only show when search is complete)
                            HStack {
                                Spacer()
                                VStack(spacing: 12) {
                                    Image(systemName: "magnifyingglass")
                                        .font(.largeTitle)
                                        .foregroundStyle(.secondary)

                                    Text("No results found")
                                        .font(.headline)
                                        .foregroundStyle(.secondary)

                                    Text("Try searching for a different place")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 40)
                                Spacer()
                            }
                            .listRowBackground(Color.clear)
                        } else {
                            ForEach(searchCompleter.searchResults, id: \.self) { result in
                                SearchResultRow(
                                    result: result,
                                    distance: searchCompleter.distances[searchCompleter.cacheKey(for: result)],
                                    isSelecting: isSelectingResult,
                                    onSelect: {
                                        Task {
                                            await selectSearchResult(result)
                                        }
                                    }
                                )
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollIndicators(.hidden)
                .disabled(isSelectingResult)
            }
            .navigationTitle("Select Location")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        isPresented = false
                    }
                }
            }
            .alert("Location Access Denied", isPresented: $showLocationDeniedAlert) {
                Button("Open Settings") {
                    locationManager.openSettings()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Please enable location access in Settings to use your current location.")
            }
            .alert("Location Selection Failed", isPresented: $showSelectionError) {
                Button("OK") {}
            } message: {
                Text(selectionErrorMessage)
            }
        }
        .task {
            // Start location services when view appears
            locationManager.startUpdatingLocation()
            // Set region bias and user location when available
            if let location = locationManager.currentLocation {
                searchCompleter.updateRegion(center: location)
                searchCompleter.userLocation = location
            }
        }
        .onChange(of: locationManager.currentLocation?.latitude) { _, _ in
            // Update region bias and user location when location changes
            if let location = locationManager.currentLocation {
                searchCompleter.updateRegion(center: location)
                searchCompleter.userLocation = location
            }
        }
    }

    private func handleCurrentLocationTap() {
        Task {
            // Force refresh authorization state to ensure we have the latest
            await MainActor.run {
                locationManager.refreshAuthorizationState()
            }

            // Check authorization status
            switch locationManager.authorizationStatus {
            case .notDetermined:
                // Request permission
                debugLog("[LocationSearch] Requesting location permission...")
                locationManager.requestPermission()
                // Wait for permission response
                try? await Task.sleep(nanoseconds: 1_500_000_000) // 1.5 seconds
                // Refresh state after waiting
                await MainActor.run {
                    locationManager.refreshAuthorizationState()
                }

            case .denied, .restricted:
                // Show alert to open settings
                debugLog("[LocationSearch] Location denied/restricted - showing alert")
                await MainActor.run {
                    showLocationDeniedAlert = true
                }
                return

            case .authorizedWhenInUse, .authorizedAlways:
                // Already authorized, proceed
                debugLog("[LocationSearch] Already authorized: \(locationManager.authorizationStatus.rawValue)")
                break

            @unknown default:
                break
            }

            // Get current location - check both status and flag for safety
            let currentStatus = locationManager.authorizationStatus
            guard currentStatus == .authorizedWhenInUse || currentStatus == .authorizedAlways else {
                debugLog("[LocationSearch] Not authorized after permission request. Status: \(currentStatus.rawValue)")
                return
            }

            await MainActor.run {
                isGettingCurrentLocation = true
            }

            if let location = await locationManager.getCurrentLocation() {
                // Reverse geocode to get street-level address using CLGeocoder
                let address = await reverseGeocodeCoordinate(location)

                await MainActor.run {
                    selectedLocation = address
                    selectedCoordinates = location
                    isGettingCurrentLocation = false
                    isPresented = false
                    debugLog("[LocationSearch] ✅ Current location: \(address)")
                }
            } else {
                await MainActor.run {
                    isGettingCurrentLocation = false
                    debugLog("[LocationSearch] ❌ Failed to get current location")
                }
            }
        }
    }

    private func selectSearchResult(_ result: MKLocalSearchCompletion) async {
        // Prevent double-taps
        guard !isSelectingResult else { return }

        await MainActor.run {
            isSelectingResult = true
        }

        // First, check if we have cached coordinates (from prefetch)
        if let cachedCoordinate = searchCompleter.getCachedCoordinates(for: result) {
            await MainActor.run {
                selectedLocation = result.title + (result.subtitle.isEmpty ? "" : ", \(result.subtitle)")
                selectedCoordinates = cachedCoordinate
                isSelectingResult = false
                isPresented = false
            }
            return
        }

        // If not cached, fetch with retry logic
        if let coordinate = await searchCompleter.fetchCoordinateWithRetry(for: result, maxRetries: 3) {
            await MainActor.run {
                selectedLocation = result.title + (result.subtitle.isEmpty ? "" : ", \(result.subtitle)")
                selectedCoordinates = coordinate
                isSelectingResult = false
                isPresented = false
            }
        } else {
            await MainActor.run {
                isSelectingResult = false
                selectionErrorMessage = "This location couldn't be found in Apple Maps. Try searching for a more specific address or place name."
                showSelectionError = true
            }
        }
    }

    // MARK: - Reverse Geocoding Helpers

    /// Reverse geocodes a coordinate to a street-level address using CLGeocoder
    private func reverseGeocodeCoordinate(_ coordinate: CLLocationCoordinate2D) async -> String {
        let geocoder = CLGeocoder()
        let location = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)

        do {
            let placemarks = try await geocoder.reverseGeocodeLocation(location)

            if let placemark = placemarks.first {
                return formatAddress(from: placemark)
            }
        } catch {
            debugLog("[LocationSearch] Reverse geocoding failed: \(error)")
        }

        return "Current Location"
    }

    /// Formats a placemark into a readable address string
    private func formatAddress(from placemark: CLPlacemark) -> String {
        // For locations with a street address, use traditional format
        if let thoroughfare = placemark.thoroughfare {
            var components: [String] = []

            if let subThoroughfare = placemark.subThoroughfare {
                components.append("\(subThoroughfare) \(thoroughfare)")
            } else {
                components.append(thoroughfare)
            }

            if let locality = placemark.locality {
                components.append(locality)
            }

            if let administrativeArea = placemark.administrativeArea {
                components.append(administrativeArea)
            }

            return components.joined(separator: ", ")
        }

        // For POIs/natural features without street addresses, prefer the name
        if let name = placemark.name, !name.isEmpty {
            var result = name

            // Add locality for context if different from name
            if let locality = placemark.locality, !name.contains(locality) {
                result += ", \(locality)"
            }

            // Add state for context
            if let administrativeArea = placemark.administrativeArea {
                result += ", \(administrativeArea)"
            }

            return result
        }

        // Fallback: build from whatever we have
        var components: [String] = []

        if let locality = placemark.locality {
            components.append(locality)
        }

        if let administrativeArea = placemark.administrativeArea {
            components.append(administrativeArea)
        }

        if components.isEmpty {
            return "Selected Location"
        }

        return components.joined(separator: ", ")
    }

    /// Reverse geocodes a map pin tap and updates the address preview
    private func reverseGeocodeMapPin(_ coordinate: CLLocationCoordinate2D) async {
        await MainActor.run {
            isReverseGeocoding = true
            mapSelectedAddress = ""
        }

        let address = await reverseGeocodeCoordinate(coordinate)

        await MainActor.run {
            mapSelectedAddress = address
            isReverseGeocoding = false
        }
    }
}

// MARK: - Search Result Row
struct SearchResultRow: View {
    let result: MKLocalSearchCompletion
    let distance: String?
    let isSelecting: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack {
                ZStack {
                    Circle()
                        .fill(Color.hbBrand.opacity(0.2))
                        .frame(width: 40, height: 40)

                    if isSelecting {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: Color.hbBrand))
                            .scaleEffect(0.8)
                    } else {
                        Image(systemName: "mappin.circle.fill")
                            .foregroundStyle(Color.hbBrand)
                            .font(.system(size: 18))
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(result.title)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)

                    if !result.subtitle.isEmpty {
                        Text(result.subtitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                if let distance = distance {
                    Text(distance)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .disabled(isSelecting)
    }
}

// MARK: - Location Search Completer
class LocationSearchCompleter: NSObject, ObservableObject {
    @Published var searchResults: [MKLocalSearchCompletion] = []
    @Published var isSearching = false
    @Published var distances: [String: String] = [:] // Formatted distances from cached coordinates

    /// Cache of pre-fetched coordinates for search results (keyed by title|subtitle)
    private var coordinateCache: [String: CLLocationCoordinate2D] = [:]
    private var prefetchTasks: [String: Task<Void, Never>] = [:]

    var userLocation: CLLocationCoordinate2D?

    var searchQuery = "" {
        didSet {
            if searchQuery.isEmpty {
                searchResults = []
                isSearching = false
                distances = [:]
                // Cancel any pending prefetch tasks
                prefetchTasks.values.forEach { $0.cancel() }
                prefetchTasks.removeAll()
            } else {
                isSearching = true
                searchCompleter.queryFragment = searchQuery
            }
        }
    }

    private let searchCompleter = MKLocalSearchCompleter()

    override init() {
        super.init()
        searchCompleter.delegate = self
        searchCompleter.resultTypes = [.address, .pointOfInterest]
    }

    /// Update the search region to bias results toward the user's location
    func updateRegion(center: CLLocationCoordinate2D) {
        let region = MKCoordinateRegion(
            center: center,
            latitudinalMeters: 50_000,
            longitudinalMeters: 50_000
        )
        searchCompleter.region = region
    }

    /// Get cache key for a search result
    func cacheKey(for result: MKLocalSearchCompletion) -> String {
        return "\(result.title)|\(result.subtitle)"
    }

    /// Get cached coordinates for a result, if available
    func getCachedCoordinates(for result: MKLocalSearchCompletion) -> CLLocationCoordinate2D? {
        return coordinateCache[cacheKey(for: result)]
    }

    /// Pre-fetch coordinates for the first N results to reduce latency when user taps
    func prefetchCoordinates(for results: [MKLocalSearchCompletion], limit: Int = 5) {
        // Cancel previous prefetch tasks
        prefetchTasks.values.forEach { $0.cancel() }
        prefetchTasks.removeAll()

        for result in results.prefix(limit) {
            let key = cacheKey(for: result)

            // Skip if already cached
            if coordinateCache[key] != nil { continue }

            let task = Task {
                if let coordinate = await fetchCoordinateWithRetry(for: result, maxRetries: 2) {
                    await MainActor.run {
                        self.coordinateCache[key] = coordinate
                        // Calculate distance if we have user location
                        if let userLoc = self.userLocation {
                            self.distances[key] = self.formatDistance(from: userLoc, to: coordinate)
                        }
                    }
                }
            }
            prefetchTasks[key] = task
        }
    }

    /// Fetch coordinates for a result with retry logic
    func fetchCoordinateWithRetry(for result: MKLocalSearchCompletion, maxRetries: Int = 3) async -> CLLocationCoordinate2D? {
        // Check cache first
        let key = cacheKey(for: result)
        if let cached = coordinateCache[key] {
            return cached
        }

        var lastError: Error?
        var emptyResultCount = 0

        for attempt in 0..<maxRetries {
            // Exponential backoff: 0ms, 500ms, 1500ms
            if attempt > 0 {
                let delay = UInt64(500_000_000 * attempt) // 500ms * attempt
                try? await Task.sleep(nanoseconds: delay)
            }

            // Check for cancellation
            if Task.isCancelled { return nil }

            let searchRequest = MKLocalSearch.Request(completion: result)
            let search = MKLocalSearch(request: searchRequest)

            do {
                let response = try await search.start()
                if let mapItem = response.mapItems.first {
                    let coordinate = mapItem.placemark.coordinate
                    // Validate coordinates are not invalid (0,0)
                    guard coordinate.latitude != 0 || coordinate.longitude != 0 else {
                        debugLog("[LocationSearch] Attempt \(attempt + 1): Got invalid (0,0) coordinates for '\(result.title)'")
                        emptyResultCount += 1
                        continue
                    }
                    // Cache the result
                    await MainActor.run {
                        self.coordinateCache[key] = coordinate
                        // Calculate distance if we have user location
                        if let userLoc = self.userLocation {
                            self.distances[key] = self.formatDistance(from: userLoc, to: coordinate)
                        }
                    }
                    return coordinate
                } else {
                    // MapKit returned no results for this completion - this is a known limitation
                    debugLog("[LocationSearch] Attempt \(attempt + 1): No mapItems returned for '\(result.title)' (Apple MapKit limitation)")
                    emptyResultCount += 1
                }
            } catch {
                lastError = error
                debugLog("[LocationSearch] Attempt \(attempt + 1)/\(maxRetries) failed: \(error.localizedDescription)")
            }
        }

        // Log final failure reason
        if emptyResultCount == maxRetries {
            debugLog("[LocationSearch] Location '\(result.title)' has no coordinate data in Apple Maps - try a more specific search")
        } else if let error = lastError {
            debugLog("[LocationSearch] All \(maxRetries) attempts failed for '\(result.title)': \(error.localizedDescription)")
        }
        return nil
    }

    /// Format distance between two coordinates
    private func formatDistance(from: CLLocationCoordinate2D, to: CLLocationCoordinate2D) -> String {
        let fromLocation = CLLocation(latitude: from.latitude, longitude: from.longitude)
        let toLocation = CLLocation(latitude: to.latitude, longitude: to.longitude)
        let meters = fromLocation.distance(from: toLocation)

        if meters < 1609.34 {  // Less than 1 mile
            let feet = meters * 3.28084
            return "\(Int(feet)) ft"
        } else {
            let miles = meters / 1609.34
            return String(format: "%.1f mi", miles)
        }
    }
}

// MARK: - MKLocalSearchCompleter Delegate
extension LocationSearchCompleter: MKLocalSearchCompleterDelegate {
    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        DispatchQueue.main.async {
            self.isSearching = false
            self.searchResults = completer.results
            // Pre-fetch coordinates for top results (reduces failure rate when user taps)
            self.prefetchCoordinates(for: completer.results, limit: 5)
        }
    }

    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        debugLog("Search completer error: \(error)")
        DispatchQueue.main.async {
            self.isSearching = false
        }
    }
}

#Preview {
    LocationSearchView(
        selectedLocation: .constant(""),
        selectedCoordinates: .constant(nil),
        isPresented: .constant(true)
    )
}