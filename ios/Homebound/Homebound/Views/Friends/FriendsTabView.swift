import SwiftUI
import Combine

// Notification for tab switch refresh
extension Notification.Name {
    static let friendsTabSelected = Notification.Name("friendsTabSelected")
}

/// Main Friends tab view showing friends list and invite options
struct FriendsTabView: View {
    @EnvironmentObject var session: Session
    @State private var showingInviteSheet = false
    @State private var showingQRScanner = false
    @State private var selectedFriend: Friend? = nil
    @State private var isLoading = false

    // Auto-refresh polling
    @State private var pollingTask: Task<Void, Never>? = nil
    @State private var lastTabRefresh: Date? = nil
    private let pollingInterval: TimeInterval = 30
    private let tabSwitchDebounce: TimeInterval = 5

    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground)
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Header
                        headerView

                        // Action buttons
                        actionButtonsView

                        // Friends list
                        friendsListView
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 100)
                }
                .scrollIndicators(.hidden)
                .refreshable {
                    await loadData()
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showingInviteSheet) {
                FriendInviteView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingQRScanner) {
                QRScannerView { token in
                    showingQRScanner = false
                    Task {
                        await handleScannedToken(token)
                    }
                }
            }
            .sheet(item: $selectedFriend) { friend in
                FriendProfileView(friend: friend)
                    .environmentObject(session)
                    .environmentObject(AppPreferences.shared)
            }
            .task {
                await loadData()
            }
            .onAppear {
                startPolling()
            }
            .onDisappear {
                stopPolling()
            }
            .onReceive(NotificationCenter.default.publisher(for: .friendsTabSelected)) { _ in
                let now = Date()
                if let last = lastTabRefresh, now.timeIntervalSince(last) < tabSwitchDebounce {
                    return // Skip if recently refreshed
                }
                lastTabRefresh = now
                Task { await loadData() }
            }
        }
    }

    // MARK: - Polling

    private func startPolling() {
        guard pollingTask == nil else { return }
        pollingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(pollingInterval * 1_000_000_000))
                guard !Task.isCancelled else { break }
                _ = await session.loadFriendActiveTrips()
            }
        }
    }

    private func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    // MARK: - Header

    var headerView: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Friends")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.hbBrand, Color.hbTeal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                Text("\(session.friends.count) friend\(session.friends.count == 1 ? "" : "s")")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.top, 8)
    }

    // MARK: - Action Buttons

    var actionButtonsView: some View {
        HStack(spacing: 12) {
            // Share invite link button
            Button(action: { showingInviteSheet = true }) {
                HStack {
                    Image(systemName: "link.badge.plus")
                    Text("Invite Friend")
                }
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Color.hbBrand)
                .cornerRadius(12)
            }

            // Scan QR code button
            Button(action: { showingQRScanner = true }) {
                HStack {
                    Image(systemName: "qrcode.viewfinder")
                    Text("Scan QR")
                }
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(Color.hbBrand)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Color.hbBrand.opacity(0.1))
                .cornerRadius(12)
            }
        }
    }

    // MARK: - Friends List

    var friendsListView: some View {
        VStack(alignment: .leading, spacing: 16) {
            if isLoading && session.friends.isEmpty {
                // Loading state
                HStack {
                    Spacer()
                    ProgressView()
                        .padding(.vertical, 40)
                    Spacer()
                }
            } else if session.friends.isEmpty {
                // Empty state
                emptyStateView
            } else {
                // Friends list with expandable trip cards
                ForEach(session.friends) { friend in
                    FriendRowWithTripsView(
                        friend: friend,
                        trips: tripsForFriend(friend),
                        onTap: { selectedFriend = friend }
                    )
                }
            }
        }
    }

    private func tripsForFriend(_ friend: Friend) -> [FriendActiveTrip] {
        session.friendActiveTrips.filter { $0.owner.user_id == friend.user_id }
    }

    // MARK: - Empty State

    var emptyStateView: some View {
        VStack(spacing: 16) {
            Image(systemName: "person.2.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("No Friends Yet")
                .font(.headline)

            Text("Invite friends to Homebound so they can be your safety contacts with instant push notifications.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button(action: { showingInviteSheet = true }) {
                Label("Invite Your First Friend", systemImage: "person.badge.plus")
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
                    .background(Color.hbBrand)
                    .cornerRadius(12)
            }
            .padding(.top, 8)
        }
        .padding(.vertical, 40)
        .padding(.horizontal)
    }

    // MARK: - Actions

    func loadData() async {
        isLoading = true
        async let friends = session.loadFriends()
        async let activeTrips = session.loadFriendActiveTrips()
        _ = await (friends, activeTrips)
        isLoading = false
    }

    func handleScannedToken(_ token: String) async {
        // First get the invite preview
        if let preview = await session.getFriendInvitePreview(token: token) {
            if preview.is_valid {
                // Accept the invite
                let friend = await session.acceptFriendInvite(token: token)
                if friend != nil {
                    // Reload friends list to ensure UI is updated
                    _ = await session.loadFriends()
                }
            } else {
                await MainActor.run {
                    session.lastError = "This invite has expired"
                }
            }
        }
    }
}

// MARK: - Friend Row View

struct FriendRowView: View {
    let friend: Friend

    var body: some View {
        HStack(spacing: 12) {
            // Profile photo or initial
            if let photoUrl = friend.profile_photo_url, let url = URL(string: photoUrl) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .scaledToFill()
                } placeholder: {
                    initialCircle
                }
                .frame(width: 50, height: 50)
                .clipShape(Circle())
            } else {
                initialCircle
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(friend.fullName)
                    .font(.headline)

                if let friendshipDate = friend.friendshipSinceDate {
                    Text("Friends since \(friendshipDate.formatted(date: .abbreviated, time: .omitted))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    var initialCircle: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [Color.hbBrand, Color.hbTeal],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 50, height: 50)
            .overlay(
                Text(friend.first_name.prefix(1).uppercased())
                    .font(.title2)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
            )
    }
}

// MARK: - Friend Row With Trips View

struct FriendRowWithTripsView: View {
    let friend: Friend
    let trips: [FriendActiveTrip]
    let onTap: () -> Void

    /// Trips that are active/overdue (auto-expanded with full details)
    var activeTrips: [FriendActiveTrip] {
        trips.filter { $0.isActiveStatus }
    }

    /// Planned trips (compact one-liner preview)
    var plannedTrips: [FriendActiveTrip] {
        trips.filter { $0.isPlanned }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Friend row (tap to view profile)
            FriendRowView(friend: friend)
                .onTapGesture { onTap() }

            // Active trips section - always expanded with full details
            if !activeTrips.isEmpty {
                VStack(spacing: 8) {
                    ForEach(activeTrips) { trip in
                        FriendActiveTripCardExpanded(trip: trip)
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 12)
                .background(Color(.tertiarySystemBackground))
            }

            // Planned trips section - compact one-liners
            if !plannedTrips.isEmpty {
                VStack(spacing: 4) {
                    ForEach(plannedTrips) { trip in
                        FriendPlannedTripCompact(trip: trip)
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color(.tertiarySystemBackground))
            }
        }
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - Friend Trip Card View

struct FriendTripCardView: View {
    let trip: FriendActiveTrip

    private var statusColor: Color {
        if trip.contactsNotified { return .red }
        if trip.isOverdue { return .orange }
        return .green
    }

    private var statusText: String {
        if trip.contactsNotified { return "OVERDUE" }
        if trip.isOverdue { return "CHECK IN" }
        if trip.isPlanned { return "PLANNED" }
        return "ACTIVE"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header: Icon + Title + Status
            HStack {
                Text(trip.activity_icon)
                    .font(.title3)

                VStack(alignment: .leading, spacing: 2) {
                    Text(trip.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)

                    Text(trip.activity_name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Status badge
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 6, height: 6)
                        .accessibilityHidden(true)
                    Text(statusText)
                        .font(.caption2)
                        .fontWeight(.bold)
                        .foregroundStyle(statusColor)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Friend's trip status: \(statusText)")
            }

            // Location
            if let location = trip.location_text, !location.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "location.fill")
                        .font(.caption2)
                    Text(location)
                        .font(.caption)
                        .lineLimit(1)
                }
                .foregroundStyle(.secondary)
            }

            // ETA (displayed in the trip's original timezone)
            if let etaDate = trip.etaDate {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.caption2)
                    Text("Expected by \(DateUtils.formatTime(etaDate, inTimezone: trip.timezone))")
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            // Notes (if any)
            if let notes = trip.notes, !notes.isEmpty {
                Text(notes)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding()
        .background(trip.primaryColor.opacity(0.1))
        .cornerRadius(8)
    }
}

// MARK: - Time State for Friend Trips

/// Time state for friend's trip countdown
enum FriendTripTimeState {
    case onTime       // Before ETA
    case graceWarning // Past ETA but within grace period
    case overdue      // Past grace period
}

// MARK: - Pulse Modifier (allowed animation per CLAUDE.md)

/// Pulse animation for status dot - one of the only allowed animations
struct PulseModifier: ViewModifier {
    let isActive: Bool
    @State private var isPulsing = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(isPulsing && isActive ? 1.3 : 1.0)
            .opacity(isPulsing && isActive ? 0.7 : 1.0)
            .onAppear {
                guard isActive else { return }
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                    isPulsing = true
                }
            }
    }
}

// MARK: - Compact Planned Trip View

/// Compact one-liner for planned trips
struct FriendPlannedTripCompact: View {
    let trip: FriendActiveTrip

    var body: some View {
        HStack(spacing: 8) {
            // Activity icon
            Text(trip.activity_icon)
                .font(.caption)

            // Title
            Text(trip.title)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(1)

            Spacer()

            // Status badge
            HStack(spacing: 4) {
                Circle()
                    .fill(Color.blue.opacity(0.6))
                    .frame(width: 4, height: 4)
                Text("PLANNED")
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
            }

            // ETA (displayed in the trip's original timezone)
            if let etaDate = trip.etaDate {
                Text(DateUtils.formatTime(etaDate, inTimezone: trip.timezone))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(trip.primaryColor.opacity(0.05))
        .cornerRadius(6)
    }
}

// MARK: - Expanded Active Trip Card

/// Expanded card for active/overdue trips with live timer
struct FriendActiveTripCardExpanded: View {
    let trip: FriendActiveTrip
    @EnvironmentObject var session: Session

    // Timer state
    @State private var timeRemaining = ""
    @State private var timeState: FriendTripTimeState = .onTime

    // Map and request update state
    @State private var showingMap = false
    @State private var isRequestingUpdate = false

    // Computed from Session to survive view recreation
    private var cooldownRemaining: Int? {
        session.getCooldownRemaining(for: trip.id)
    }

    private var statusColor: Color {
        switch timeState {
        case .onTime: return .green
        case .graceWarning: return .orange
        case .overdue: return .red
        }
    }

    private var statusText: String {
        switch timeState {
        case .onTime: return "ACTIVE"
        case .graceWarning: return "CHECK IN"
        case .overdue: return "OVERDUE"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header: Icon + Title + Status + Timer
            HStack {
                Text(trip.activity_icon)
                    .font(.title2)

                VStack(alignment: .leading, spacing: 2) {
                    Text(trip.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)

                    Text(trip.activity_name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Live countdown timer
                VStack(alignment: .trailing, spacing: 2) {
                    // Status badge with pulse (allowed animation)
                    HStack(spacing: 4) {
                        Circle()
                            .fill(statusColor)
                            .frame(width: 8, height: 8)
                            .modifier(PulseModifier(isActive: timeState != .onTime))
                            .accessibilityHidden(true)

                        Text(statusText)
                            .font(.caption2)
                            .fontWeight(.bold)
                            .foregroundStyle(statusColor)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Trip status: \(statusText)")

                    // Countdown
                    Text(timeRemaining)
                        .font(.headline)
                        .fontWeight(.bold)
                        .foregroundStyle(statusColor)
                        .monospacedDigit()
                        .accessibilityLabel("Time remaining: \(timeRemaining)")
                }
            }

            // Location (if present)
            if let location = trip.location_text, !location.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "location.fill")
                        .font(.caption2)
                    Text(location)
                        .font(.caption)
                        .lineLimit(2)
                }
                .foregroundStyle(.secondary)
            }

            // ETA info (displayed in the trip's original timezone)
            if let etaDate = trip.etaDate {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.caption2)

                    if timeState == .onTime {
                        Text("Expected by \(DateUtils.formatTime(etaDate, inTimezone: trip.timezone))")
                    } else {
                        Text("Was expected by \(DateUtils.formatTime(etaDate, inTimezone: trip.timezone))")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            // Last check-in with location (enhanced for friends)
            if let lastCheckin = trip.lastCheckinLocation {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.green)
                    if let locationName = lastCheckin.location_name {
                        Text("Last seen: \(locationName)")
                    } else if let date = lastCheckin.timestampDate {
                        Text("Last check-in: \(date.formatted(.relative(presentation: .named)))")
                    }
                    Spacer()
                    if let date = lastCheckin.timestampDate {
                        Text(date.formatted(.relative(presentation: .named)))
                            .font(.caption2)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            } else if let lastCheckin = trip.lastCheckinDate {
                // Fallback for trips without location data
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.green)
                    Text("Last check-in: \(lastCheckin.formatted(.relative(presentation: .named)))")
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            // Live location indicator
            if trip.live_location != nil {
                HStack(spacing: 4) {
                    Image(systemName: "location.fill")
                        .font(.caption2)
                        .foregroundStyle(.blue)
                    Text("Live location sharing enabled")
                        .font(.caption)
                }
                .foregroundStyle(.blue)
            }

            // Full notes (no line limit for expanded view)
            if let notes = trip.notes, !notes.isEmpty {
                Divider()

                Text(notes)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // Action buttons row
            Divider()

            HStack(spacing: 12) {
                // View on Map button (if there's location data)
                if trip.hasLocationData {
                    Button {
                        showingMap = true
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "map.fill")
                            Text("View Map")
                        }
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.blue)
                        .clipShape(Capsule())
                    }
                }

                Spacer()

                // Request Update button (always visible)
                Button {
                    requestUpdate()
                } label: {
                    HStack(spacing: 4) {
                        if isRequestingUpdate {
                            ProgressView()
                                .scaleEffect(0.7)
                                .tint(.white)
                        } else {
                            Image(systemName: "bell.badge")
                        }
                        if let cooldown = cooldownRemaining, cooldown > 0 {
                            Text("Wait \(cooldown)s")
                        } else {
                            Text("Request Update")
                        }
                    }
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(cooldownRemaining != nil ? Color.gray : Color.orange)
                    .clipShape(Capsule())
                }
                .disabled(isRequestingUpdate || (cooldownRemaining ?? 0) > 0)
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(trip.primaryColor.opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(statusColor.opacity(0.3), lineWidth: 1)
                )
        )
        .sheet(isPresented: $showingMap) {
            FriendTripMapView(trip: trip)
                .environmentObject(session)
        }
        .onAppear {
            // Calculate time state immediately so button visibility is correct
            updateTimeRemaining()
            // Check if there's already a pending request (from has_pending_update_request)
            // Only set if we don't already have a cooldown tracked
            if trip.has_pending_update_request == true && session.getCooldownRemaining(for: trip.id) == nil {
                session.setCooldown(for: trip.id, seconds: 600)
            }
        }
        .task {
            // Initial update
            updateTimeRemaining()
            // Timer loop - auto-cancelled when view disappears
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                updateTimeRemaining()
            }
        }
    }

    private func requestUpdate() {
        isRequestingUpdate = true
        Task {
            let result = await session.requestTripUpdate(tripId: trip.id)
            await MainActor.run {
                isRequestingUpdate = false
                if let cooldown = result.cooldown_remaining_seconds {
                    session.setCooldown(for: trip.id, seconds: cooldown)
                }
            }
        }
    }

    private func updateTimeRemaining() {
        guard let eta = trip.etaDate else {
            timeRemaining = "--"
            return
        }

        let now = Date()
        let graceEnd = eta.addingTimeInterval(Double(trip.grace_min) * 60)

        if now > graceEnd {
            // After grace period - overdue
            timeState = .overdue
            let interval = now.timeIntervalSince(graceEnd)
            timeRemaining = "+\(formatInterval(interval))"
        } else if now > eta {
            // Past ETA but within grace
            timeState = .graceWarning
            let interval = graceEnd.timeIntervalSince(now)
            timeRemaining = formatInterval(interval)
        } else {
            // Before ETA
            timeState = .onTime
            let interval = eta.timeIntervalSince(now)
            timeRemaining = formatInterval(interval)
        }
    }

    private func formatInterval(_ interval: TimeInterval) -> String {
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60
        let seconds = Int(interval) % 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else if minutes > 0 {
            return "\(minutes)m \(seconds)s"
        } else {
            return "\(seconds)s"
        }
    }
}

#Preview {
    FriendsTabView()
        .environmentObject(Session())
}
