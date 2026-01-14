import SwiftUI
import MapKit

/// Full-screen detail view for past trips
struct TripDetailView: View {
    let tripId: Int
    @EnvironmentObject var session: Session
    @State private var timelineEvents: [TimelineEvent] = []
    @State private var isLoadingTimeline = false
    @State private var isLoadingContacts = false
    @State private var isLoadingFriends = false
    @State private var contactsLoaded = false
    @State private var friendsLoaded = false
    @State private var participants: [TripParticipant] = []
    @State private var isLoadingParticipants = false
    @State private var myTripContacts: [TripContact] = []
    @State private var isLoadingMyContacts = false

    // Computed property to always get fresh trip from session
    private var trip: Trip? {
        session.allTrips.first(where: { $0.id == tripId })
    }

    var body: some View {
        Group {
            if let trip = trip {
                ScrollView {
                    VStack(spacing: 16) {
                        // Map Section
                        TripDetailMapSection(
                            trip: trip,
                            events: timelineEvents,
                            participants: trip.is_group_trip ? participants : []
                        )

                        // Summary Card
                        TripDetailSummaryCard(trip: trip)

                        // Timeline Section
                        TripDetailTimelineSection(events: timelineEvents, isLoading: isLoadingTimeline)

                        // Safety Contacts Section
                        TripDetailContactsSection(
                            trip: trip,
                            myContacts: myTripContacts,
                            isLoading: isLoadingMyContacts,
                            contactsReady: contactsLoaded && friendsLoaded
                        )

                        // Participants Section (for group trips)
                        if trip.is_group_trip {
                            TripDetailParticipantsSection(
                                participants: participants,
                                isLoading: isLoadingParticipants,
                                showLocationSharing: trip.group_settings?.share_locations_between_participants ?? false
                            )
                        }

                        // Statistics Section
                        TripDetailStatsSection(trip: trip, events: timelineEvents)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 24)
                }
                .background(Color(.systemBackground))
                .navigationTitle("Trip Details")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        ShareLink(item: generateShareSummary(for: trip)) {
                            Image(systemName: "square.and.arrow.up")
                        }
                    }
                }
            } else {
                ContentUnavailableView(
                    "Trip Not Found",
                    systemImage: "exclamationmark.triangle",
                    description: Text("This trip may have been deleted.")
                )
            }
        }
        .task {
            await loadAllData()
        }
        .refreshable {
            await refreshAllData()
        }
        .onChange(of: session.timelineLastUpdated) { _, _ in
            // Realtime event detected - refresh timeline for updated check-in count
            Task {
                await loadTimelineEvents()
                await loadParticipantsIfGroupTrip()
            }
        }
    }

    private func loadAllData() async {
        // Load timeline, contacts, friends, participants, and my-contacts in parallel
        async let timelineTask: Void = loadTimelineEvents()
        async let contactsTask: Void = ensureContactsLoaded()
        async let friendsTask: Void = ensureFriendsLoaded()
        async let participantsTask: Void = loadParticipantsIfGroupTrip()
        async let myContactsTask: Void = loadMyContactsIfGroupTrip()
        _ = await (timelineTask, contactsTask, friendsTask, participantsTask, myContactsTask)
    }

    private func loadMyContactsIfGroupTrip() async {
        guard let trip = trip, trip.is_group_trip else { return }
        await MainActor.run { isLoadingMyContacts = true }
        let contacts = await session.getMyTripContacts(tripId: tripId)
        await MainActor.run {
            myTripContacts = contacts
            isLoadingMyContacts = false
        }
    }

    private func loadParticipantsIfGroupTrip() async {
        guard let trip = trip, trip.is_group_trip else {
            debugLog("[TripDetail] Not loading participants: trip=\(trip != nil), isGroupTrip=\(trip?.is_group_trip ?? false)")
            return
        }
        debugLog("[TripDetail] Loading participants for group trip \(tripId)")
        await MainActor.run { isLoadingParticipants = true }
        if let response = await session.getParticipants(tripId: tripId) {
            debugLog("[TripDetail] Loaded \(response.participants.count) participants")
            await MainActor.run {
                participants = response.participants
            }
        } else {
            debugLog("[TripDetail] Failed to load participants - API returned nil")
        }
        await MainActor.run { isLoadingParticipants = false }
    }

    private func refreshAllData() async {
        // Force refresh all data from network
        async let timelineTask: Void = loadTimelineEvents()
        async let contactsTask: [Contact] = session.loadContacts()
        async let friendsTask: [Friend] = session.loadFriends()
        async let participantsTask: Void = loadParticipantsIfGroupTrip()
        async let myContactsTask: Void = loadMyContactsIfGroupTrip()
        _ = await (timelineTask, contactsTask, friendsTask, participantsTask, myContactsTask)
    }

    private func ensureContactsLoaded() async {
        await MainActor.run { isLoadingContacts = true }
        _ = await session.loadContacts()
        await MainActor.run {
            isLoadingContacts = false
            contactsLoaded = true
        }
    }

    private func ensureFriendsLoaded() async {
        await MainActor.run { isLoadingFriends = true }
        _ = await session.loadFriends()
        await MainActor.run {
            isLoadingFriends = false
            friendsLoaded = true
        }
    }

    private func loadTimelineEvents() async {
        await MainActor.run { isLoadingTimeline = true }
        let events = await session.loadTimeline(planId: tripId)
        await MainActor.run {
            timelineEvents = events
            isLoadingTimeline = false
        }

        // Debug: Log timeline events
        debugLog("[TripDetailView] Loaded \(events.count) timeline events for trip \(tripId)")
        for event in events {
            debugLog("[TripDetailView] Event: kind=\(event.kind), lat=\(String(describing: event.lat)), lon=\(String(describing: event.lon))")
        }
        let checkins = events.filter { $0.kind == "checkin" && $0.lat != nil && $0.lon != nil }
        debugLog("[TripDetailView] Check-ins with coordinates: \(checkins.count)")
    }

    private func generateShareSummary(for trip: Trip) -> String {
        var summary = "\(trip.activity.icon) \(trip.title)\n\n"
        summary += "Status: \(trip.status.capitalized)\n"

        if let location = trip.location_text {
            summary += "Location: \(location)\n"
        }

        summary += "Started: \(DateUtils.formatDateTime(trip.start_at, inTimezone: trip.start_timezone))\n"

        if let completedAt = trip.completed_at {
            summary += "Completed: \(DateUtils.formatDateTime(completedAt, inTimezone: trip.eta_timezone))\n"

            if let duration = DateUtils.formatDuration(from: trip.start_at, to: completedAt) {
                summary += "Duration: \(duration)\n"
            }
        }

        let checkinCount = timelineEvents.filter { $0.kind == "checkin" }.count
        if checkinCount > 0 {
            summary += "Check-ins: \(checkinCount)\n"
        }

        summary += "\nShared via Homebound"
        return summary
    }
}

// MARK: - Map Section

private struct TripDetailMapSection: View {
    let trip: Trip
    let events: [TimelineEvent]
    let participants: [TripParticipant]
    @EnvironmentObject var session: Session
    @ObservedObject private var locationManager = LocationManager.shared
    @State private var mapPosition: MapCameraPosition = .automatic

    // Check-in events sorted chronologically (oldest first for correct numbering)
    private var checkinEvents: [TimelineEvent] {
        events.filter { $0.kind == "checkin" && $0.lat != nil && $0.lon != nil }
            .sorted { e1, e2 in
                guard let d1 = e1.atDate, let d2 = e2.atDate else { return false }
                return d1 < d2
            }
    }

    // Check if location sharing is enabled for this group trip
    private var shouldShowParticipantLocations: Bool {
        guard trip.is_group_trip else { return false }
        return trip.group_settings?.share_locations_between_participants ?? false
    }

    // Participants with valid locations (excluding current user to avoid duplicate pins)
    private var participantsWithLocations: [TripParticipant] {
        guard shouldShowParticipantLocations else { return [] }
        return participants.filter { participant in
            // Must have valid location and be accepted
            guard participant.last_lat != nil && participant.last_lon != nil && participant.status == "accepted" else {
                return false
            }
            // Exclude current user (they see their own location separately)
            if let currentUserId = session.userId, participant.user_id == currentUserId {
                return false
            }
            return true
        }
    }

    // Colors for participant pins (cycle through these)
    private let participantColors: [Color] = [
        .blue, .purple, .orange, .pink, .cyan, .mint, .indigo
    ]

    private func colorForParticipant(at index: Int) -> Color {
        participantColors[index % participantColors.count]
    }

    private var allCoordinates: [CLLocationCoordinate2D] {
        var coords: [CLLocationCoordinate2D] = []

        // User's current location (always included for group trips)
        if trip.is_group_trip, locationManager.isAuthorized, let userLocation = locationManager.currentLocation {
            coords.append(userLocation)
        }

        // Start location
        if trip.has_separate_locations, let lat = trip.start_lat, let lng = trip.start_lng {
            coords.append(CLLocationCoordinate2D(latitude: lat, longitude: lng))
        }

        // Check-in locations
        for event in checkinEvents {
            if let lat = event.lat, let lon = event.lon {
                coords.append(CLLocationCoordinate2D(latitude: lat, longitude: lon))
            }
        }

        // Participant locations (only if sharing is enabled)
        for participant in participantsWithLocations {
            if let lat = participant.last_lat, let lon = participant.last_lon {
                coords.append(CLLocationCoordinate2D(latitude: lat, longitude: lon))
            }
        }

        // Destination
        if let lat = trip.location_lat, let lng = trip.location_lng {
            coords.append(CLLocationCoordinate2D(latitude: lat, longitude: lng))
        }

        return coords
    }

    private var hasMapData: Bool {
        let hasUserLocation = trip.is_group_trip && locationManager.isAuthorized && locationManager.currentLocation != nil
        return trip.location_lat != nil || trip.start_lat != nil || !checkinEvents.isEmpty || !participantsWithLocations.isEmpty || hasUserLocation
    }

    private func calculateRegion() -> MKCoordinateRegion {
        guard !allCoordinates.isEmpty else {
            return MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: 0, longitude: 0),
                span: MKCoordinateSpan(latitudeDelta: 0.1, longitudeDelta: 0.1)
            )
        }

        let lats = allCoordinates.map { $0.latitude }
        let lons = allCoordinates.map { $0.longitude }

        let center = CLLocationCoordinate2D(
            latitude: (lats.min()! + lats.max()!) / 2,
            longitude: (lons.min()! + lons.max()!) / 2
        )

        let span = MKCoordinateSpan(
            latitudeDelta: max((lats.max()! - lats.min()!) * 1.5, 0.01),
            longitudeDelta: max((lons.max()! - lons.min()!) * 1.5, 0.01)
        )

        return MKCoordinateRegion(center: center, span: span)
    }

    var body: some View {
        if hasMapData {
            Map(position: $mapPosition) {
                // Start location pin
                if trip.has_separate_locations, let lat = trip.start_lat, let lng = trip.start_lng {
                    Annotation(trip.start_location_text ?? "Start", coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng)) {
                        DetailStartPin()
                    }
                }

                // Check-in pins (numbered, chronological)
                ForEach(Array(checkinEvents.enumerated()), id: \.element.id) { index, event in
                    if let lat = event.lat, let lon = event.lon {
                        Annotation("Check-in \(index + 1)", coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon)) {
                            DetailCheckinPin(number: index + 1)
                        }
                    }
                }

                // User's current location (always shown for group trips)
                if trip.is_group_trip, locationManager.isAuthorized, let userLocation = locationManager.currentLocation {
                    Annotation("My Location", coordinate: userLocation) {
                        UserLocationPin()
                    }
                }

                // Participant location pins (only shown if sharing is enabled by group leader)
                ForEach(Array(participantsWithLocations.enumerated()), id: \.element.id) { index, participant in
                    if let lat = participant.last_lat, let lon = participant.last_lon {
                        Annotation(participant.displayName, coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon)) {
                            ParticipantLocationPin(
                                name: participant.displayName,
                                color: colorForParticipant(at: index),
                                isOwner: participant.role == "owner"
                            )
                        }
                    }
                }

                // Destination pin
                if let lat = trip.location_lat, let lng = trip.location_lng {
                    Annotation(trip.location_text ?? "Destination", coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng)) {
                        DetailDestinationPin(activityIcon: trip.activity.icon, primaryColor: Color(hex: trip.activity.colors.primary) ?? .hbBrand)
                    }
                }

                // Polyline connecting points
                if allCoordinates.count > 1 {
                    MapPolyline(coordinates: allCoordinates)
                        .stroke(.blue.opacity(0.5), lineWidth: 2)
                }
            }
            .mapStyle(.standard)
            .frame(height: 250)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .id(events.count)  // Force complete re-render when events change
            .onAppear {
                mapPosition = .region(calculateRegion())
            }
            .onChange(of: events.count) {
                mapPosition = .region(calculateRegion())
            }
            .task {
                // Send location updates for group trips with sharing enabled
                await sendGroupTripLocationUpdates()
            }
        }
    }

    /// Send periodic location updates for group trips (less frequent than live location)
    private func sendGroupTripLocationUpdates() async {
        // Only for active group trips with location sharing enabled
        guard trip.is_group_trip,
              trip.status == "active",
              trip.group_settings?.share_locations_between_participants == true,
              locationManager.isAuthorized else {
            return
        }

        let updateInterval: UInt64 = 60_000_000_000 // 60 seconds (less frequent than live location)

        // Send initial location update
        await sendLocationUpdate()

        // Poll for location updates while map is visible
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: updateInterval)
            guard !Task.isCancelled else { break }
            await sendLocationUpdate()
        }
    }

    /// Send current location to server for group trip
    private func sendLocationUpdate() async {
        guard let userLocation = locationManager.currentLocation else { return }
        do {
            _ = try await session.updateLiveLocation(
                tripId: trip.id,
                latitude: userLocation.latitude,
                longitude: userLocation.longitude,
                altitude: nil,
                horizontalAccuracy: nil,
                speed: nil
            )
            debugLog("[GroupTripMap] Sent location update for trip \(trip.id)")
        } catch {
            debugLog("[GroupTripMap] Failed to send location: \(error.localizedDescription)")
        }
    }
}

// MARK: - Summary Card

private struct TripDetailSummaryCard: View {
    let trip: Trip

    private var primaryColor: Color {
        Color(hex: trip.activity.colors.primary) ?? .hbBrand
    }

    private var statusColor: Color {
        switch trip.status {
        case "active": return .orange
        case "completed": return .green
        case "overdue", "overdue_notified": return .red
        case "cancelled": return .gray
        default: return .gray
        }
    }

    private func formatDateTime(_ date: Date, timezone: String? = nil) -> String {
        let formatted = DateUtils.formatDateTime(date, inTimezone: timezone)
        if let tzId = timezone,
           let tz = TimeZone(identifier: tzId),
           tz != .current,
           let abbr = tz.abbreviation(for: date) {
            return "\(formatted) \(abbr)"
        }
        return formatted
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with icon, title, and status
            HStack(alignment: .top, spacing: 12) {
                Circle()
                    .fill(primaryColor.opacity(0.2))
                    .frame(width: 56, height: 56)
                    .overlay(
                        Text(trip.activity.icon)
                            .font(.title)
                    )

                VStack(alignment: .leading, spacing: 4) {
                    Text(trip.title)
                        .font(.title3)
                        .fontWeight(.semibold)
                        .lineLimit(2)

                    Text(trip.activity.name)
                        .font(.subheadline)
                        .foregroundStyle(primaryColor)
                        .fontWeight(.medium)
                }

                Spacer()

                Text(trip.status.capitalized)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(statusColor.opacity(0.2))
                    .foregroundStyle(statusColor)
                    .cornerRadius(8)
            }

            Divider()

            // Time info
            VStack(alignment: .leading, spacing: 8) {
                InfoRow(
                    icon: "arrow.right.circle.fill",
                    iconColor: .green,
                    label: "Started",
                    value: formatDateTime(trip.start_at, timezone: trip.start_timezone)
                )

                if trip.status == "completed" {
                    if let completedAt = trip.completed_at {
                        InfoRow(
                            icon: "checkmark.circle.fill",
                            iconColor: .blue,
                            label: "Finished",
                            value: formatDateTime(completedAt, timezone: trip.eta_timezone)
                        )
                    }
                } else {
                    InfoRow(
                        icon: "clock.fill",
                        iconColor: .orange,
                        label: "Expected",
                        value: formatDateTime(trip.eta_at, timezone: trip.eta_timezone)
                    )
                }

                // Duration
                if trip.status == "completed", let completedAt = trip.completed_at {
                    if let duration = DateUtils.formatDuration(from: trip.start_at, to: completedAt) {
                        InfoRow(
                            icon: "timer",
                            iconColor: .hbBrand,
                            label: "Duration",
                            value: duration
                        )
                    }
                }

                // Locations
                if trip.has_separate_locations, let startLocation = trip.start_location_text {
                    InfoRow(
                        icon: "figure.walk.departure",
                        iconColor: .green,
                        label: "Start",
                        value: startLocation
                    )
                }

                if let location = trip.location_text {
                    InfoRow(
                        icon: trip.has_separate_locations ? "flag.fill" : "location.fill",
                        iconColor: .red,
                        label: trip.has_separate_locations ? "Destination" : "Location",
                        value: location
                    )
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
    }
}

// MARK: - Timeline Section

private struct TripDetailTimelineSection: View {
    let events: [TimelineEvent]
    let isLoading: Bool

    private var sortedEvents: [TimelineEvent] {
        events.sorted { event1, event2 in
            guard let date1 = event1.atDate, let date2 = event2.atDate else { return false }
            return date1 < date2
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Timeline")
                .font(.headline)

            if isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .padding(.vertical, 8)
            } else if events.isEmpty {
                Text("No events recorded")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(sortedEvents.enumerated()), id: \.element.id) { index, event in
                        TimelineEventRow(event: event, isLast: index == sortedEvents.count - 1)
                    }
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
    }
}

private struct TimelineEventRow: View {
    let event: TimelineEvent
    let isLast: Bool

    private var eventIcon: String {
        switch event.kind {
        case "checkin": return "checkmark.circle.fill"
        case "checkout": return "flag.checkered"
        case "extended": return "plus.circle.fill"
        default: return "circle.fill"
        }
    }

    private var eventColor: Color {
        switch event.kind {
        case "checkin": return .green
        case "checkout": return .blue
        case "extended": return .orange
        default: return .gray
        }
    }

    private var eventTitle: String {
        // Get the actor's first name if available
        let actorName: String? = {
            guard let fullName = event.user_name, !fullName.isEmpty else { return nil }
            // Extract first name only
            return fullName.split(separator: " ").first.map(String.init)
        }()

        switch event.kind {
        case "checkin":
            if let name = actorName {
                return "\(name) checked in"
            }
            return "Checked in"
        case "checkout":
            if let name = actorName {
                return "\(name) checked out"
            }
            return "Checked out"
        case "extended":
            let extendedText: String
            if let minutes = event.extended_by {
                extendedText = "Extended by \(minutes) min"
            } else {
                extendedText = "Extended"
            }
            if let name = actorName {
                return "\(name): \(extendedText)"
            }
            return extendedText
        default:
            if let name = actorName {
                return "\(name): \(event.kind.capitalized)"
            }
            return event.kind.capitalized
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Timeline dot and line
            VStack(spacing: 0) {
                Circle()
                    .fill(eventColor)
                    .frame(width: 12, height: 12)

                if !isLast {
                    Rectangle()
                        .fill(Color(.separator))
                        .frame(width: 2)
                        .frame(maxHeight: .infinity)
                }
            }
            .frame(width: 12)

            // Event content
            VStack(alignment: .leading, spacing: 2) {
                Text(eventTitle)
                    .font(.subheadline)
                    .fontWeight(.medium)

                if let date = event.atDate {
                    Text(DateUtils.formatDateTime(date, inTimezone: nil))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if event.lat != nil && event.lon != nil {
                    Label("Location recorded", systemImage: "location.fill")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.bottom, isLast ? 0 : 16)

            Spacer()
        }
    }
}

// MARK: - Contacts Section

private struct TripDetailContactsSection: View {
    let trip: Trip
    let myContacts: [TripContact]
    let isLoading: Bool
    let contactsReady: Bool
    @EnvironmentObject var session: Session

    // For non-group trips, use trip's contact IDs
    private var friendContactIds: [Int] {
        [trip.friend_contact1, trip.friend_contact2, trip.friend_contact3].compactMap { $0 }
    }

    private var emailContactIds: [Int] {
        [trip.contact1, trip.contact2, trip.contact3].compactMap { $0 }
    }

    private var hasContacts: Bool {
        if trip.is_group_trip {
            return !myContacts.isEmpty
        }
        return !friendContactIds.isEmpty || !emailContactIds.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Safety Contacts")
                .font(.headline)

            if isLoading || (!trip.is_group_trip && !contactsReady) {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .padding(.vertical, 8)
            } else if !hasContacts {
                Text("No contacts assigned")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else if trip.is_group_trip {
                // Group trip: use myContacts from /my-contacts endpoint
                VStack(spacing: 8) {
                    ForEach(myContacts) { contact in
                        if contact.isFriendContact {
                            TripContactRow(
                                name: contact.displayName,
                                icon: "bell.fill",
                                iconColor: .blue,
                                notificationType: "Push notification"
                            )
                        } else {
                            TripContactRow(
                                name: contact.displayName,
                                icon: "envelope.fill",
                                iconColor: .orange,
                                notificationType: "Email"
                            )
                        }
                    }
                }
            } else {
                // Non-group trip: use trip's contact IDs (existing behavior)
                VStack(spacing: 8) {
                    // Friend contacts (push notifications)
                    ForEach(friendContactIds, id: \.self) { userId in
                        if let friend = session.friends.first(where: { $0.user_id == userId }) {
                            TripContactRow(
                                name: friend.fullName,
                                icon: "bell.fill",
                                iconColor: .blue,
                                notificationType: "Push notification"
                            )
                        } else {
                            TripContactRow(
                                name: "Friend (removed)",
                                icon: "person.fill.questionmark",
                                iconColor: .gray,
                                notificationType: "Push notification"
                            )
                        }
                    }

                    // Email contacts
                    ForEach(emailContactIds, id: \.self) { contactId in
                        if let contact = session.contacts.first(where: { $0.id == contactId }) {
                            TripContactRow(
                                name: contact.name,
                                icon: "envelope.fill",
                                iconColor: .orange,
                                notificationType: "Email"
                            )
                        } else {
                            TripContactRow(
                                name: "Contact (removed)",
                                icon: "person.fill.questionmark",
                                iconColor: .gray,
                                notificationType: "Email"
                            )
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
    }
}

private struct TripContactRow: View {
    let name: String
    let icon: String
    let iconColor: Color
    let notificationType: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .foregroundStyle(iconColor)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.subheadline)
                    .fontWeight(.medium)

                Text(notificationType)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
    }
}

// MARK: - Participants Section (for group trips)

private struct TripDetailParticipantsSection: View {
    let participants: [TripParticipant]
    let isLoading: Bool
    let showLocationSharing: Bool

    var acceptedParticipants: [TripParticipant] {
        participants.filter { $0.status == "accepted" }
    }

    var leftParticipants: [TripParticipant] {
        participants.filter { $0.status == "left" }
    }

    var pendingParticipants: [TripParticipant] {
        participants.filter { $0.status == "invited" }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Image(systemName: "person.3.fill")
                    .foregroundStyle(Color.hbBrand)
                Text("Participants")
                    .font(.headline)

                Spacer()

                Text("\(acceptedParticipants.count) joined")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Location sharing indicator
            if showLocationSharing {
                HStack(spacing: 4) {
                    Image(systemName: "location.fill")
                        .font(.caption2)
                    Text("Location sharing enabled")
                        .font(.caption2)
                }
                .foregroundStyle(.blue)
            }

            if isLoading {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .padding(.vertical, 20)
            } else if participants.isEmpty {
                Text("No participants yet")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 20)
            } else {
                VStack(spacing: 8) {
                    // Accepted participants
                    ForEach(acceptedParticipants, id: \.id) { participant in
                        ParticipantRow(participant: participant, showLocation: showLocationSharing)
                    }

                    // Left participants
                    if !leftParticipants.isEmpty {
                        Divider()
                            .padding(.vertical, 4)

                        Text("Left")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        ForEach(leftParticipants, id: \.id) { participant in
                            ParticipantRow(participant: participant, showLocation: false)
                        }
                    }

                    // Pending participants
                    if !pendingParticipants.isEmpty {
                        Divider()
                            .padding(.vertical, 4)

                        Text("Pending")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        ForEach(pendingParticipants, id: \.id) { participant in
                            ParticipantRow(participant: participant, showLocation: false)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
    }
}

private struct ParticipantRow: View {
    let participant: TripParticipant
    let showLocation: Bool

    private var statusColor: Color {
        switch participant.status {
        case "accepted": return .green
        case "invited": return .orange
        case "declined", "left": return .secondary
        default: return .secondary
        }
    }

    private var statusIcon: String {
        switch participant.status {
        case "accepted": return "checkmark.circle.fill"
        case "invited": return "hourglass"
        case "declined": return "xmark.circle"
        case "left": return "arrow.right.circle"
        default: return "circle"
        }
    }

    private var hasLocation: Bool {
        participant.last_lat != nil && participant.last_lon != nil
    }

    var body: some View {
        HStack(spacing: 12) {
            // Profile photo or initials
            if let photoUrl = participant.profile_photo_url, let url = URL(string: photoUrl) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                } placeholder: {
                    initialsCircle
                }
                .frame(width: 36, height: 36)
                .clipShape(Circle())
            } else {
                initialsCircle
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(participant.displayName)
                        .font(.subheadline)

                    if participant.role == "owner" {
                        Text("Owner")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.hbBrand.opacity(0.2))
                            .foregroundStyle(Color.hbBrand)
                            .cornerRadius(4)
                    }
                }

                // Status-dependent info
                if participant.status == "left", let leftAt = participant.leftAtDate {
                    Text("Left on \(leftAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else if showLocation && hasLocation, let lastCheckin = participant.lastCheckinAtDate {
                    // Show location timestamp when sharing is enabled
                    HStack(spacing: 4) {
                        Image(systemName: "location.fill")
                            .font(.caption2)
                        Text("Updated \(lastCheckin, style: .relative) ago")
                    }
                    .font(.caption2)
                    .foregroundStyle(.blue)
                } else if let lastCheckin = participant.lastCheckinAtDate {
                    Text("Last check-in: \(lastCheckin.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Location indicator (when sharing enabled and has location)
            if showLocation && hasLocation {
                Image(systemName: "location.fill")
                    .font(.caption)
                    .foregroundStyle(.blue)
            }

            // Status indicator
            Image(systemName: statusIcon)
                .font(.title3)
                .foregroundStyle(statusColor)
        }
        .padding(.vertical, 4)
    }

    private var initialsCircle: some View {
        let initials = participant.displayName.split(separator: " ")
            .prefix(2)
            .compactMap { $0.first }
            .map { String($0) }
            .joined()
            .uppercased()

        return Circle()
            .fill(Color.hbBrand.opacity(0.2))
            .frame(width: 36, height: 36)
            .overlay {
                Text(initials.isEmpty ? "?" : initials)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(Color.hbBrand)
            }
    }
}

// MARK: - Statistics Section

private struct TripDetailStatsSection: View {
    let trip: Trip
    let events: [TimelineEvent]

    private var checkinCount: Int {
        events.filter { $0.kind == "checkin" }.count
    }

    private var durationString: String? {
        if trip.status == "completed", let completedAt = trip.completed_at {
            return DateUtils.formatDuration(from: trip.start_at, to: completedAt)
        }
        return nil
    }

    private var averageCheckinInterval: String? {
        let checkins = events.filter { $0.kind == "checkin" }.compactMap { $0.atDate }.sorted()
        guard checkins.count >= 2 else { return nil }

        var totalInterval: TimeInterval = 0
        for i in 1..<checkins.count {
            totalInterval += checkins[i].timeIntervalSince(checkins[i-1])
        }

        let avgSeconds = totalInterval / Double(checkins.count - 1)
        let avgMinutes = Int(avgSeconds / 60)

        if avgMinutes < 60 {
            return "\(avgMinutes) min"
        } else {
            let hours = avgMinutes / 60
            let mins = avgMinutes % 60
            return mins > 0 ? "\(hours)h \(mins)m" : "\(hours)h"
        }
    }

    private var distanceTraveled: String? {
        // Show distance if we have both start and destination coordinates
        guard let startLat = trip.start_lat,
              let startLng = trip.start_lng,
              let endLat = trip.location_lat,
              let endLng = trip.location_lng else {
            return nil
        }

        let startLocation = CLLocation(latitude: startLat, longitude: startLng)
        let endLocation = CLLocation(latitude: endLat, longitude: endLng)
        let distanceMeters = startLocation.distance(from: endLocation)

        // Don't show if distance is essentially zero (same location)
        guard distanceMeters > 10 else { return nil }

        let distanceMiles = distanceMeters / 1609.34
        if distanceMiles < 0.1 {
            return String(format: "%.0f ft", distanceMeters * 3.281)
        } else {
            return String(format: "%.1f mi", distanceMiles)
        }
    }

    private var hasAnyStats: Bool {
        durationString != nil || distanceTraveled != nil || checkinCount > 0 || averageCheckinInterval != nil || trip.grace_minutes > 0
    }

    var body: some View {
        if hasAnyStats {
            VStack(alignment: .leading, spacing: 12) {
                Text("Statistics")
                    .font(.headline)

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    if let duration = durationString {
                        StatBox(icon: "timer", label: "Duration", value: duration)
                    }

                    if let distance = distanceTraveled {
                        StatBox(icon: "arrow.left.and.right", label: "Distance", value: distance)
                    }

                    if checkinCount > 0 {
                        StatBox(icon: "checkmark.circle.fill", label: "Check-ins", value: "\(checkinCount)")
                    }

                    if let avgInterval = averageCheckinInterval {
                        StatBox(icon: "clock.arrow.circlepath", label: "Avg Interval", value: avgInterval)
                    }

                    if trip.grace_minutes > 0 {
                        StatBox(icon: "clock.badge.checkmark", label: "Grace Period", value: "\(trip.grace_minutes) min")
                    }
                }
            }
            .padding(16)
            .background(Color(.secondarySystemBackground))
            .cornerRadius(16)
        }
    }
}

private struct StatBox: View {
    let icon: String
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(Color.hbBrand)

            Text(value)
                .font(.headline)

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Color(.tertiarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - Map Pin Components (duplicated from FriendTripMapView for now)

private struct DetailDestinationPin: View {
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

            DetailTriangle()
                .fill(primaryColor)
                .frame(width: 12, height: 8)
                .offset(y: -2)
        }
    }
}

private struct DetailStartPin: View {
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

            DetailTriangle()
                .fill(.gray)
                .frame(width: 10, height: 6)
                .offset(y: -2)
        }
    }
}

private struct DetailCheckinPin: View {
    let number: Int

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Circle()
                    .fill(.green)
                    .frame(width: 32, height: 32)
                Text("\(number)")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.white)
            }
            .shadow(color: .black.opacity(0.3), radius: 3, x: 0, y: 2)

            // Pin point
            Image(systemName: "triangle.fill")
                .font(.system(size: 10))
                .foregroundStyle(.green)
                .rotationEffect(.degrees(180))
                .offset(y: -3)
        }
    }
}

/// User's current location pin (always shown on group trip maps)
private struct UserLocationPin: View {
    var body: some View {
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

private struct ParticipantLocationPin: View {
    let name: String
    let color: Color
    let isOwner: Bool

    private var initials: String {
        name.split(separator: " ")
            .prefix(2)
            .compactMap { $0.first }
            .map { String($0) }
            .joined()
            .uppercased()
    }

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Circle()
                    .fill(color)
                    .frame(width: 36, height: 36)

                Text(initials.isEmpty ? "?" : initials)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.white)

                // Owner crown badge
                if isOwner {
                    Image(systemName: "crown.fill")
                        .font(.system(size: 10))
                        .foregroundStyle(.yellow)
                        .offset(x: 12, y: -12)
                }
            }
            .shadow(color: .black.opacity(0.3), radius: 3, x: 0, y: 2)

            // Pin point
            Image(systemName: "triangle.fill")
                .font(.system(size: 10))
                .foregroundStyle(color)
                .rotationEffect(.degrees(180))
                .offset(y: -3)
        }
    }
}

private struct DetailTriangle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.closeSubpath()
        return path
    }
}
