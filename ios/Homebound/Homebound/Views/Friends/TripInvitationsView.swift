import SwiftUI

/// View showing pending trip invitations the user has received
struct TripInvitationsView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var isLoading = false
    @State private var processingTripId: Int? = nil
    @State private var invitationToJoin: TripInvitation? = nil  // Triggers contact selection sheet

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
                            onAccept: { invitationToJoin = invitation },  // Show contact selection
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
            .sheet(item: $invitationToJoin) { invitation in
                JoinTripContactSelectionView(
                    invitation: invitation,
                    onJoin: { contactIds in
                        await acceptInvitation(invitation, withContactIds: contactIds)
                    }
                )
                .environmentObject(session)
            }
        }
    }

    private func acceptInvitation(_ invitation: TripInvitation, withContactIds contactIds: [Int]) async {
        processingTripId = invitation.trip_id
        let success = await session.acceptTripInvitation(tripId: invitation.trip_id, safetyContactIds: contactIds)
        if success {
            // Refresh invitations list
            await session.loadTripInvitations()
            // Also refresh trips list since user is now part of this trip
            _ = await session.loadAllTrips()
        }
        processingTripId = nil
        invitationToJoin = nil
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

// MARK: - Join Trip Contact Selection View

/// View for selecting safety contacts when joining a group trip
struct JoinTripContactSelectionView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    let invitation: TripInvitation
    let onJoin: ([Int]) async -> Void

    @State private var selectedContactIds: Set<Int> = []
    @State private var savedContacts: [Contact] = []
    @State private var isLoading = true
    @State private var isJoining = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Header info
                VStack(spacing: 16) {
                    // Trip info header
                    HStack(spacing: 12) {
                        Text(invitation.activity_icon)
                            .font(.title)
                            .frame(width: 50, height: 50)
                            .background(Color.hbBrand.opacity(0.1))
                            .clipShape(Circle())

                        VStack(alignment: .leading, spacing: 2) {
                            Text(invitation.trip_title)
                                .font(.headline)
                            if let inviter = invitation.inviter_name {
                                Text("Invited by \(inviter)")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                    }
                    .padding()
                    .background(Color(.secondarySystemGroupedBackground))
                    .cornerRadius(12)

                    // Safety contacts explanation
                    HStack(spacing: 12) {
                        Image(systemName: "shield.checkered")
                            .font(.title2)
                            .foregroundStyle(Color.hbBrand)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("Select Your Safety Contacts")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            Text("These contacts will be notified if you don't check in during the trip. Select 1-3 contacts.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding()
                    .background(Color.hbBrand.opacity(0.1))
                    .cornerRadius(12)
                }
                .padding()

                if isLoading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if savedContacts.isEmpty {
                    // No contacts available
                    Spacer()
                    VStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.badge.exclamationmark")
                            .font(.system(size: 50))
                            .foregroundStyle(.secondary)

                        Text("No Contacts Available")
                            .font(.headline)

                        Text("You need to add at least one contact before joining a group trip. Go to Settings > Contacts to add contacts.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                    Spacer()
                } else {
                    // Contact selection list
                    List {
                        Section {
                            ForEach(savedContacts) { contact in
                                JoinTripContactRow(
                                    contact: contact,
                                    isSelected: selectedContactIds.contains(contact.id),
                                    canSelect: selectedContactIds.count < 3 || selectedContactIds.contains(contact.id)
                                ) { selected in
                                    if selected {
                                        selectedContactIds.insert(contact.id)
                                    } else {
                                        selectedContactIds.remove(contact.id)
                                    }
                                }
                            }
                        } header: {
                            Text("\(selectedContactIds.count)/3 contacts selected")
                        } footer: {
                            if selectedContactIds.isEmpty {
                                Text("Select at least one contact to join the trip")
                                    .foregroundStyle(.orange)
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }

                // Join button
                VStack(spacing: 12) {
                    Button(action: {
                        Task {
                            isJoining = true
                            await onJoin(Array(selectedContactIds))
                            isJoining = false
                            dismiss()
                        }
                    }) {
                        HStack {
                            if isJoining {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                    .scaleEffect(0.9)
                            } else {
                                Image(systemName: "person.badge.plus")
                                Text("Join Trip")
                                    .fontWeight(.semibold)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 56)
                        .background(selectedContactIds.isEmpty ? Color.gray : Color.hbBrand)
                        .foregroundStyle(.white)
                        .cornerRadius(16)
                    }
                    .disabled(selectedContactIds.isEmpty || isJoining)
                }
                .padding()
            }
            .navigationTitle("Join Group Trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
            }
            .task {
                savedContacts = await session.loadContacts()
                isLoading = false
            }
        }
    }
}

// MARK: - Join Trip Contact Row

struct JoinTripContactRow: View {
    let contact: Contact
    let isSelected: Bool
    let canSelect: Bool
    let onToggle: (Bool) -> Void

    var body: some View {
        Button(action: {
            if canSelect || isSelected {
                onToggle(!isSelected)
            }
        }) {
            HStack(spacing: 12) {
                // Contact avatar
                Circle()
                    .fill(isSelected ? Color.hbBrand : Color(.secondarySystemFill))
                    .frame(width: 44, height: 44)
                    .overlay(
                        Text(contact.name.prefix(1).uppercased())
                            .font(.headline)
                            .foregroundStyle(isSelected ? .white : .secondary)
                    )

                VStack(alignment: .leading, spacing: 2) {
                    Text(contact.name)
                        .font(.body)
                        .foregroundStyle(.primary)

                    Text(contact.email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Selection indicator
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(isSelected ? Color.hbBrand : .secondary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .opacity(canSelect || isSelected ? 1 : 0.5)
    }
}

#Preview {
    TripInvitationsView()
        .environmentObject(Session())
}
