import SwiftUI
import MapKit
import CoreLocation

// MARK: - CLLocationCoordinate2D Equatable Conformance
extension CLLocationCoordinate2D: @retroactive Equatable {
    public static func == (lhs: CLLocationCoordinate2D, rhs: CLLocationCoordinate2D) -> Bool {
        lhs.latitude == rhs.latitude && lhs.longitude == rhs.longitude
    }
}

// MARK: - Trip Map View
struct TripMapView: View {
    @EnvironmentObject var session: Session
    @ObservedObject private var locationManager = LocationManager.shared
    @State private var trips: [Trip] = []
    @State private var isLoading = false
    @State private var region = MKCoordinateRegion(
        center: Constants.Map.defaultCenter,
        span: MKCoordinateSpan(latitudeDelta: Constants.Map.defaultSpanDelta, longitudeDelta: Constants.Map.defaultSpanDelta)
    )
    @State private var mapPosition: MapCameraPosition = .automatic
    @State private var selectedActivity: String? = nil
    @State private var selectedTrip: Trip? = nil
    @State private var showLocationDeniedAlert = false
    @State private var hasLoadedInitialView = false
    @State private var hasSetInitialLocationZoom = false

    var tripsWithLocations: [Trip] {
        trips.filter { trip in
            guard let lat = trip.location_lat, let lon = trip.location_lng else { return false }
            return lat != 0.0 && lon != 0.0
        }
    }

    var filteredTrips: [Trip] {
        if let selectedActivity = selectedActivity {
            return tripsWithLocations.filter { $0.activity_type.lowercased() == selectedActivity.lowercased() }
        }
        return tripsWithLocations
    }

    var annotations: [TripAnnotation] {
        filteredTrips.map { trip in
            TripAnnotation(trip: trip, isStart: false)
        }
    }

    var startAnnotations: [TripAnnotation] {
        filteredTrips.filter { $0.has_separate_locations }
            .compactMap { trip -> TripAnnotation? in
                guard let lat = trip.start_lat, let lng = trip.start_lng,
                      lat != 0.0 && lng != 0.0 else { return nil }
                return TripAnnotation(trip: trip, isStart: true)
            }
    }

    var activityFilters: [Activity] {
        let uniqueActivities = Dictionary(grouping: tripsWithLocations) { $0.activity.id }
            .compactMap { $0.value.first?.activity }
        return uniqueActivities.sorted { $0.name < $1.name }
    }

    var mapStyleFromPreferences: MapStyle {
        switch AppPreferences.shared.defaultMapType {
        case .standard:
            return .standard
        case .satellite:
            return .imagery
        case .hybrid:
            return .hybrid
        }
    }

    // MARK: - Filter Controls
    @ViewBuilder
    private var filterControls: some View {
        VStack {
            Spacer()

            // Selected trip card (above filter chips)
            if let trip = selectedTrip {
                TripDetailCard(trip: trip) {
                    withAnimation {
                        selectedTrip = nil
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 8)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            // Activity filter chips
            if !activityFilters.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        // All button
                        FilterChip(
                            label: "All",
                            icon: "📍",
                            isSelected: selectedActivity == nil,
                            count: tripsWithLocations.count
                        ) {
                            withAnimation {
                                selectedActivity = nil
                            }
                        }

                        // Activity filters
                        ForEach(activityFilters, id: \.id) { activity in
                            let count = tripsWithLocations.filter { $0.activity.id == activity.id }.count

                            FilterChip(
                                label: activity.name,
                                icon: activity.icon,
                                isSelected: selectedActivity == activity.name,
                                count: count
                            ) {
                                withAnimation {
                                    selectedActivity = selectedActivity == activity.name ? nil : activity.name
                                }
                            }
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
            }
        }
    }

    // MARK: - Map Content
    @MapContentBuilder
    private var mapContent: some MapContent {
        // User location
        if locationManager.isAuthorized, let userLocation = locationManager.currentLocation {
            Annotation("My Location", coordinate: userLocation) {
                Circle()
                    .fill(Color.blue)
                    .frame(width: 20, height: 20)
                    .overlay(
                        Circle()
                            .stroke(Color.white, lineWidth: 3)
                    )
                    .shadow(radius: 3)
            }
        }

        // Trip destination annotations
        ForEach(annotations) { annotation in
            Annotation(annotation.trip.title, coordinate: annotation.coordinate) {
                TripMapPin(annotation: annotation, isSelected: selectedTrip?.id == annotation.trip.id)
                    .onTapGesture {
                        withAnimation {
                            selectedTrip = annotation.trip
                        }
                    }
            }
        }

        // Start location annotations (for trips with separate start/destination)
        ForEach(startAnnotations) { annotation in
            Annotation("Start: \(annotation.trip.title)", coordinate: annotation.coordinate) {
                StartLocationPin(annotation: annotation, isSelected: selectedTrip?.id == annotation.trip.id)
                    .onTapGesture {
                        withAnimation {
                            selectedTrip = annotation.trip
                        }
                    }
            }
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Map - Using modern iOS 17+ API
                Map(position: $mapPosition) {
                    mapContent
                }
                .mapStyle(mapStyleFromPreferences)
                .ignoresSafeArea(edges: .top)
                .onTapGesture {
                    // Tap map to dismiss selected trip card
                    if selectedTrip != nil {
                        withAnimation {
                            selectedTrip = nil
                        }
                    }
                }

                filterControls

                // Loading indicator
                if isLoading {
                    ProgressView()
                        .scaleEffect(1.5)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(.ultraThinMaterial)
                }
            }
            .navigationTitle("Trip Map")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    HStack(spacing: 12) {
                        // Center on user location button
                        Button(action: centerOnUserLocation) {
                            Image(systemName: locationManager.isAuthorized ? "location.fill" : "location.slash.fill")
                                .foregroundStyle(locationManager.isAuthorized ? Color.white : .gray)
                        }

                        // Center on trips button
                        Button(action: centerOnTrips) {
                            Image(systemName: "scope")
                                .foregroundStyle(Color.white)
                        }
                    }
                }
            }
            .alert("Location Access Denied", isPresented: $showLocationDeniedAlert) {
                Button("Open Settings") {
                    locationManager.openSettings()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Please enable location access in Settings to see your location on the map.")
            }
            .task {
                // Load trips first (faster)
                await loadTrips()

                // Delay location services slightly to reduce initial lag
                try? await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
                locationManager.startUpdatingLocation()

                hasLoadedInitialView = true
            }
            .onDisappear {
                // Stop location updates when view disappears to conserve battery
                locationManager.stopUpdatingLocation()
            }
            .onChange(of: locationManager.currentLocation) { oldValue, newValue in
                // Only zoom on first location fix after permission granted
                if !hasSetInitialLocationZoom, let location = newValue {
                    hasSetInitialLocationZoom = true

                    // Zoom to neighborhood level (~10km)
                    let newRegion = MKCoordinateRegion(
                        center: location,
                        span: MKCoordinateSpan(latitudeDelta: 0.1, longitudeDelta: 0.1)
                    )

                    withAnimation {
                        mapPosition = .region(newRegion)
                        region = newRegion
                    }
                }
            }
        }
    }

    func loadTrips() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let loadedTrips: [Trip] = try await session.api.get(
                session.url("/api/v1/trips/"),
                bearer: session.accessToken
            )

            await MainActor.run {
                trips = loadedTrips

                // Only auto-center on first load if there are trips
                if !hasLoadedInitialView && !loadedTrips.isEmpty {
                    centerOnTrips()
                }
            }
        } catch {
            debugLog("Failed to load trips: \(error)")
        }
    }

    func centerOnTrips() {
        guard !filteredTrips.isEmpty else { return }

        let coordinates = filteredTrips.compactMap { trip -> CLLocationCoordinate2D? in
            guard let lat = trip.location_lat, let lon = trip.location_lng else { return nil }
            return CLLocationCoordinate2D(latitude: lat, longitude: lon)
        }

        guard !coordinates.isEmpty else { return }

        let minLat = coordinates.map { $0.latitude }.min() ?? 0
        let maxLat = coordinates.map { $0.latitude }.max() ?? 0
        let minLon = coordinates.map { $0.longitude }.min() ?? 0
        let maxLon = coordinates.map { $0.longitude }.max() ?? 0

        let center = CLLocationCoordinate2D(
            latitude: (minLat + maxLat) / 2,
            longitude: (minLon + maxLon) / 2
        )

        let span = MKCoordinateSpan(
            latitudeDelta: max((maxLat - minLat) * 1.3, 0.1),
            longitudeDelta: max((maxLon - minLon) * 1.3, 0.1)
        )

        let newRegion = MKCoordinateRegion(center: center, span: span)

        withAnimation {
            mapPosition = .region(newRegion)
            region = newRegion
        }
    }

    func centerOnUserLocation() {
        // Check authorization status
        switch locationManager.authorizationStatus {
        case .notDetermined:
            // Request permission
            debugLog("[TripMap] Requesting location permission...")
            locationManager.requestPermission()

        case .denied, .restricted:
            // Show alert to open settings
            debugLog("[TripMap] Location denied/restricted - showing alert")
            showLocationDeniedAlert = true

        case .authorizedWhenInUse, .authorizedAlways:
            // Center on user location if available
            if let userLocation = locationManager.currentLocation {
                let newRegion = MKCoordinateRegion(
                    center: userLocation,
                    span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)
                )

                withAnimation {
                    mapPosition = .region(newRegion)
                    region = newRegion
                }
                debugLog("[TripMap] ✅ Centered on user location: \(userLocation)")
            } else {
                debugLog("[TripMap] ⚠️  User location not available yet")
                // Start updates if not already running
                locationManager.startUpdatingLocation()
            }

        @unknown default:
            break
        }
    }
}

// MARK: - Trip Annotation
struct TripAnnotation: Identifiable {
    let id: String
    let trip: Trip
    let coordinate: CLLocationCoordinate2D
    let isStart: Bool

    init(trip: Trip, isStart: Bool = false) {
        self.id = isStart ? "start-\(trip.id)" : "dest-\(trip.id)"
        self.trip = trip
        self.isStart = isStart
        if isStart {
            self.coordinate = CLLocationCoordinate2D(
                latitude: trip.start_lat ?? 0,
                longitude: trip.start_lng ?? 0
            )
        } else {
            self.coordinate = CLLocationCoordinate2D(
                latitude: trip.location_lat ?? 0,
                longitude: trip.location_lng ?? 0
            )
        }
    }
}

// MARK: - Trip Map Pin
struct TripMapPin: View {
    let annotation: TripAnnotation
    let isSelected: Bool

    var activity: ActivityTypeAdapter {
        ActivityTypeAdapter(activity: annotation.trip.activity)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Activity icon
            Circle()
                .fill(activity.primaryColor)
                .frame(width: isSelected ? 44 : 32, height: isSelected ? 44 : 32)
                .overlay(
                    Text(activity.icon)
                        .font(isSelected ? .title3 : .caption)
                )
                .overlay(
                    Circle()
                        .stroke(Color.white, lineWidth: 3)
                )
                .shadow(color: .black.opacity(0.3), radius: 3, x: 0, y: 2)

            // Pin tail
            Image(systemName: "arrowtriangle.down.fill")
                .font(.caption)
                .foregroundStyle(activity.primaryColor)
                .offset(y: -4)
        }
        .scaleEffect(isSelected ? 1.2 : 1.0)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isSelected)
    }
}

// MARK: - Start Location Pin
struct StartLocationPin: View {
    let annotation: TripAnnotation
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Start icon (green circle with departure icon)
            Circle()
                .fill(Color.green)
                .frame(width: isSelected ? 36 : 26, height: isSelected ? 36 : 26)
                .overlay(
                    Image(systemName: "figure.walk.departure")
                        .font(isSelected ? .caption : .caption2)
                        .foregroundStyle(.white)
                )
                .overlay(
                    Circle()
                        .stroke(Color.white, lineWidth: 2)
                )
                .shadow(color: .black.opacity(0.3), radius: 2, x: 0, y: 1)

            // Pin tail
            Image(systemName: "arrowtriangle.down.fill")
                .font(.caption2)
                .foregroundStyle(.green)
                .offset(y: -3)

        }
        .scaleEffect(isSelected ? 1.2 : 1.0)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isSelected)
    }
}

// MARK: - Filter Chip
struct FilterChip: View {
    let label: String
    let icon: String
    let isSelected: Bool
    let count: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(icon)
                    .font(.caption)
                Text(label)
                    .font(.caption)
                    .fontWeight(.medium)
                Text("(\(count))")
                    .font(.caption2)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? (Color.hbBrand) : Color(.systemBackground))
            .foregroundStyle(isSelected ? .white : .primary)
            .cornerRadius(20)
            .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
        }
    }
}

// MARK: - Trip Detail Card
struct TripDetailCard: View {
    let trip: Trip
    let onDismiss: () -> Void

    var activity: ActivityTypeAdapter {
        ActivityTypeAdapter(activity: trip.activity)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Circle()
                    .fill(activity.primaryColor.opacity(0.2))
                    .frame(width: 40, height: 40)
                    .overlay(
                        Text(activity.icon)
                            .font(.title3)
                    )

                VStack(alignment: .leading, spacing: 2) {
                    Text(trip.title)
                        .font(.headline)
                        .lineLimit(1)

                    Text(activity.displayName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 24, height: 24)
                        .background(Circle().fill(.black.opacity(0.5)))
                }
            }

            // Details
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "calendar")
                        .font(.caption)
                    Text(DateUtils.formatDateTime(trip.start_at, inTimezone: trip.start_timezone))
                        .font(.caption)
                }
                .foregroundStyle(.secondary)

                if let location = trip.location_text {
                    HStack(spacing: 6) {
                        Image(systemName: "location.fill")
                            .font(.caption)
                        Text(location)
                            .font(.caption)
                            .lineLimit(1)
                    }
                    .foregroundStyle(.secondary)
                }

                // Status badge
                HStack(spacing: 6) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 8, height: 8)
                    Text(trip.status.capitalized)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                .foregroundStyle(statusColor)
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.2), radius: 10, x: 0, y: 5)
    }

    var statusColor: Color {
        switch trip.status {
        case "completed": return .green
        case "cancelled": return .orange
        case "overdue": return .red
        case "active": return .blue
        default: return .gray
        }
    }
}
