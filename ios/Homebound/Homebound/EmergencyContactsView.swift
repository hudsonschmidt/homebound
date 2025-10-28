import SwiftUI

struct EmergencyContactsView: View {
    @EnvironmentObject var session: Session
    @State private var savedContacts: [SavedContact] = []
    @State private var showingAddContact = false
    @State private var newContactName = ""
    @State private var newContactPhone = ""
    @State private var newContactEmail = ""
    @State private var isLoading = true
    @State private var showError = false
    @State private var errorMessage = ""

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
                                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
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
                                SavedContactRow(
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
                                    .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
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
            await loadContacts()
        }
        .sheet(isPresented: $showingAddContact) {
            AddEmergencyContactSheet(
                name: $newContactName,
                phone: $newContactPhone,
                email: $newContactEmail,
                onAdd: {
                    Task {
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
        isLoading = true
        let contacts = await session.loadSavedContacts()
        await MainActor.run {
            self.savedContacts = contacts
            self.isLoading = false
        }
    }

    private func addContact() async {
        let contact = SavedContact(
            id: UUID().uuidString,
            name: newContactName,
            phone: newContactPhone,
            email: newContactEmail.isEmpty ? nil : newContactEmail
        )

        let success = await session.addSavedContact(contact)
        if success {
            await MainActor.run {
                savedContacts.append(contact)
                newContactName = ""
                newContactPhone = ""
                newContactEmail = ""
                showingAddContact = false
            }
        } else {
            await MainActor.run {
                errorMessage = "Failed to add contact"
                showError = true
            }
        }
    }

    private func deleteContact(_ contact: SavedContact) {
        Task {
            let success = await session.deleteSavedContact(contact.id)
            if success {
                await MainActor.run {
                    savedContacts.removeAll { $0.id == contact.id }
                }
            }
        }
    }
}

// MARK: - Saved Contact Row
struct SavedContactRow: View {
    let contact: SavedContact
    let onDelete: () -> Void
    @State private var showDeleteAlert = false

    var body: some View {
        HStack {
            // Contact Icon
            Circle()
                .fill(
                    LinearGradient(
                        colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
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

                Text(contact.phone)
                    .font(.caption)
                    .foregroundStyle(.secondary)

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
                        onAdd()
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .disabled(!isValid)
                }
            }
        }
    }
}

// MARK: - Saved Contact Model
struct SavedContact: Identifiable, Codable {
    let id: String
    let name: String
    let phone: String
    let email: String?
}

#Preview {
    NavigationStack {
        EmergencyContactsView()
            .environmentObject(Session())
    }
}