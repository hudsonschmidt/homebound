import SwiftUI
import MapKit
import CoreLocation

/// Map view showing a friend's trip with destination, start location, check-in markers, and live location
struct FriendTripMapView: View {
    let trip: FriendActiveTrip
    @EnvironmentObject var session: Session
    @State private var currentTrip: FriendActiveTrip
    @State private var mapPosition: MapCameraPosition = .automatic
    @Environment(\.dismiss) private var dismiss
    private let pollingInterval: TimeInterval = 10

    init(trip: FriendActiveTrip) {
        self.trip = trip
        _currentTrip = State(initialValue: trip)
        _mapPosition = State(initialValue: Self.initialMapPosition(for: trip))
    }

    /// Calculate initial map position that fits all markers with comfortable padding
    private static func initialMapPosition(for trip: FriendActiveTrip) -> MapCameraPosition {
        var coordinates: [CLLocationCoordinate2D] = []

        if let coord = trip.destinationCoordinate {
            coordinates.append(coord)
        }
        if let coord = trip.startCoordinate {
            coordinates.append(coord)
        }
        if let checkins = trip.checkin_locations {
            coordinates.append(contentsOf: checkins.compactMap { $0.coordinate })
        }
        if let liveLocation = trip.live_location {
            coordinates.append(liveLocation.coordinate)
        }

        guard !coordinates.isEmpty else {
            return .automatic
        }

        // Calculate bounding box
        let minLat = coordinates.map { $0.latitude }.min()!
        let maxLat = coordinates.map { $0.latitude }.max()!
        let minLon = coordinates.map { $0.longitude }.min()!
        let maxLon = coordinates.map { $0.longitude }.max()!

        let center = CLLocationCoordinate2D(
            latitude: (minLat + maxLat) / 2,
            longitude: (minLon + maxLon) / 2
        )

        // Calculate span with padding (add 50% extra space on each side)
        let latDelta = max((maxLat - minLat) * 1.5, 0.01)  // Minimum 0.01 degrees (~1km)
        let lonDelta = max((maxLon - minLon) * 1.5, 0.01)

        let region = MKCoordinateRegion(
            center: center,
            span: MKCoordinateSpan(latitudeDelta: latDelta, longitudeDelta: lonDelta)
        )

        return .region(region)
    }

    // MARK: - Map Content
    @MapContentBuilder
    private var mapContent: some MapContent {
        // Destination pin
        if let coord = currentTrip.destinationCoordinate {
            Annotation(currentTrip.location_text ?? "Destination", coordinate: coord) {
                DestinationPin(activityIcon: currentTrip.activity_icon, primaryColor: currentTrip.primaryColor)
            }
        }

        // Start location pin
        if let coord = currentTrip.startCoordinate {
            Annotation(currentTrip.start_location_text ?? "Start", coordinate: coord) {
                StartPin()
            }
        }

        // Check-in location markers (numbered, most recent first)
        if let checkins = currentTrip.checkin_locations {
            ForEach(Array(checkins.enumerated()), id: \.element.id) { index, checkin in
                if let coord = checkin.coordinate {
                    Annotation(checkin.location_name ?? "Check-in \(index + 1)", coordinate: coord) {
                        CheckinPin(number: index + 1, isLatest: index == 0)
                    }
                }
            }
        }

        // Live location pin
        if let liveLocation = currentTrip.live_location {
            Annotation("\(currentTrip.owner.first_name) (Live)", coordinate: liveLocation.coordinate) {
                LiveLocationPin(ownerName: currentTrip.owner.first_name)
            }
        }

        // Draw polyline connecting check-ins if there are multiple
        if let checkins = currentTrip.checkin_locations,
           checkins.count > 1 {
            let coordinates = checkins.compactMap { $0.coordinate }
            if coordinates.count > 1 {
                MapPolyline(coordinates: coordinates)
                    .stroke(.blue.opacity(0.5), lineWidth: 2)
            }
        }
    }

    var body: some View {
        NavigationStack {
            Map(position: $mapPosition) {
                mapContent
            }
            .mapStyle(.standard)
            .navigationTitle("\(currentTrip.owner.first_name)'s Trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    if currentTrip.live_location != nil {
                        Button {
                            centerOnLiveLocation()
                        } label: {
                            Image(systemName: "location.fill")
                        }
                    }
                }
            }
            .overlay(alignment: .bottom) {
                // Trip info card at bottom
                TripInfoCard(trip: currentTrip)
                    .padding()
            }
            .task {
                // Poll for live location updates while map is open
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: UInt64(pollingInterval * 1_000_000_000))
                    guard !Task.isCancelled else { break }
                    await refreshTripData()
                }
            }
        }
    }

    private func centerOnLiveLocation() {
        guard let liveLocation = currentTrip.live_location else { return }
        withAnimation {
            mapPosition = .region(MKCoordinateRegion(
                center: liveLocation.coordinate,
                span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
            ))
        }
    }

    private func refreshTripData() async {
        // Reload active trips and find this one
        _ = await session.loadFriendActiveTrips()
        if let updated = session.friendActiveTrips.first(where: { $0.id == trip.id }) {
            await MainActor.run {
                currentTrip = updated
            }
        }
    }
}

// MARK: - Map Pin Components

/// Destination pin with activity icon
private struct DestinationPin: View {
    let activityIcon: String
    let primaryColor: Color

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Circle()
                    .fill(primaryColor)
                    .frame(width: 36, height: 36)
                Text(activityIcon)
                    .font(.system(size: 18))
            }
            .shadow(radius: 3)

            // Pin point
            Triangle()
                .fill(primaryColor)
                .frame(width: 12, height: 8)
                .offset(y: -2)
        }
    }
}

/// Start location pin
private struct StartPin: View {
    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Circle()
                    .fill(.gray)
                    .frame(width: 28, height: 28)
                Image(systemName: "flag.fill")
                    .font(.system(size: 14))
                    .foregroundStyle(.white)
            }
            .shadow(radius: 2)

            Triangle()
                .fill(.gray)
                .frame(width: 10, height: 6)
                .offset(y: -2)
        }
    }
}

/// Check-in location pin with number
private struct CheckinPin: View {
    let number: Int
    let isLatest: Bool

    var body: some View {
        ZStack {
            Circle()
                .fill(isLatest ? .green : .green.opacity(0.7))
                .frame(width: isLatest ? 32 : 26, height: isLatest ? 32 : 26)
            if isLatest {
                Image(systemName: "checkmark")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.white)
            } else {
                Text("\(number)")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.white)
            }
        }
        .shadow(radius: 2)
    }
}

/// Live location pin with pulse animation
private struct LiveLocationPin: View {
    let ownerName: String
    @State private var isPulsing = false

    var body: some View {
        ZStack {
            // Pulsing outer ring
            Circle()
                .stroke(Color.blue.opacity(0.3), lineWidth: 2)
                .frame(width: 44, height: 44)
                .scaleEffect(isPulsing ? 1.3 : 1.0)
                .opacity(isPulsing ? 0 : 0.8)

            // Main circle
            Circle()
                .fill(.blue)
                .frame(width: 32, height: 32)

            Image(systemName: "location.fill")
                .font(.system(size: 16))
                .foregroundStyle(.white)
        }
        .shadow(radius: 3)
        .onAppear {
            withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: false)) {
                isPulsing = true
            }
        }
    }
}

/// Triangle shape for pin points
private struct Triangle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.closeSubpath()
        return path
    }
}

// MARK: - Trip Info Card

/// Bottom card showing trip information
private struct TripInfoCard: View {
    let trip: FriendActiveTrip

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                Text(trip.activity_icon)
                    .font(.title2)
                VStack(alignment: .leading, spacing: 2) {
                    Text(trip.title)
                        .font(.headline)
                    Text("\(trip.owner.fullName)'s trip")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                StatusBadge(status: trip.status)
            }

            Divider()

            // Location info
            if let destination = trip.location_text {
                Label(destination, systemImage: "mappin.circle.fill")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Last check-in info
            if let lastCheckin = trip.lastCheckinLocation {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    if let name = lastCheckin.location_name {
                        Text("Last seen: \(name)")
                    } else {
                        Text("Last check-in")
                    }
                    Spacer()
                    if let date = lastCheckin.timestampDate {
                        Text(date, style: .relative)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            // Live location indicator
            if let liveLocation = trip.live_location {
                HStack {
                    Image(systemName: "location.fill")
                        .foregroundStyle(.blue)
                    Text("Live location")
                    Spacer()
                    if let date = liveLocation.timestampDate {
                        Text(date, style: .relative)
                            .foregroundStyle(.secondary)
                    }
                }
                .font(.caption)
                .foregroundStyle(.blue)
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

/// Status badge for trip
private struct StatusBadge: View {
    let status: String

    private var color: Color {
        switch status {
        case "active": return .green
        case "overdue", "overdue_notified": return .red
        case "planned": return .blue
        default: return .gray
        }
    }

    private var text: String {
        switch status {
        case "active": return "ACTIVE"
        case "overdue", "overdue_notified": return "OVERDUE"
        case "planned": return "PLANNED"
        default: return status.uppercased()
        }
    }

    var body: some View {
        Text(text)
            .font(.caption2)
            .fontWeight(.bold)
            .foregroundStyle(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color)
            .clipShape(Capsule())
    }
}
