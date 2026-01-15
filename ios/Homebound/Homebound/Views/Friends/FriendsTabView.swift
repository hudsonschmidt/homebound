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
    @State private var showingTripInvitations = false
    @State private var selectedFriend: Friend? = nil
    @State private var isLoading = false

    // Group management
    @State private var showingManageGroups = false
    @State private var showingGroupsPaywall = false
    @State private var groupsRefreshTrigger = UUID()  // Force refresh when groups change

    // Auto-refresh polling
    @State private var pollingTask: Task<Void, Never>? = nil
    @State private var lastTabRefresh: Date? = nil
    private let pollingInterval: TimeInterval = 30
    private let tabSwitchDebounce: TimeInterval = 5

    // Navigation from push notifications
    @Binding var scrollToTripId: Int?
    @State private var highlightedTripId: Int?

    init(scrollToTripId: Binding<Int?> = .constant(nil)) {
        _scrollToTripId = scrollToTripId
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground)
                    .ignoresSafeArea()

                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: 24) {
                            // Header
                            headerView

                            // Trip invitations banner (if any pending)
                            tripInvitationsBanner

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
                    .onChange(of: scrollToTripId) { oldValue, newValue in
                        if let tripId = newValue {
                            // Scroll to the trip card
                            withAnimation(.easeInOut(duration: 0.3)) {
                                proxy.scrollTo("trip-\(tripId)", anchor: .center)
                            }
                            // Highlight the card briefly
                            highlightedTripId = tripId
                            // Clear after a short delay
                            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                                highlightedTripId = nil
                                scrollToTripId = nil
                            }
                        }
                    }
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
                    .id(friend.user_id)  // Force view recreation when friend changes
                    .environmentObject(session)
                    .environmentObject(AppPreferences.shared)
            }
            .sheet(isPresented: $showingTripInvitations) {
                TripInvitationsView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingManageGroups) {
                ManageGroupsView(
                    friends: session.friends,
                    onGroupsChanged: { groupsRefreshTrigger = UUID() }
                )
                .environmentObject(session)
            }
            .sheet(isPresented: $showingGroupsPaywall) {
                PaywallView(feature: .contactGroups)
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

    // MARK: - Trip Invitations Banner

    @ViewBuilder
    var tripInvitationsBanner: some View {
        if !session.tripInvitations.isEmpty {
            Button(action: { showingTripInvitations = true }) {
                HStack(spacing: 12) {
                    // Icon with badge
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "person.3.fill")
                            .font(.title2)
                            .foregroundStyle(Color.hbBrand)

                        // Badge
                        Text("\(session.tripInvitations.count)")
                            .font(.caption2)
                            .fontWeight(.bold)
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.orange)
                            .clipShape(Capsule())
                            .offset(x: 8, y: -4)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Trip Invitations")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundStyle(.primary)

                        Text("\(session.tripInvitations.count) pending invitation\(session.tripInvitations.count == 1 ? "" : "s")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                .padding()
                .background(Color.orange.opacity(0.1))
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.orange.opacity(0.3), lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
        }
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
                // Friends list with expandable trip cards (active trips sorted to top)
                ForEach(sortedFriends) { friend in
                    FriendRowWithTripsView(
                        friend: friend,
                        trips: tripsForFriend(friend),
                        highlightedTripId: highlightedTripId,
                        onTap: { selectedFriend = friend }
                    )
                    .id("\(friend.user_id)-\(groupsRefreshTrigger)")  // Force refresh when groups change
                }

                // Manage Groups button
                if session.canUse(feature: .contactGroups) {
                    Button(action: { showingManageGroups = true }) {
                        HStack {
                            Image(systemName: "folder.badge.gearshape")
                            Text("Manage Groups")
                        }
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.hbBrand)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(12)
                    }
                    .padding(.top, 8)
                } else {
                    // Show upgrade prompt for free users
                    Button(action: { showingGroupsPaywall = true }) {
                        HStack {
                            Image(systemName: "folder.badge.gearshape")
                            Text("Manage Groups")
                            Spacer()
                            PremiumBadge()
                        }
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .padding(.horizontal)
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(12)
                    }
                    .padding(.top, 8)
                }
            }
        }
    }

    private func tripsForFriend(_ friend: Friend) -> [FriendActiveTrip] {
        session.friendActiveTrips.filter { $0.owner.user_id == friend.user_id }
    }

    /// Friends sorted with those who have active trips at the top
    private var sortedFriends: [Friend] {
        session.friends.sorted { friend1, friend2 in
            let trips1 = tripsForFriend(friend1)
            let trips2 = tripsForFriend(friend2)
            let hasActive1 = trips1.contains { $0.isActiveStatus }
            let hasActive2 = trips2.contains { $0.isActiveStatus }

            // Friends with active trips come first
            if hasActive1 != hasActive2 {
                return hasActive1
            }
            // Then friends with any trips
            if !trips1.isEmpty != !trips2.isEmpty {
                return !trips1.isEmpty
            }
            // Otherwise maintain original order (by name or however they're sorted)
            return false
        }
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
        await session.loadTripInvitations()
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

                HStack(spacing: 8) {
                    if let friendshipDate = friend.friendshipSinceDate {
                        Text("Friends since \(friendshipDate.formatted(date: .abbreviated, time: .omitted))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
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
                Text(friend.initial)
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
    var highlightedTripId: Int? = nil
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
                        FriendActiveTripCardExpanded(trip: trip, isHighlighted: highlightedTripId == trip.id)
                            .id("trip-\(trip.id)")
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

            // ETA (displayed in the trip's original timezone, with date if not today)
            if let etaDate = trip.etaDate {
                Text(formattedETA(etaDate))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(trip.primaryColor.opacity(0.05))
        .cornerRadius(6)
    }

    /// Format ETA with date if not today (in the trip's timezone)
    private func formattedETA(_ date: Date) -> String {
        // Use trip's timezone for determining "today" and formatting
        var calendar = Calendar.current
        if let tzId = trip.timezone, let tz = TimeZone(identifier: tzId) {
            calendar.timeZone = tz
        }

        let time = DateUtils.formatTime(date, inTimezone: trip.timezone)

        if calendar.isDateInToday(date) {
            return time
        } else {
            // Format date in trip's timezone
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "MMM d"
            if let tzId = trip.timezone, let tz = TimeZone(identifier: tzId) {
                dateFormatter.timeZone = tz
            }
            let dateStr = dateFormatter.string(from: date)
            return "\(dateStr) • \(time)"
        }
    }
}

// MARK: - Expanded Active Trip Card

/// Expanded card for active/overdue trips with live timer
struct FriendActiveTripCardExpanded: View {
    let trip: FriendActiveTrip
    var isHighlighted: Bool = false
    @EnvironmentObject var session: Session

    // Timer state
    @State private var timeRemaining = ""
    @State private var timeState: FriendTripTimeState = .onTime

    // Map and request update state
    @State private var showingMap = false
    @State private var isRequestingUpdate = false

    // Constants
    private let defaultCooldownSeconds = 600  // 10 minutes between update requests

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
                // Activity icon with optional group badge
                ZStack(alignment: .bottomTrailing) {
                    Text(trip.activity_icon)
                        .font(.title2)

                    // Subtle group indicator badge
                    if trip.isGroupTrip {
                        Image(systemName: "person.2.fill")
                            .font(.system(size: 8))
                            .foregroundStyle(.white)
                            .padding(2)
                            .background(Color.hbBrand.opacity(0.8))
                            .clipShape(Circle())
                            .offset(x: 4, y: 2)
                    }
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(trip.title)
                        .font(.subheadline)
                        .fontWeight(.semibold)

                    // For group trips, show who we're monitoring; for solo trips show activity
                    if trip.isGroupTrip {
                        Text("Monitoring \(trip.monitoredFirstName)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text(trip.activity_name)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
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
                        .strokeBorder(
                            isHighlighted ? Color.hbBrand : statusColor.opacity(0.3),
                            lineWidth: isHighlighted ? 2 : 1
                        )
                )
        )
        .shadow(color: isHighlighted ? Color.hbBrand.opacity(0.3) : .clear, radius: 8)
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
                session.setCooldown(for: trip.id, seconds: defaultCooldownSeconds)
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
        .onChange(of: trip.etaDate) { _, _ in
            updateTimeRemaining()
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

// MARK: - Manage Groups View

struct ManageGroupsView: View {
    @EnvironmentObject var session: Session
    let friends: [Friend]
    let onGroupsChanged: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var showingCreateGroup = false
    @State private var groupToEdit: String? = nil
    @State private var groupToRename: String? = nil
    @State private var renameText = ""
    @State private var groupToDelete: String? = nil
    @State private var refreshTrigger = UUID()

    /// Get all existing group names
    private var existingGroups: [String] {
        UserDefaults.standard.stringArray(forKey: "customFriendGroups") ?? []
    }

    /// Get friends in a specific group
    private func friendsInGroup(_ groupName: String) -> [Friend] {
        let friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        return friends.filter { friend in
            let groups = friendGroupsData[String(friend.user_id)] ?? []
            return groups.contains(groupName)
        }
    }

    /// Get groups for a friend
    private func groupsForFriend(_ friend: Friend) -> [String] {
        let friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        return friendGroupsData[String(friend.user_id)] ?? []
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Create new group button
                    Button(action: { showingCreateGroup = true }) {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                                .font(.title2)
                            Text("Create New Group")
                                .fontWeight(.semibold)
                        }
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.hbBrand)
                        .cornerRadius(12)
                    }
                    .padding(.horizontal)

                    if existingGroups.isEmpty {
                        // Empty state
                        VStack(spacing: 16) {
                            Image(systemName: "folder.badge.plus")
                                .font(.system(size: 56))
                                .foregroundStyle(.secondary)
                            Text("No Groups Yet")
                                .font(.title2)
                                .fontWeight(.semibold)
                            Text("Create groups to organize your friends.\nFriends can be in multiple groups.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 60)
                    } else {
                        // Groups list
                        VStack(spacing: 12) {
                            ForEach(existingGroups, id: \.self) { groupName in
                                GroupCard(
                                    groupName: groupName,
                                    friends: friendsInGroup(groupName),
                                    allFriends: friends,
                                    onEdit: { groupToEdit = groupName },
                                    onRename: {
                                        renameText = groupName
                                        groupToRename = groupName
                                    },
                                    onDelete: { groupToDelete = groupName }
                                )
                            }
                        }
                        .padding(.horizontal)
                        .id(refreshTrigger)
                    }
                }
                .padding(.vertical)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Manage Groups")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
            .sheet(isPresented: $showingCreateGroup) {
                CreateGroupSheet(
                    friends: friends,
                    onComplete: { name, selectedFriends in
                        createGroup(name: name, withFriends: selectedFriends)
                    }
                )
            }
            .sheet(isPresented: .init(
                get: { groupToEdit != nil },
                set: { if !$0 { groupToEdit = nil } }
            )) {
                if let groupName = groupToEdit {
                    EditGroupSheet(
                        groupName: groupName,
                        friends: friends,
                        onComplete: { onGroupsChanged(); refreshTrigger = UUID() }
                    )
                }
            }
            .alert("Rename Group", isPresented: .init(
                get: { groupToRename != nil },
                set: { if !$0 { groupToRename = nil; renameText = "" } }
            )) {
                TextField("Group name", text: $renameText)
                Button("Cancel", role: .cancel) {
                    groupToRename = nil
                    renameText = ""
                }
                Button("Rename") {
                    if let oldName = groupToRename {
                        renameGroup(from: oldName, to: renameText)
                    }
                }
                .disabled(renameText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            } message: {
                Text("Enter a new name for this group")
            }
            .alert("Delete Group?", isPresented: .init(
                get: { groupToDelete != nil },
                set: { if !$0 { groupToDelete = nil } }
            )) {
                Button("Cancel", role: .cancel) {
                    groupToDelete = nil
                }
                Button("Delete", role: .destructive) {
                    if let groupName = groupToDelete {
                        deleteGroup(groupName)
                    }
                }
            } message: {
                Text("This will remove the group. Friends will remain in their other groups.")
            }
        }
    }

    private func createGroup(name: String, withFriends selectedFriends: [Friend]) {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else { return }

        // Add to custom groups list
        var customGroups = UserDefaults.standard.stringArray(forKey: "customFriendGroups") ?? []
        if !customGroups.contains(trimmedName) {
            customGroups.append(trimmedName)
            UserDefaults.standard.set(customGroups, forKey: "customFriendGroups")
        }

        // Add selected friends to this group
        var friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        for friend in selectedFriends {
            let key = String(friend.user_id)
            var groups = friendGroupsData[key] ?? []
            if !groups.contains(trimmedName) {
                groups.append(trimmedName)
                friendGroupsData[key] = groups
            }
        }
        UserDefaults.standard.set(friendGroupsData, forKey: "friendGroupsMulti")

        refreshTrigger = UUID()
        onGroupsChanged()
    }

    private func renameGroup(from oldName: String, to newName: String) {
        let trimmedNew = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedNew.isEmpty, oldName != trimmedNew else { return }

        // Update custom groups list
        var customGroups = UserDefaults.standard.stringArray(forKey: "customFriendGroups") ?? []
        if let index = customGroups.firstIndex(of: oldName) {
            customGroups[index] = trimmedNew
        }
        UserDefaults.standard.set(customGroups, forKey: "customFriendGroups")

        // Update all friend assignments
        var friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        for (key, groups) in friendGroupsData {
            if groups.contains(oldName) {
                var newGroups = groups.filter { $0 != oldName }
                newGroups.append(trimmedNew)
                friendGroupsData[key] = newGroups
            }
        }
        UserDefaults.standard.set(friendGroupsData, forKey: "friendGroupsMulti")

        groupToRename = nil
        renameText = ""
        refreshTrigger = UUID()
        onGroupsChanged()
    }

    private func deleteGroup(_ groupName: String) {
        // Remove from custom groups list
        var customGroups = UserDefaults.standard.stringArray(forKey: "customFriendGroups") ?? []
        customGroups.removeAll { $0 == groupName }
        UserDefaults.standard.set(customGroups, forKey: "customFriendGroups")

        // Remove this group from all friend assignments
        var friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        for (key, groups) in friendGroupsData {
            if groups.contains(groupName) {
                let newGroups = groups.filter { $0 != groupName }
                if newGroups.isEmpty {
                    friendGroupsData.removeValue(forKey: key)
                } else {
                    friendGroupsData[key] = newGroups
                }
            }
        }
        UserDefaults.standard.set(friendGroupsData, forKey: "friendGroupsMulti")

        groupToDelete = nil
        refreshTrigger = UUID()
        onGroupsChanged()
    }
}

// MARK: - Group Card

struct GroupCard: View {
    let groupName: String
    let friends: [Friend]
    let allFriends: [Friend]
    let onEdit: () -> Void
    let onRename: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Image(systemName: "folder.fill")
                    .foregroundStyle(Color.hbBrand)
                Text(groupName)
                    .font(.headline)
                Spacer()
                Menu {
                    Button(action: onEdit) {
                        Label("Edit Members", systemImage: "person.2")
                    }
                    Button(action: onRename) {
                        Label("Rename", systemImage: "pencil")
                    }
                    Divider()
                    Button(role: .destructive, action: onDelete) {
                        Label("Delete Group", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
            }

            if friends.isEmpty {
                Text("No members yet")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                // Friend avatars in a flow layout
                FlowLayout(spacing: 8) {
                    ForEach(friends) { friend in
                        FriendChip(friend: friend)
                    }
                }
            }

            // Add members button
            Button(action: onEdit) {
                HStack {
                    Image(systemName: "plus")
                    Text(friends.isEmpty ? "Add Members" : "Edit Members")
                }
                .font(.subheadline)
                .fontWeight(.medium)
                .foregroundStyle(Color.hbBrand)
            }
        }
        .padding()
        .background(Color(.secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

// MARK: - Friend Chip

struct FriendChip: View {
    let friend: Friend

    var body: some View {
        HStack(spacing: 6) {
            if let photoUrl = friend.profile_photo_url, let url = URL(string: photoUrl) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .scaledToFill()
                } placeholder: {
                    initialCircle
                }
                .frame(width: 24, height: 24)
                .clipShape(Circle())
            } else {
                initialCircle
            }
            Text(friend.first_name)
                .font(.subheadline)
                .lineLimit(1)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(.tertiarySystemFill))
        .cornerRadius(20)
    }

    private var initialCircle: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [Color.hbBrand, Color.hbTeal],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 24, height: 24)
            .overlay(
                Text(friend.initial)
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
            )
    }
}

// MARK: - Flow Layout

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = computeLayout(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = computeLayout(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func computeLayout(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        var positions: [CGPoint] = []
        var currentX: CGFloat = 0
        var currentY: CGFloat = 0
        var lineHeight: CGFloat = 0
        var maxWidth: CGFloat = 0

        let maxX = proposal.width ?? .infinity

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)

            if currentX + size.width > maxX && currentX > 0 {
                currentX = 0
                currentY += lineHeight + spacing
                lineHeight = 0
            }

            positions.append(CGPoint(x: currentX, y: currentY))
            lineHeight = max(lineHeight, size.height)
            currentX += size.width + spacing
            maxWidth = max(maxWidth, currentX)
        }

        return (CGSize(width: maxWidth, height: currentY + lineHeight), positions)
    }
}

// MARK: - Create Group Sheet

struct CreateGroupSheet: View {
    let friends: [Friend]
    let onComplete: (String, [Friend]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var groupName = ""
    @State private var selectedFriends: Set<Int> = []
    @State private var searchText = ""

    private var filteredFriends: [Friend] {
        if searchText.isEmpty {
            return friends
        }
        return friends.filter { $0.fullName.localizedCaseInsensitiveContains(searchText) }
    }

    private var canCreate: Bool {
        !groupName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Group name input
                VStack(alignment: .leading, spacing: 8) {
                    Text("Group Name")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                    TextField("e.g., Family, Coworkers, Hiking Buddies", text: $groupName)
                        .textFieldStyle(.roundedBorder)
                }
                .padding()
                .background(Color(.secondarySystemGroupedBackground))

                // Friends selection
                List {
                    Section {
                        if friends.isEmpty {
                            Text("No friends to add")
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(filteredFriends) { friend in
                                GroupMemberSelectionRow(
                                    friend: friend,
                                    isSelected: selectedFriends.contains(friend.user_id),
                                    onToggle: {
                                        if selectedFriends.contains(friend.user_id) {
                                            selectedFriends.remove(friend.user_id)
                                        } else {
                                            selectedFriends.insert(friend.user_id)
                                        }
                                    }
                                )
                            }
                        }
                    } header: {
                        HStack {
                            Text("Select Friends")
                            Spacer()
                            if !selectedFriends.isEmpty {
                                Text("\(selectedFriends.count) selected")
                                    .foregroundStyle(Color.hbBrand)
                            }
                        }
                    } footer: {
                        if !friends.isEmpty {
                            Text("You can add more friends later")
                        }
                    }
                }
                .searchable(text: $searchText, prompt: "Search friends")
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("New Group")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Create") {
                        let selected = friends.filter { selectedFriends.contains($0.user_id) }
                        onComplete(groupName, selected)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .disabled(!canCreate)
                }
            }
        }
    }
}

// MARK: - Edit Group Sheet

struct EditGroupSheet: View {
    let groupName: String
    let friends: [Friend]
    let onComplete: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var selectedFriends: Set<Int> = []
    @State private var searchText = ""

    private var filteredFriends: [Friend] {
        if searchText.isEmpty {
            return friends
        }
        return friends.filter { $0.fullName.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(filteredFriends) { friend in
                        GroupMemberSelectionRow(
                            friend: friend,
                            isSelected: selectedFriends.contains(friend.user_id),
                            onToggle: {
                                toggleFriend(friend)
                            }
                        )
                    }
                } header: {
                    HStack {
                        Text("Members")
                        Spacer()
                        Text("\(selectedFriends.count) selected")
                            .foregroundStyle(Color.hbBrand)
                    }
                }
            }
            .searchable(text: $searchText, prompt: "Search friends")
            .navigationTitle(groupName)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        onComplete()
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
            .onAppear {
                loadCurrentMembers()
            }
        }
    }

    private func loadCurrentMembers() {
        let friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        selectedFriends = Set(friends.filter { friend in
            let groups = friendGroupsData[String(friend.user_id)] ?? []
            return groups.contains(groupName)
        }.map { $0.user_id })
    }

    private func toggleFriend(_ friend: Friend) {
        var friendGroupsData = UserDefaults.standard.dictionary(forKey: "friendGroupsMulti") as? [String: [String]] ?? [:]
        let key = String(friend.user_id)
        var groups = friendGroupsData[key] ?? []

        if selectedFriends.contains(friend.user_id) {
            // Remove from group
            selectedFriends.remove(friend.user_id)
            groups.removeAll { $0 == groupName }
        } else {
            // Add to group
            selectedFriends.insert(friend.user_id)
            if !groups.contains(groupName) {
                groups.append(groupName)
            }
        }

        if groups.isEmpty {
            friendGroupsData.removeValue(forKey: key)
        } else {
            friendGroupsData[key] = groups
        }

        UserDefaults.standard.set(friendGroupsData, forKey: "friendGroupsMulti")
    }
}

// MARK: - Friend Selection Row

struct GroupMemberSelectionRow: View {
    let friend: Friend
    let isSelected: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
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
                    .frame(width: 40, height: 40)
                    .clipShape(Circle())
                } else {
                    initialCircle
                }

                Text(friend.fullName)
                    .foregroundStyle(.primary)

                Spacer()

                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(isSelected ? Color.hbBrand : Color.gray.opacity(0.3))
            }
        }
    }

    private var initialCircle: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [Color.hbBrand, Color.hbTeal],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 40, height: 40)
            .overlay(
                Text(friend.initial)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
            )
    }
}

#Preview {
    FriendsTabView()
        .environmentObject(Session())
}
