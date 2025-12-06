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
                        if searchCompleter.searchResults.isEmpty && !searchText.isEmpty {
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
                                    distance: searchCompleter.distances[searchCompleter.resultKey(result)],
                                    locationEnabled: locationManager.isAuthorized,
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
        }
        .task {
            // Start location services when view appears
            locationManager.startUpdatingLocation()
            // Set initial user location for distance calculations
            searchCompleter.userLocation = locationManager.currentLocation
        }
        .onChange(of: locationManager.currentLocation?.latitude) { _, _ in
            // Update search completer with user location for distance calculations
            searchCompleter.userLocation = locationManager.currentLocation
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
        // Convert search completion to map item
        let searchRequest = MKLocalSearch.Request(completion: result)
        let search = MKLocalSearch(request: searchRequest)

        do {
            let response = try await search.start()
            if let mapItem = response.mapItems.first {
                await MainActor.run {
                    selectedLocation = result.title + (result.subtitle.isEmpty ? "" : ", \(result.subtitle)")
                    selectedCoordinates = mapItem.location.coordinate
                    isPresented = false
                }
            }
        } catch {
            debugLog("Error converting search result: \(error)")
            await MainActor.run {
                selectedLocation = result.title
                isPresented = false
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
        var components: [String] = []

        // Street address (number + street name)
        if let subThoroughfare = placemark.subThoroughfare,
           let thoroughfare = placemark.thoroughfare {
            components.append("\(subThoroughfare) \(thoroughfare)")
        } else if let thoroughfare = placemark.thoroughfare {
            components.append(thoroughfare)
        }

        // City
        if let locality = placemark.locality {
            components.append(locality)
        }

        // State
        if let administrativeArea = placemark.administrativeArea {
            components.append(administrativeArea)
        }

        // Return formatted address or fallback
        if components.isEmpty {
            // Try name as last resort (e.g., "Golden Gate Bridge")
            if let name = placemark.name, !name.isEmpty {
                return name
            }
            return "Current Location"
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
    let locationEnabled: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack {
                ZStack {
                    Circle()
                        .fill(Color.hbBrand.opacity(0.2))
                        .frame(width: 40, height: 40)

                    Image(systemName: "mappin.circle.fill")
                        .foregroundStyle(Color.hbBrand)
                        .font(.system(size: 18))
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

                // Distance or location prompt
                if let distance = distance {
                    Text(distance)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if !locationEnabled {
                    Image(systemName: "location.slash")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
        }
    }
}

// MARK: - Location Search Completer
class LocationSearchCompleter: NSObject, ObservableObject {
    @Published var searchResults: [MKLocalSearchCompletion] = []
    @Published var distances: [String: String] = [:] // Key: result title+subtitle, Value: formatted distance

    var userLocation: CLLocationCoordinate2D?

    var searchQuery = "" {
        didSet {
            if searchQuery.isEmpty {
                searchResults = []
                distances = [:]
            } else {
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

    /// Get a unique key for a search result
    func resultKey(_ result: MKLocalSearchCompletion) -> String {
        return "\(result.title)|\(result.subtitle)"
    }

    /// Fetch distances for all current results
    func fetchDistances() {
        guard let userLocation = userLocation else { return }

        for result in searchResults {
            let key = resultKey(result)
            // Skip if we already have this distance
            if distances[key] != nil { continue }

            Task {
                await fetchDistance(for: result, from: userLocation)
            }
        }
    }

    /// Fetch distance for a single result
    private func fetchDistance(for result: MKLocalSearchCompletion, from userLocation: CLLocationCoordinate2D) async {
        let request = MKLocalSearch.Request(completion: result)
        let search = MKLocalSearch(request: request)

        do {
            let response = try await search.start()
            if let resultCoord = response.mapItems.first?.placemark.coordinate {
                let userCL = CLLocation(latitude: userLocation.latitude, longitude: userLocation.longitude)
                let resultCL = CLLocation(latitude: resultCoord.latitude, longitude: resultCoord.longitude)
                let meters = userCL.distance(from: resultCL)
                let formatted = formatDistance(meters)

                await MainActor.run {
                    self.distances[self.resultKey(result)] = formatted
                }
            }
        } catch {
            // Silently ignore distance fetch failures
        }
    }

    /// Format distance in miles/feet
    private func formatDistance(_ meters: CLLocationDistance) -> String {
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
            self.searchResults = completer.results
            self.fetchDistances()
        }
    }

    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        debugLog("Search completer error: \(error)")
    }
}

#Preview {
    LocationSearchView(
        selectedLocation: .constant(""),
        selectedCoordinates: .constant(nil),
        isPresented: .constant(true)
    )
}