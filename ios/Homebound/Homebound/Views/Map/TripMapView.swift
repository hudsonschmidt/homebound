import SwiftUI
import MapKit

// MARK: - Trip Map View
struct TripMapView: View {
    @EnvironmentObject var session: Session
    @State private var trips: [PlanOut] = []
    @State private var isLoading = false
    @State private var region = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 37.7749, longitude: -122.4194),
        span: MKCoordinateSpan(latitudeDelta: 50, longitudeDelta: 50)
    )
    @State private var selectedActivity: String? = nil
    @State private var selectedTrip: PlanOut? = nil

    var tripsWithLocations: [PlanOut] {
        trips.filter { trip in
            guard let lat = trip.location_lat, let lon = trip.location_lng else { return false }
            return lat != 0.0 && lon != 0.0
        }
    }

    var filteredTrips: [PlanOut] {
        if let selectedActivity = selectedActivity {
            return tripsWithLocations.filter { $0.activity_type.lowercased() == selectedActivity.lowercased() }
        }
        return tripsWithLocations
    }

    var annotations: [TripAnnotation] {
        filteredTrips.map { trip in
            TripAnnotation(trip: trip)
        }
    }

    var activityFilters: [String] {
        let activities = Set(tripsWithLocations.map { $0.activity_type })
        return Array(activities).sorted()
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Map
                Map(coordinateRegion: $region, annotationItems: annotations) { annotation in
                    MapAnnotation(coordinate: annotation.coordinate) {
                        TripMapPin(annotation: annotation, isSelected: selectedTrip?.id == annotation.trip.id)
                            .onTapGesture {
                                withAnimation {
                                    selectedTrip = annotation.trip
                                }
                            }
                    }
                }
                .ignoresSafeArea(edges: .top)

                // Filter Controls
                VStack {
                    Spacer()

                    // Activity filter chips
                    if !activityFilters.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                // All button
                                FilterChip(
                                    label: "All",
                                    icon: "map.fill",
                                    isSelected: selectedActivity == nil,
                                    count: tripsWithLocations.count
                                ) {
                                    withAnimation {
                                        selectedActivity = nil
                                    }
                                }

                                // Activity filters
                                ForEach(activityFilters, id: \.self) { activity in
                                    let activityType = getActivityType(for: activity)
                                    let count = tripsWithLocations.filter { $0.activity_type == activity }.count

                                    FilterChip(
                                        label: activityType.displayName,
                                        icon: activityType.icon,
                                        isSelected: selectedActivity == activity,
                                        count: count
                                    ) {
                                        withAnimation {
                                            selectedActivity = selectedActivity == activity ? nil : activity
                                        }
                                    }
                                }
                            }
                            .padding(.horizontal)
                        }
                        .padding(.vertical, 8)
                        .background(.ultraThinMaterial)
                    }

                    // Selected trip card
                    if let trip = selectedTrip {
                        TripDetailCard(trip: trip) {
                            withAnimation {
                                selectedTrip = nil
                            }
                        }
                        .padding()
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }

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
                    Button(action: centerOnTrips) {
                        Image(systemName: "scope")
                            .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                    }
                }
            }
            .task {
                await loadTrips()
            }
        }
    }

    func loadTrips() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let loadedTrips: [PlanOut] = try await session.api.get(
                session.url("/api/v1/trips/"),
                bearer: session.accessToken
            )

            await MainActor.run {
                trips = loadedTrips
                centerOnTrips()
            }
        } catch {
            print("Failed to load trips: \(error)")
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

        withAnimation {
            region = MKCoordinateRegion(center: center, span: span)
        }
    }

    func getActivityType(for activityString: String) -> ActivityType {
        if let matched = ActivityType(rawValue: activityString.lowercased()) {
            return matched
        }
        let normalized = activityString.lowercased().replacingOccurrences(of: " ", with: "_")
        return ActivityType(rawValue: normalized) ?? .other
    }
}

// MARK: - Trip Annotation
struct TripAnnotation: Identifiable {
    let id: Int
    let trip: PlanOut
    let coordinate: CLLocationCoordinate2D

    init(trip: PlanOut) {
        self.id = trip.id
        self.trip = trip
        self.coordinate = CLLocationCoordinate2D(
            latitude: trip.location_lat ?? 0,
            longitude: trip.location_lng ?? 0
        )
    }
}

// MARK: - Trip Map Pin
struct TripMapPin: View {
    let annotation: TripAnnotation
    let isSelected: Bool

    var activity: ActivityType {
        if let matched = ActivityType(rawValue: annotation.trip.activity_type.lowercased()) {
            return matched
        }
        let normalized = annotation.trip.activity_type.lowercased().replacingOccurrences(of: " ", with: "_")
        return ActivityType(rawValue: normalized) ?? .other
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
            .background(isSelected ? (Color(hex: "#6C63FF") ?? .purple) : Color(.systemBackground))
            .foregroundStyle(isSelected ? .white : .primary)
            .cornerRadius(20)
            .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
        }
    }
}

// MARK: - Trip Detail Card
struct TripDetailCard: View {
    let trip: PlanOut
    let onDismiss: () -> Void

    var activity: ActivityType {
        if let matched = ActivityType(rawValue: trip.activity_type.lowercased()) {
            return matched
        }
        let normalized = trip.activity_type.lowercased().replacingOccurrences(of: " ", with: "_")
        return ActivityType(rawValue: normalized) ?? .other
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
                    Image(systemName: "xmark.circle.fill")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
            }

            // Details
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "calendar")
                        .font(.caption)
                    Text(trip.start_at.formatted(date: .abbreviated, time: .shortened))
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
