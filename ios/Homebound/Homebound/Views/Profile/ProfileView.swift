import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    // Editable fields
    @State private var editingName = false
    @State private var editName = ""
    @State private var editingAge = false
    @State private var editAge = ""

    // UI State
    @State private var showSignOutAlert = false
    @State private var showDeleteAccount = false
    @State private var confirmDeleteText = ""
    @State private var isDeleting = false
    @State private var isSaving = false
    @State private var showError = false
    @State private var errorMessage = ""

    var body: some View {
        NavigationStack {
            ZStack {
                // Background
                Color(.systemBackground)
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Profile Header
                        ProfileHeaderSection()

                        // Personal Information
                        VStack(alignment: .leading, spacing: 20) {
                            SectionHeader(title: "Personal Information", icon: "person.fill")

                            // Name Field
                            EditableField(
                                label: "Name",
                                value: session.userName ?? "Not set",
                                icon: "person.fill",
                                isEditing: $editingName,
                                editValue: $editName,
                                onSave: { await updateName() }
                            )

                            // Email Field (non-editable)
                            InfoField(
                                label: "Email",
                                value: session.userEmail ?? "Not set",
                                icon: "envelope.fill"
                            )

                            // Age Field
                            EditableField(
                                label: "Age",
                                value: session.userAge != nil ? "\(session.userAge!)" : "Not set",
                                icon: "calendar",
                                isEditing: $editingAge,
                                editValue: $editAge,
                                keyboardType: .numberPad,
                                onSave: { await updateAge() }
                            )
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )

                        // Account Settings
                        VStack(alignment: .leading, spacing: 20) {
                            SectionHeader(title: "Account Settings", icon: "gearshape.fill")

                            // Member Since
                            InfoField(
                                label: "Member Since",
                                value: formatMemberSince(session.memberSince),
                                icon: "clock.fill"
                            )

                            // Sign Out Button
                            Button(action: { showSignOutAlert = true }) {
                                HStack {
                                    Image(systemName: "arrow.left.square.fill")
                                    Text("Sign Out")
                                    Spacer()
                                }
                                .padding()
                                .background(Color(.tertiarySystemFill))
                                .foregroundStyle(.primary)
                                .cornerRadius(12)
                            }
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )

                        // Danger Zone
                        VStack(alignment: .leading, spacing: 20) {
                            HStack {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundStyle(.red)
                                Text("Danger Zone")
                                    .font(.headline)
                                    .foregroundStyle(.red)
                            }

                            Text("Once you delete your account, there is no going back. All your data will be permanently removed.")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Button(action: { showDeleteAccount = true }) {
                                HStack {
                                    Image(systemName: "trash.fill")
                                    Text("Delete Account")
                                    Spacer()
                                }
                                .padding()
                                .background(Color.red.opacity(0.1))
                                .foregroundStyle(.red)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.red.opacity(0.3), lineWidth: 1)
                                )
                            }
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )
                    }
                    .padding()
                    .padding(.bottom, 50)
                }
                .scrollIndicators(.hidden)
                .scrollDismissesKeyboard(.interactively)
            }
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .alert("Sign Out", isPresented: $showSignOutAlert) {
                Button("Cancel", role: .cancel) {}
                Button("Sign Out", role: .destructive) {
                    session.signOut()
                    dismiss()
                }
            } message: {
                Text("Are you sure you want to sign out?")
            }
            .alert("Delete Account", isPresented: $showDeleteAccount) {
                TextField("Type 'DELETE' to confirm", text: $confirmDeleteText)
                    .textInputAutocapitalization(.characters)
                Button("Cancel", role: .cancel) {
                    confirmDeleteText = ""
                }
                Button("Delete Forever", role: .destructive) {
                    if confirmDeleteText == "DELETE" {
                        Task {
                            await deleteAccount()
                        }
                    }
                }
                .disabled(confirmDeleteText != "DELETE")
            } message: {
                Text("This action cannot be undone. All your trips, contacts, and personal information will be permanently deleted. Type DELETE to confirm.")
            }
            .alert("Error", isPresented: $showError) {
                Button("OK") {}
            } message: {
                Text(errorMessage)
            }
        }
    }

    // MARK: - Helper Functions

    private func formatMemberSince(_ date: Date?) -> String {
        guard let date = date else {
            return "Unknown"
        }
        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM yyyy"
        return formatter.string(from: date)
    }

    func updateName() async {
        guard !editName.isEmpty else {
            editingName = false
            return
        }

        // Split name into first and last
        let components = editName.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
        let firstName = components.first.map(String.init) ?? editName
        let lastName = components.count > 1 ? String(components[1]) : ""

        isSaving = true
        let success = await session.updateProfile(firstName: firstName, lastName: lastName, age: nil)
        isSaving = false

        if success {
            editingName = false
            editName = ""
        } else {
            errorMessage = "Failed to update name"
            showError = true
        }
    }

    func updateAge() async {
        // Validate age input
        guard let age = Int(editAge) else {
            errorMessage = "Please enter a valid number for age"
            showError = true
            return
        }

        guard age > 0 && age < 150 else {
            errorMessage = "Please enter a valid age (1-149)"
            showError = true
            return
        }

        isSaving = true
        let success = await session.updateProfile(firstName: nil, lastName: nil, age: age)
        isSaving = false

        if success {
            editingAge = false
            editAge = ""
        } else {
            errorMessage = "Failed to update age"
            showError = true
        }
    }

    func deleteAccount() async {
        isDeleting = true
        let success = await session.deleteAccount()
        isDeleting = false

        if success {
            dismiss()
        } else {
            errorMessage = "Failed to delete account. Please try again."
            showError = true
        }
    }
}

// MARK: - Supporting Views

struct ProfileHeaderSection: View {
    @EnvironmentObject var session: Session

    var body: some View {
        VStack(spacing: 16) {
            // Avatar
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
                    Text(session.userName?.prefix(1).uppercased() ?? "?")
                        .font(.system(size: 40, weight: .bold))
                        .foregroundStyle(.white)
                )

            // Name and Email
            VStack(spacing: 4) {
                Text(session.userName ?? "Adventurer")
                    .font(.title2)
                    .fontWeight(.bold)

                Text(session.userEmail ?? "")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.top)
    }
}

struct EditableField: View {
    let label: String
    let value: String
    let icon: String
    @Binding var isEditing: Bool
    @Binding var editValue: String
    var keyboardType: UIKeyboardType = .default
    let onSave: () async -> Void

    var body: some View {
        HStack {
            Label(label, systemImage: icon)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(width: 100, alignment: .leading)

            if isEditing {
                TextField(label, text: $editValue)
                    .textFieldStyle(.plain)
                    .keyboardType(keyboardType)
                    .onSubmit {
                        Task {
                            await onSave()
                        }
                    }

                Button("Save") {
                    Task {
                        await onSave()
                    }
                }
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(Color.hbBrand)

                Button("Cancel") {
                    isEditing = false
                    editValue = ""
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            } else {
                Text(value)
                    .font(.subheadline)

                Spacer()

                Button(action: {
                    editValue = value == "Not set" ? "" : value
                    isEditing = true
                }) {
                    Text("Edit")
                        .font(.caption)
                        .foregroundStyle(Color.hbBrand)
                }
            }
        }
        .padding(.vertical, 8)
    }
}

struct InfoField: View {
    let label: String
    let value: String
    let icon: String

    var body: some View {
        HStack {
            Label(label, systemImage: icon)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(width: 100, alignment: .leading)

            Text(value)
                .font(.subheadline)

            Spacer()
        }
        .padding(.vertical, 8)
    }
}

struct SectionHeader: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.headline)
            .foregroundStyle(.primary)
    }
}

#Preview {
    ProfileView()
        .environmentObject(Session())
}