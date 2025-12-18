import SwiftUI

/// View showing a friend's profile details with option to remove
struct FriendProfileView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss
    let friend: Friend

    @State private var showingRemoveConfirmation = false
    @State private var isRemoving = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Profile header
                    profileHeaderView

                    // Info cards
                    infoCardsView

                    // Safety contact info
                    safetyContactInfoView

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

    // MARK: - Profile Header

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

                Text("Homebound Member")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
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

    // MARK: - Info Cards

    var infoCardsView: some View {
        VStack(spacing: 12) {
            // Member since
            if let memberDate = friend.memberSinceDate {
                infoCard(
                    icon: "person.badge.clock",
                    title: "Member Since",
                    value: memberDate.formatted(date: .long, time: .omitted)
                )
            }

            // Friends since
            if let friendshipDate = friend.friendshipSinceDate {
                infoCard(
                    icon: "heart.fill",
                    title: "Friends Since",
                    value: friendshipDate.formatted(date: .long, time: .omitted)
                )
            }
        }
    }

    func infoCard(icon: String, title: String, value: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Color.hbBrand)
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

    // MARK: - Safety Contact Info

    var safetyContactInfoView: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("As Safety Contact")
                .font(.headline)

            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 12) {
                    Image(systemName: "bell.badge.fill")
                        .font(.title3)
                        .foregroundStyle(.green)
                        .frame(width: 32)

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Push Notifications")
                            .font(.subheadline)
                            .fontWeight(.medium)
                        Text("Gets instant alerts on their phone")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 12) {
                    Image(systemName: "bolt.fill")
                        .font(.title3)
                        .foregroundStyle(.orange)
                        .frame(width: 32)

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Faster Response")
                            .font(.subheadline)
                            .fontWeight(.medium)
                        Text("No email delays - immediate notification")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                HStack(spacing: 12) {
                    Image(systemName: "shield.checkered")
                        .font(.title3)
                        .foregroundStyle(.blue)
                        .frame(width: 32)

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Trip Updates")
                            .font(.subheadline)
                            .fontWeight(.medium)
                        Text("Notified when you start, complete, or are overdue")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding()
            .background(Color(.secondarySystemBackground))
            .cornerRadius(12)
        }
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
        friendship_since: "2024-06-01T00:00:00"
    ))
    .environmentObject(Session())
}
