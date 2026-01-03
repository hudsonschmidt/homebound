import SwiftUI

/// View showing pending trip invitations the user has received
struct TripInvitationsView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var isLoading = false
    @State private var processingTripId: Int? = nil

    var body: some View {
        NavigationStack {
            List {
                if session.tripInvitations.isEmpty && !isLoading {
                    // Empty state
                    Section {
                        VStack(spacing: 16) {
                            Image(systemName: "person.3")
                                .font(.system(size: 40))
                                .foregroundStyle(.secondary)

                            Text("No Trip Invitations")
                                .font(.headline)

                            Text("When friends invite you to join a group trip, you'll see it here.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    }
                } else {
                    ForEach(session.tripInvitations) { invitation in
                        TripInvitationRow(
                            invitation: invitation,
                            isProcessing: processingTripId == invitation.trip_id,
                            onAccept: { await acceptInvitation(invitation) },
                            onDecline: { await declineInvitation(invitation) }
                        )
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Trip Invitations")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .refreshable {
                await session.loadTripInvitations()
            }
            .overlay {
                if isLoading && session.tripInvitations.isEmpty {
                    ProgressView()
                }
            }
            .task {
                isLoading = true
                await session.loadTripInvitations()
                isLoading = false
            }
        }
    }

    private func acceptInvitation(_ invitation: TripInvitation) async {
        processingTripId = invitation.trip_id
        let success = await session.acceptTripInvitation(tripId: invitation.trip_id)
        if success {
            // Refresh invitations list
            await session.loadTripInvitations()
            // Also refresh trips list since user is now part of this trip
            _ = await session.loadAllTrips()
        }
        processingTripId = nil
    }

    private func declineInvitation(_ invitation: TripInvitation) async {
        processingTripId = invitation.trip_id
        let success = await session.declineTripInvitation(tripId: invitation.trip_id)
        if success {
            await session.loadTripInvitations()
        }
        processingTripId = nil
    }
}

// MARK: - Trip Invitation Row

struct TripInvitationRow: View {
    let invitation: TripInvitation
    let isProcessing: Bool
    let onAccept: () async -> Void
    let onDecline: () async -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with activity icon and title
            HStack(spacing: 12) {
                // Activity icon
                Text(invitation.activity_icon)
                    .font(.title2)
                    .frame(width: 44, height: 44)
                    .background(Color.hbBrand.opacity(0.1))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text(invitation.trip_title)
                        .font(.headline)

                    if let inviterName = invitation.inviter_name {
                        Text("Invited by \(inviterName)")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()
            }

            // Trip details
            VStack(alignment: .leading, spacing: 6) {
                // Activity type
                HStack(spacing: 6) {
                    Image(systemName: "figure.hiking")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(invitation.activity_name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Location
                if let location = invitation.trip_location, !location.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "location")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(location)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                // Times
                if let startDate = invitation.tripStartDate, let etaDate = invitation.tripEtaDate {
                    HStack(spacing: 6) {
                        Image(systemName: "clock")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("\(startDate.formatted(date: .abbreviated, time: .shortened)) - \(etaDate.formatted(date: .omitted, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.leading, 4)

            // Accept/Decline buttons
            HStack(spacing: 12) {
                Button(action: {
                    Task { await onDecline() }
                }) {
                    HStack {
                        if isProcessing {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle())
                                .scaleEffect(0.8)
                        } else {
                            Text("Decline")
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(Color(.secondarySystemGroupedBackground))
                    .foregroundStyle(.secondary)
                    .cornerRadius(10)
                }
                .disabled(isProcessing)

                Button(action: {
                    Task { await onAccept() }
                }) {
                    HStack {
                        if isProcessing {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                .scaleEffect(0.8)
                        } else {
                            Text("Join Trip")
                                .fontWeight(.semibold)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(Color.hbBrand)
                    .foregroundStyle(.white)
                    .cornerRadius(10)
                }
                .disabled(isProcessing)
            }
        }
        .padding(.vertical, 8)
    }
}

#Preview {
    TripInvitationsView()
        .environmentObject(Session())
}
