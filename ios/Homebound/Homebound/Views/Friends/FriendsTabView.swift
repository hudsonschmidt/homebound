import SwiftUI

/// Main Friends tab view showing friends list and invite options
struct FriendsTabView: View {
    @EnvironmentObject var session: Session
    @State private var showingInviteSheet = false
    @State private var showingQRScanner = false
    @State private var selectedFriend: Friend? = nil
    @State private var isLoading = false

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
            }
            .task {
                await loadData()
            }
            .refreshable {
                await loadData()
            }
        }
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

            // Push notification indicator
            HStack(spacing: 4) {
                Image(systemName: "bell.fill")
                    .font(.caption)
                    .foregroundStyle(.green)
                Text("Push")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

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

    @State private var isExpanded: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            // Friend row (tap to view profile)
            FriendRowView(friend: friend)
                .onTapGesture { onTap() }

            // Active trips indicator + expandable section
            if !trips.isEmpty {
                Button(action: { isExpanded.toggle() }) {
                    HStack {
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.caption)
                        Text("\(trips.count) active trip\(trips.count == 1 ? "" : "s")")
                            .font(.caption)
                        Spacer()
                    }
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)
                    .padding(.vertical, 8)
                    .background(Color(.tertiarySystemBackground))
                }

                if isExpanded {
                    VStack(spacing: 8) {
                        ForEach(trips) { trip in
                            FriendTripCardView(trip: trip)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 12)
                    .background(Color(.tertiarySystemBackground))
                }
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
                    Text(statusText)
                        .font(.caption2)
                        .fontWeight(.bold)
                        .foregroundStyle(statusColor)
                }
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

            // ETA
            if let etaDate = trip.etaDate {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.caption2)
                    Text("Expected by \(etaDate.formatted(date: .omitted, time: .shortened))")
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

#Preview {
    FriendsTabView()
        .environmentObject(Session())
}
