import SwiftUI

/// View showing a friend's profile details with option to remove
struct FriendProfileView: View {
    @EnvironmentObject var session: Session
    @EnvironmentObject var preferences: AppPreferences
    @Environment(\.dismiss) var dismiss
    let friend: Friend

    @State private var showingRemoveConfirmation = false
    @State private var isRemoving = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Profile header (always shown)
                    profileHeaderView

                    // Stats grid (conditional based on preferences)
                    if hasVisibleStats {
                        statsGridView
                    }

                    Spacer(minLength: 40)

                    // Remove friend button
                    removeButtonView
                }
                .padding()
            }
            .background(Color(.systemBackground))
            .navigationTitle("Friend Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .confirmationDialog(
                "Remove Friend",
                isPresented: $showingRemoveConfirmation,
                titleVisibility: .visible
            ) {
                Button("Remove \(friend.first_name)", role: .destructive) {
                    removeFriend()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Are you sure you want to remove \(friend.fullName) as a friend? They will no longer receive push notifications as your safety contact.")
            }
        }
    }

    // MARK: - Check if any stats are visible

    private var hasVisibleStats: Bool {
        preferences.showFriendJoinDate ||
        preferences.showFriendAge ||
        preferences.showFriendAchievements ||
        preferences.showFriendTotalTrips ||
        preferences.showFriendAdventureTime ||
        preferences.showFriendFavoriteActivity
    }

    // MARK: - Profile Header (always shown: name, profile photo, friends since)

    var profileHeaderView: some View {
        VStack(spacing: 16) {
            // Profile photo or initial
            if let photoUrl = friend.profile_photo_url, let url = URL(string: photoUrl) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .scaledToFill()
                } placeholder: {
                    profileInitialCircle
                }
                .frame(width: 100, height: 100)
                .clipShape(Circle())
            } else {
                profileInitialCircle
            }

            VStack(spacing: 4) {
                Text(friend.fullName)
                    .font(.title2)
                    .fontWeight(.bold)

                // Friends since (always shown)
                if let friendshipDate = friend.friendshipSinceDate {
                    HStack(spacing: 4) {
                        Image(systemName: "heart.fill")
                            .font(.caption)
                            .foregroundStyle(.pink)
                        Text("Friends since \(friendshipDate.formatted(date: .abbreviated, time: .omitted))")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(.top, 20)
    }

    var profileInitialCircle: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [Color.hbBrand, Color.hbTeal],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 100, height: 100)
            .overlay(
                Text(friend.first_name.prefix(1).uppercased())
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(.white)
            )
    }

    // MARK: - Stats Grid (conditional)

    var statsGridView: some View {
        VStack(spacing: 12) {
            // Member since
            if preferences.showFriendJoinDate, let memberDate = friend.memberSinceDate {
                statCard(
                    icon: "calendar.badge.clock",
                    iconColor: .blue,
                    title: "Member Since",
                    value: memberDate.formatted(date: .abbreviated, time: .omitted)
                )
            }

            // Age
            if preferences.showFriendAge, let age = friend.age, age > 0 {
                statCard(
                    icon: "number",
                    iconColor: .purple,
                    title: "Age",
                    value: "\(age) years old"
                )
            }

            // Achievements
            if preferences.showFriendAchievements, let count = friend.achievements_count {
                statCard(
                    icon: "trophy.fill",
                    iconColor: .orange,
                    title: "Achievements",
                    value: "\(count) unlocked"
                )
            }

            // Total trips
            if preferences.showFriendTotalTrips, let trips = friend.total_trips {
                statCard(
                    icon: "figure.walk",
                    iconColor: .red,
                    title: "Total Trips",
                    value: "\(trips) trips"
                )
            }

            // Adventure time
            if preferences.showFriendAdventureTime, let formatted = friend.formattedAdventureTime {
                statCard(
                    icon: "hourglass",
                    iconColor: .green,
                    title: "Adventure Time",
                    value: formatted
                )
            }

            // Favorite activity
            if preferences.showFriendFavoriteActivity,
               let activityName = friend.favorite_activity_name,
               let activityIcon = friend.favorite_activity_icon {
                statCardWithEmoji(
                    emoji: activityIcon,
                    title: "Favorite Activity",
                    value: activityName
                )
            }
        }
    }

    func statCard(icon: String, iconColor: Color, title: String, value: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(iconColor)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }

            Spacer()
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    func statCardWithEmoji(emoji: String, title: String, value: String) -> some View {
        HStack(spacing: 12) {
            Text(emoji)
                .font(.title3)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }

            Spacer()
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    // MARK: - Remove Button

    var removeButtonView: some View {
        Button(action: { showingRemoveConfirmation = true }) {
            HStack {
                if isRemoving {
                    ProgressView()
                        .tint(.red)
                } else {
                    Image(systemName: "person.badge.minus")
                }
                Text("Remove Friend")
            }
            .font(.subheadline)
            .fontWeight(.medium)
            .foregroundStyle(.red)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.red.opacity(0.1))
            .cornerRadius(12)
        }
        .disabled(isRemoving)
    }

    // MARK: - Actions

    func removeFriend() {
        isRemoving = true
        Task {
            let success = await session.removeFriend(userId: friend.user_id)
            await MainActor.run {
                isRemoving = false
                if success {
                    dismiss()
                }
            }
        }
    }
}

#Preview {
    FriendProfileView(friend: Friend(
        user_id: 1,
        first_name: "Jane",
        last_name: "Doe",
        profile_photo_url: nil,
        member_since: "2024-01-15T00:00:00",
        friendship_since: "2024-06-01T00:00:00",
        age: 28,
        achievements_count: 12,
        total_trips: 45,
        total_adventure_hours: 120,
        favorite_activity_name: "Hiking",
        favorite_activity_icon: "🥾"
    ))
    .environmentObject(Session())
    .environmentObject(AppPreferences.shared)
}
