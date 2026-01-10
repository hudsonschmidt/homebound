import SwiftUI

/// View shown when user opens a friend invite link
struct InviteAcceptView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    let token: String
    let onComplete: () -> Void

    @State private var preview: FriendInvitePreview?
    @State private var isLoading = true
    @State private var isAccepting = false
    @State private var errorMessage: String?
    @State private var acceptedFriend: Friend?

    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemBackground)
                    .ignoresSafeArea()

                if isLoading {
                    loadingView
                } else if let error = errorMessage {
                    errorView(message: error)
                } else if let friend = acceptedFriend {
                    successView(friend: friend)
                } else if let preview = preview {
                    if preview.is_own_invite {
                        ownInviteView
                    } else if preview.is_valid {
                        invitePreviewView(preview: preview)
                    } else {
                        expiredView
                    }
                } else {
                    errorView(message: "Invite not found")
                }
            }
            .navigationTitle("Friend Invite")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") {
                        dismiss()
                        onComplete()
                    }
                }
            }
            .task {
                await loadPreview()
            }
        }
    }

    // MARK: - Loading View

    var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Loading invite...")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Invite Preview View

    func invitePreviewView(preview: FriendInvitePreview) -> some View {
        VStack(spacing: 32) {
            Spacer()

            // Inviter info
            VStack(spacing: 16) {
                // Profile photo or initial
                if let photoUrl = preview.inviter_profile_photo_url, let url = URL(string: photoUrl) {
                    AsyncImage(url: url) { image in
                        image
                            .resizable()
                            .scaledToFill()
                    } placeholder: {
                        inviterInitialCircle(name: preview.inviter_first_name)
                    }
                    .frame(width: 100, height: 100)
                    .clipShape(Circle())
                } else {
                    inviterInitialCircle(name: preview.inviter_first_name)
                }

                VStack(spacing: 4) {
                    Text(preview.inviter_first_name)
                        .font(.title)
                        .fontWeight(.bold)

                    Text("wants to be your friend on Homebound")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }

                if let memberDate = preview.inviterMemberSinceDate {
                    Text("Member since \(memberDate.formatted(date: .abbreviated, time: .omitted))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Benefits info
            VStack(alignment: .leading, spacing: 12) {
                benefitRow(icon: "bell.badge.fill", color: .green, text: "Receive instant push notifications")
                benefitRow(icon: "shield.fill", color: .blue, text: "Be their safety contact")
                benefitRow(icon: "person.2.fill", color: .purple, text: "See each other's profiles")
            }
            .padding()
            .background(Color(.secondarySystemBackground))
            .cornerRadius(16)

            Spacer()

            // Accept button
            Button(action: { Task { await acceptInvite() } }) {
                HStack {
                    if isAccepting {
                        ProgressView()
                            .tint(.white)
                    } else {
                        Image(systemName: "person.badge.plus")
                        Text("Accept Friend Request")
                    }
                }
                .font(.headline)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Color.hbBrand)
                .cornerRadius(14)
            }
            .disabled(isAccepting)

            // Expiry notice
            if let expiryDate = preview.expiresAtDate {
                Text("Expires \(expiryDate.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }

    func benefitRow(icon: String, color: Color, text: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 30)
            Text(text)
                .font(.subheadline)
            Spacer()
        }
    }

    func inviterInitialCircle(name: String) -> some View {
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
                Text(name.prefix(1).uppercased())
                    .font(.system(size: 40, weight: .semibold))
                    .foregroundStyle(.white)
            )
    }

    // MARK: - Success View

    func successView(friend: Friend) -> some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 80))
                .foregroundStyle(.green)

            VStack(spacing: 8) {
                Text("You're now friends!")
                    .font(.title2)
                    .fontWeight(.bold)

                Text("You and \(friend.fullName) are now connected on Homebound.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            Button(action: {
                dismiss()
                onComplete()
            }) {
                Text("Done")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color.hbBrand)
                    .cornerRadius(14)
            }
        }
        .padding()
    }

    // MARK: - Expired View

    var expiredView: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "clock.badge.exclamationmark")
                .font(.system(size: 60))
                .foregroundStyle(.orange)

            VStack(spacing: 8) {
                Text("Invite Expired")
                    .font(.title2)
                    .fontWeight(.bold)

                Text("This friend invite has expired or has already been used. Ask your friend to send a new invite.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            Button(action: {
                dismiss()
                onComplete()
            }) {
                Text("Close")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color(.systemGray))
                    .cornerRadius(14)
            }
        }
        .padding()
    }

    // MARK: - Own Invite View

    var ownInviteView: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "person.crop.circle.badge.questionmark")
                .font(.system(size: 60))
                .foregroundStyle(.blue)

            VStack(spacing: 8) {
                Text("This is Your Invite")
                    .font(.title2)
                    .fontWeight(.bold)

                Text("You can't add yourself as a friend. Share this link with others to connect with them on Homebound!")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            Button(action: {
                dismiss()
                onComplete()
            }) {
                Text("Got It")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color.hbBrand)
                    .cornerRadius(14)
            }
        }
        .padding()
    }

    // MARK: - Error View

    func errorView(message: String) -> some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 60))
                .foregroundStyle(.red)

            VStack(spacing: 8) {
                Text("Something went wrong")
                    .font(.title2)
                    .fontWeight(.bold)

                Text(message)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            Button(action: {
                dismiss()
                onComplete()
            }) {
                Text("Close")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color(.systemGray))
                    .cornerRadius(14)
            }
        }
        .padding()
    }

    // MARK: - Actions

    func loadPreview() async {
        isLoading = true
        preview = await session.getFriendInvitePreview(token: token)
        isLoading = false

        if preview == nil {
            errorMessage = "This invite link is invalid or has been removed."
        }
    }

    func acceptInvite() async {
        isAccepting = true

        let friend = await session.acceptFriendInvite(token: token)

        await MainActor.run {
            isAccepting = false
            if let friend = friend {
                acceptedFriend = friend
                // Refresh friends list in the background
                Task {
                    _ = await session.loadFriends()
                }
            } else {
                // Check for specific error messages
                if session.lastError.contains("Already friends") {
                    errorMessage = "You're already friends with this person!"
                } else if session.lastError.contains("own invite") {
                    errorMessage = "You can't accept your own invite."
                } else {
                    errorMessage = session.lastError.isEmpty ? "Failed to accept invite" : session.lastError
                }
            }
        }
    }
}

#Preview {
    InviteAcceptView(token: "test-token") {}
        .environmentObject(Session())
}
