import SwiftUI

/// View showing all invites the user has sent and their status
struct PendingInvitesView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var isLoading = false

    var activeInvites: [PendingInvite] {
        session.pendingInvites.filter { $0.isActive }
    }

    var pendingInvites: [PendingInvite] {
        session.pendingInvites.filter { $0.isPending }
    }

    var acceptedInvites: [PendingInvite] {
        session.pendingInvites.filter { $0.isAccepted }
    }

    var expiredInvites: [PendingInvite] {
        session.pendingInvites.filter { $0.isExpired }
    }

    var body: some View {
        NavigationStack {
            List {
                // Active (reusable) section
                if !activeInvites.isEmpty {
                    Section {
                        ForEach(activeInvites) { invite in
                            InviteRowView(invite: invite)
                        }
                    } header: {
                        Text("Your Invite Link")
                    } footer: {
                        Text("This is your permanent invite link. Friends can use it anytime to add you.")
                    }
                }

                // Pending section (legacy one-time invites)
                if !pendingInvites.isEmpty {
                    Section {
                        ForEach(pendingInvites) { invite in
                            InviteRowView(invite: invite)
                        }
                    } header: {
                        Text("Pending")
                    } footer: {
                        Text("These invites are waiting to be accepted.")
                    }
                }

                // Accepted section
                if !acceptedInvites.isEmpty {
                    Section {
                        ForEach(acceptedInvites) { invite in
                            InviteRowView(invite: invite)
                        }
                    } header: {
                        Text("Accepted")
                    }
                }

                // Expired section
                if !expiredInvites.isEmpty {
                    Section {
                        ForEach(expiredInvites) { invite in
                            InviteRowView(invite: invite)
                        }
                    } header: {
                        Text("Expired")
                    }
                }

                // Empty state
                if session.pendingInvites.isEmpty {
                    Section {
                        VStack(spacing: 16) {
                            Image(systemName: "envelope.open")
                                .font(.system(size: 40))
                                .foregroundStyle(.secondary)

                            Text("No Invites Sent")
                                .font(.headline)

                            Text("When you invite friends, they'll appear here.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Sent Invites")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .refreshable {
                _ = await session.loadPendingInvites()
            }
            .overlay {
                if isLoading && session.pendingInvites.isEmpty {
                    ProgressView()
                }
            }
            .task {
                isLoading = true
                _ = await session.loadPendingInvites()
                isLoading = false
            }
        }
    }
}

// MARK: - Invite Row View

struct InviteRowView: View {
    @EnvironmentObject var session: Session
    let invite: PendingInvite

    var statusColor: Color {
        if invite.isActive {
            return .hbBrand
        } else if invite.isAccepted {
            return .green
        } else if invite.isExpired {
            return .secondary
        } else {
            return .orange
        }
    }

    var statusIcon: String {
        if invite.isActive {
            return "link.circle.fill"
        } else if invite.isAccepted {
            return "checkmark.circle.fill"
        } else if invite.isExpired {
            return "clock.badge.xmark"
        } else {
            return "hourglass"
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Status icon
            Image(systemName: statusIcon)
                .font(.title2)
                .foregroundStyle(statusColor)

            VStack(alignment: .leading, spacing: 4) {
                // Status or accepted by name
                if invite.isActive {
                    Text("Active - Reusable")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.hbBrand)
                } else if invite.isAccepted, let name = invite.accepted_by_name {
                    Text("Accepted by \(name)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                } else if invite.isExpired {
                    Text("Expired")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Waiting for response")
                        .font(.subheadline)
                        .fontWeight(.medium)
                }

                // Created date
                if let createdAt = invite.createdAtDate {
                    Text("Created \(createdAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Expiration info for pending invites (not for active/permanent)
                if invite.isPending, let expiresAt = invite.expiresAtDate {
                    let isExpiringSoon = expiresAt.timeIntervalSinceNow < Constants.Time.oneDay

                    HStack(spacing: 4) {
                        Image(systemName: "clock")
                            .font(.caption2)
                        Text("Expires \(expiresAt.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption)
                    }
                    .foregroundStyle(isExpiringSoon ? .orange : .secondary)
                }
            }

            Spacer()

            // Share button for active or pending invites
            if (invite.isActive || invite.isPending), let shareURL = URL(string: "https://api.homeboundapp.com/f/\(invite.token)") {
                ShareLink(
                    item: shareURL,
                    message: Text("Be my friend on Homebound!")
                ) {
                    Image(systemName: "square.and.arrow.up")
                        .font(.subheadline)
                        .foregroundStyle(Color.hbBrand)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    PendingInvitesView()
        .environmentObject(Session())
}
