import SwiftUI

/// View showing pending trip invitations the user has received
struct TripInvitationsView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var isLoading = false
    @State private var hasLoadedOnce = false
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
                guard !hasLoadedOnce else { return }
                hasLoadedOnce = true
                isLoading = true
                await session.loadTripInvitations()
                isLoading = false
            }
            .sheet(item: $invitationToJoin, onDismiss: {
                // Do nothing on dismiss - invitation remains in list unless explicitly accepted/declined
            }) { invitation in
                JoinTripContactSelectionView(
                    invitation: invitation,
                    onJoin: { contactIds, checkinInterval, notifyStart, notifyEnd in
                        await acceptInvitation(
                            invitation,
                            withContactIds: contactIds,
                            checkinInterval: checkinInterval,
                            notifyStart: notifyStart,
                            notifyEnd: notifyEnd
                        )
                    }
                )
                .environmentObject(session)
            }
        }
    }

    private func acceptInvitation(
        _ invitation: TripInvitation,
        withContactIds contactIds: [Int],
        checkinInterval: Int,
        notifyStart: Int?,
        notifyEnd: Int?
    ) async {
        processingTripId = invitation.trip_id
        let success = await session.acceptTripInvitation(
            tripId: invitation.trip_id,
            safetyContactIds: contactIds,
            checkinIntervalMin: checkinInterval,
            notifyStartHour: notifyStart,
            notifyEndHour: notifyEnd
        )
        if success {
            // Refresh invitations list
            await session.loadTripInvitations()
            // Also refresh trips list since user is now part of this trip
            _ = await session.loadAllTrips()
            // Close the contact selection sheet
            invitationToJoin = nil
            // Close TripInvitationsView and return to Friends page
            dismiss()
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

// MARK: - Join Trip Contact Selection View

/// View for selecting safety contacts when joining a group trip
struct JoinTripContactSelectionView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    let invitation: TripInvitation
    let onJoin: ([Int], Int, Int?, Int?) async -> Void

    @State private var selectedContactIds: Set<Int> = []
    @State private var savedContacts: [Contact] = []
    @State private var isLoading = true
    @State private var isJoining = false

    // Notification settings
    @State private var checkinInterval: Int = 30
    @State private var useQuietHours: Bool = false
    @State private var notifyStartHour: Int = 8
    @State private var notifyEndHour: Int = 22

    // Add contact state
    @State private var showAddContact: Bool = false
    @State private var newContactName: String = ""
    @State private var newContactEmail: String = ""
    @State private var isAddingContact: Bool = false

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
                            Text("Your Personal Safety Settings")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            Text("Configure your own check-in frequency and contacts. These settings are personal to you and separate from other participants.")
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
                } else if savedContacts.isEmpty && !showAddContact {
                    // No contacts available - show add contact option
                    Spacer()
                    VStack(spacing: 20) {
                        Image(systemName: "person.crop.circle.badge.plus")
                            .font(.system(size: 50))
                            .foregroundStyle(Color.hbBrand)

                        Text("Add a Safety Contact")
                            .font(.headline)

                        Text("You need at least one safety contact before joining. They'll be notified if you don't check in during the trip.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)

                        Button(action: { showAddContact = true }) {
                            HStack {
                                Image(systemName: "plus.circle.fill")
                                Text("Add Contact")
                                    .fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(Color.hbBrand)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                        }
                        .padding(.horizontal, 40)
                    }
                    Spacer()
                } else if showAddContact || savedContacts.isEmpty {
                    // Add contact form
                    List {
                        Section {
                            TextField("Name", text: $newContactName)
                                .textContentType(.name)
                                .autocapitalization(.words)

                            TextField("Email", text: $newContactEmail)
                                .textContentType(.emailAddress)
                                .keyboardType(.emailAddress)
                                .autocapitalization(.none)
                        } header: {
                            Text("New Contact")
                        } footer: {
                            Text("This person will receive an email if you don't check in on time.")
                        }

                        Section {
                            Button(action: {
                                Task {
                                    await addContact()
                                }
                            }) {
                                HStack {
                                    if isAddingContact {
                                        ProgressView()
                                            .progressViewStyle(CircularProgressViewStyle())
                                            .scaleEffect(0.8)
                                    } else {
                                        Image(systemName: "plus.circle.fill")
                                        Text("Save Contact")
                                    }
                                }
                                .frame(maxWidth: .infinity)
                                .foregroundStyle(canAddContact ? Color.hbBrand : .secondary)
                            }
                            .disabled(!canAddContact || isAddingContact)
                        }

                        if !savedContacts.isEmpty {
                            Section {
                                Button("Cancel") {
                                    showAddContact = false
                                    newContactName = ""
                                    newContactEmail = ""
                                }
                                .frame(maxWidth: .infinity)
                                .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                } else {
                    // Contact selection list and notification settings
                    List {
                        // Safety contacts section
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

                        // Check-in frequency section
                        Section {
                            Picker("Check-in Frequency", selection: $checkinInterval) {
                                Text("Every 15 minutes").tag(15)
                                Text("Every 30 minutes").tag(30)
                                Text("Every hour").tag(60)
                                Text("Every 2 hours").tag(120)
                            }
                        } header: {
                            Text("Check-in Settings")
                        } footer: {
                            Text("How often you'll need to check in during the trip. If you miss a check-in, your contacts will be notified.")
                        }

                        // Quiet hours section
                        Section {
                            Toggle("Enable Quiet Hours", isOn: $useQuietHours)

                            if useQuietHours {
                                Picker("Start Time", selection: $notifyStartHour) {
                                    ForEach(0..<24, id: \.self) { hour in
                                        Text(formatHour(hour)).tag(hour)
                                    }
                                }

                                Picker("End Time", selection: $notifyEndHour) {
                                    ForEach(0..<24, id: \.self) { hour in
                                        Text(formatHour(hour)).tag(hour)
                                    }
                                }
                            }
                        } header: {
                            Text("Notification Hours")
                        } footer: {
                            if useQuietHours {
                                Text("You'll only receive check-in reminders between \(formatHour(notifyStartHour)) and \(formatHour(notifyEndHour)).")
                            } else {
                                Text("You'll receive check-in reminders at any time during the trip.")
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
                            await onJoin(
                                Array(selectedContactIds),
                                checkinInterval,
                                useQuietHours ? notifyStartHour : nil,
                                useQuietHours ? notifyEndHour : nil
                            )
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

    private func formatHour(_ hour: Int) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "h a"
        let date = Calendar.current.date(from: DateComponents(hour: hour)) ?? Date()
        return formatter.string(from: date)
    }

    private var canAddContact: Bool {
        !newContactName.trimmingCharacters(in: .whitespaces).isEmpty &&
        !newContactEmail.trimmingCharacters(in: .whitespaces).isEmpty &&
        newContactEmail.contains("@")
    }

    private func addContact() async {
        isAddingContact = true
        let contact = await session.addContact(
            name: newContactName.trimmingCharacters(in: .whitespaces),
            email: newContactEmail.trimmingCharacters(in: .whitespaces)
        )
        if let contact = contact {
            savedContacts.append(contact)
            selectedContactIds.insert(contact.id)
            showAddContact = false
            newContactName = ""
            newContactEmail = ""
        }
        isAddingContact = false
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
