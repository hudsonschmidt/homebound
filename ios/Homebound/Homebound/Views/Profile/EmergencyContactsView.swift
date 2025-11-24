import SwiftUI

struct EmergencyContactsView: View {
    @EnvironmentObject var session: Session
    @State private var savedContacts: [Contact] = []
    @State private var showingAddContact = false
    @State private var newContactName = ""
    @State private var newContactPhone = ""
    @State private var newContactEmail = ""
    @State private var isLoading = true
    @State private var showError = false
    @State private var errorMessage = ""
    @State private var hasLoadedInitially = false

    var body: some View {
        ZStack {
            if isLoading {
                ProgressView("Loading contacts...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    // Add Contact Button
                    if savedContacts.count < 10 {  // Reasonable limit for saved contacts
                        Section {
                            Button(action: {
                                showingAddContact = true
                            }) {
                                HStack {
                                    Image(systemName: "plus.circle.fill")
                                        .font(.title2)
                                        .foregroundStyle(Color.hbBrand)
                                    Text("Add Emergency Contact")
                                        .fontWeight(.medium)
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                            }
                        }
                    }

                    // Saved Contacts
                    if !savedContacts.isEmpty {
                        Section("Saved Contacts") {
                            ForEach(savedContacts) { contact in
                                ContactRow(
                                    contact: contact,
                                    onDelete: {
                                        deleteContact(contact)
                                    }
                                )
                            }
                        }
                        .headerProminence(.increased)
                    }

                    // Information Section
                    Section {
                        VStack(alignment: .leading, spacing: 12) {
                            Label {
                                Text("About Emergency Contacts")
                                    .font(.headline)
                            } icon: {
                                Image(systemName: "info.circle.fill")
                                    .foregroundStyle(Color.hbBrand)
                            }

                            Text("Save frequently used emergency contacts for quick selection when creating trips. You can save up to 10 contacts.")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Text("When creating a trip, you must select between 1-3 emergency contacts who will be notified if you don't check in on time.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 8)
                    }
                    .listRowBackground(Color(.secondarySystemBackground))
                }
            }
        }
        .navigationTitle("Emergency Contacts")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            // Only load contacts on initial view appearance
            if !hasLoadedInitially {
                await loadContacts()
                hasLoadedInitially = true
            }
        }
        .sheet(isPresented: $showingAddContact) {
            AddEmergencyContactSheet(
                name: $newContactName,
                phone: $newContactPhone,
                email: $newContactEmail,
                showingSheet: $showingAddContact,
                onAdd: {
                    Task {
                        print("DEBUG: onAdd callback triggered")
                        await addContact()
                    }
                }
            )
        }
        .alert("Error", isPresented: $showError) {
            Button("OK") { }
        } message: {
            Text(errorMessage)
        }
    }

    private func loadContacts() async {
        print("DEBUG loadContacts: Starting to load contacts")
        isLoading = true
        let contacts = await session.loadContacts()
        print("DEBUG loadContacts: Loaded \(contacts.count) contacts from server")
        await MainActor.run {
            print("DEBUG loadContacts: Updating UI with contacts")
            self.savedContacts = contacts
            self.isLoading = false
            print("DEBUG loadContacts: UI updated, savedContacts now has \(self.savedContacts.count) items")
        }
    }

    private func addContact() async {
        print("DEBUG: Starting addContact()")
        print("DEBUG: Contact Name: \(newContactName)")
        print("DEBUG: Contact Phone: \(newContactPhone)")
        print("DEBUG: Contact Email: \(newContactEmail)")

        let savedContact = await session.addContact(
            name: newContactName,
            phone: newContactPhone.isEmpty ? nil : newContactPhone,
            email: newContactEmail.isEmpty ? nil : newContactEmail
        )
        print("DEBUG: addContact returned: \(String(describing: savedContact))")

        if let savedContact = savedContact {
            print("DEBUG: Contact saved successfully, updating UI...")
            await MainActor.run {
                print("DEBUG: Before append - savedContacts count: \(savedContacts.count)")
                // Use the contact returned from the server (with server ID)
                savedContacts.append(savedContact)
                print("DEBUG: After append - savedContacts count: \(savedContacts.count)")
                print("DEBUG: Contacts in list: \(savedContacts)")

                // Clear the form
                newContactName = ""
                newContactPhone = ""
                newContactEmail = ""
                showingAddContact = false
                print("DEBUG: Contact added successfully and sheet dismissed")
            }
            // Don't reload contacts here - it causes a race condition where the
            // server hasn't fully committed the new contact yet
        } else {
            await MainActor.run {
                print("DEBUG: Save failed. Session error: \(session.lastError)")
                errorMessage = session.lastError.isEmpty ? "Failed to add contact. Please try again." : session.lastError
                showError = true
            }
        }
    }

    private func deleteContact(_ contact: Contact) {
        Task {
            let success = await session.deleteContact(contact.id)
            if success {
                await MainActor.run {
                    savedContacts.removeAll { $0.id == contact.id }
                }
            }
        }
    }
}

// MARK: - Saved Contact Row
struct ContactRow: View {
    let contact: Contact
    let onDelete: () -> Void
    @State private var showDeleteAlert = false

    var body: some View {
        HStack {
            // Contact Icon
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color.hbBrand, Color.hbTeal],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 44, height: 44)
                .overlay(
                    Text(contact.name.prefix(1).uppercased())
                        .font(.headline)
                        .foregroundStyle(.white)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(contact.name)
                    .font(.subheadline)
                    .fontWeight(.medium)

                if let phone = contact.phone, !phone.isEmpty {
                    Text(phone)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let email = contact.email, !email.isEmpty {
                    Text(email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            Button(action: {
                showDeleteAlert = true
            }) {
                Image(systemName: "trash")
                    .font(.callout)
                    .foregroundStyle(.red)
            }
        }
        .padding(.vertical, 4)
        .alert("Delete Contact", isPresented: $showDeleteAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Delete", role: .destructive) {
                onDelete()
            }
        } message: {
            Text("Are you sure you want to delete \(contact.name)?")
        }
    }
}

// MARK: - Add Contact Sheet
struct AddEmergencyContactSheet: View {
    @Binding var name: String
    @Binding var phone: String
    @Binding var email: String
    @Binding var showingSheet: Bool
    let onAdd: () -> Void
    @Environment(\.dismiss) var dismiss

    var isValid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !phone.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Contact Information") {
                    TextField("Name", text: $name)
                        .textContentType(.name)
                        .autocapitalization(.words)

                    TextField("Phone Number", text: $phone)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)

                    TextField("Email (Optional)", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
                }

                Section {
                    Text("This contact will be saved to your account for quick selection when creating trips.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("New Contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Add") {
                        print("DEBUG AddEmergencyContactSheet: Add button tapped")
                        print("DEBUG AddEmergencyContactSheet: isValid = \(isValid)")
                        print("DEBUG AddEmergencyContactSheet: Calling onAdd()")
                        onAdd()
                        // Don't dismiss immediately - let the async function handle it
                    }
                    .fontWeight(.semibold)
                    .disabled(!isValid)
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        EmergencyContactsView()
            .environmentObject(Session())
    }
}