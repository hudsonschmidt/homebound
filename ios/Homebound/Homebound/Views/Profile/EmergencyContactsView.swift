import SwiftUI

struct EmergencyContactsView: View {
    @EnvironmentObject var session: Session
    @State private var savedContacts: [Contact] = []
    @State private var showingAddContact = false
    @State private var newContactName = ""
    @State private var newContactEmail = ""
    @State private var isLoading = true
    @State private var showError = false
    @State private var errorMessage = ""
    @State private var hasLoadedInitially = false
    @State private var contactToEdit: Contact?

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
                                ContactRow(contact: contact)
                                    .contentShape(Rectangle())
                                    .onTapGesture {
                                        contactToEdit = contact
                                    }
                            }
                            .onDelete(perform: deleteContacts)
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

                            Text("Swipe left on a contact to delete it, or tap to edit.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 8)
                    }
                    .listRowBackground(Color(.secondarySystemBackground))
                }
                .scrollIndicators(.hidden)
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
                email: $newContactEmail,
                showingSheet: $showingAddContact,
                onAdd: {
                    Task {
                        await addContact()
                    }
                }
            )
        }
        .sheet(item: $contactToEdit) { contact in
            EditEmergencyContactSheet(
                contact: contact,
                onSave: { name, email in
                    Task {
                        await updateContact(contact: contact, name: name, email: email)
                    }
                },
                onDismiss: {
                    contactToEdit = nil
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
        isLoading = true
        let contacts = await session.loadContacts()
        await MainActor.run {
            self.savedContacts = contacts
            self.isLoading = false
        }
    }

    private func addContact() async {
        let savedContact = await session.addContact(
            name: newContactName,
            email: newContactEmail
        )

        if let savedContact = savedContact {
            await MainActor.run {
                savedContacts.append(savedContact)
                newContactName = ""
                newContactEmail = ""
                showingAddContact = false
            }
        } else {
            await MainActor.run {
                errorMessage = session.lastError.isEmpty ? "Failed to add contact. Please try again." : session.lastError
                showError = true
            }
        }
    }

    private func updateContact(contact: Contact, name: String, email: String) async {
        let success = await session.updateContact(contactId: contact.id, name: name, email: email)
        if success {
            await MainActor.run {
                if let index = savedContacts.firstIndex(where: { $0.id == contact.id }) {
                    savedContacts[index] = Contact(id: contact.id, user_id: contact.user_id, name: name, email: email)
                }
                contactToEdit = nil
            }
        } else {
            await MainActor.run {
                errorMessage = session.lastError.isEmpty ? "Failed to update contact. Please try again." : session.lastError
                showError = true
            }
        }
    }

    private func deleteContacts(at offsets: IndexSet) {
        for index in offsets {
            let contact = savedContacts[index]
            Task {
                let success = await session.deleteContact(contact.id)
                if success {
                    await MainActor.run {
                        savedContacts.removeAll { $0.id == contact.id }
                    }
                } else {
                    await MainActor.run {
                        errorMessage = session.lastError.isEmpty ? "Failed to delete contact." : session.lastError
                        showError = true
                    }
                }
            }
        }
    }
}

// MARK: - Saved Contact Row
struct ContactRow: View {
    let contact: Contact

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

                if !contact.email.isEmpty {
                    Text(contact.email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Add Contact Sheet
struct AddEmergencyContactSheet: View {
    @Binding var name: String
    @Binding var email: String
    @Binding var showingSheet: Bool
    let onAdd: () -> Void
    @Environment(\.dismiss) var dismiss

    var isValid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        email.contains("@")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Contact Information") {
                    TextField("Name", text: $name)
                        .textContentType(.name)
                        .autocapitalization(.words)

                    TextField("Email", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
                }

                Section {
                    Text("This contact will be saved to your account for quick selection when creating trips. They will receive email notifications about your trips.")
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
                        onAdd()
                    }
                    .fontWeight(.semibold)
                    .disabled(!isValid)
                }
            }
        }
    }
}

// MARK: - Edit Contact Sheet
struct EditEmergencyContactSheet: View {
    let contact: Contact
    let onSave: (String, String) -> Void
    let onDismiss: () -> Void

    @State private var name: String = ""
    @State private var email: String = ""
    @Environment(\.dismiss) var dismiss

    var isValid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        email.contains("@")
    }

    var hasChanges: Bool {
        name != contact.name || email != contact.email
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Contact Information") {
                    TextField("Name", text: $name)
                        .textContentType(.name)
                        .autocapitalization(.words)

                    TextField("Email", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
                }

                Section {
                    Text("Update this contact's information. They will receive email notifications about your trips.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Edit Contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        onDismiss()
                        dismiss()
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        onSave(name, email)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .disabled(!isValid || !hasChanges)
                }
            }
            .onAppear {
                name = contact.name
                email = contact.email
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
