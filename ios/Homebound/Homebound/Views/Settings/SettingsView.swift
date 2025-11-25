import SwiftUI
import PhotosUI

// MARK: - Main Settings View
struct SettingsView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss
    @State private var showingClearCacheAlert = false

    var body: some View {
        NavigationStack {
            List {
                // Account Section
                Section {
                    NavigationLink(destination: AccountView()) {
                        HStack {
                            // Profile image placeholder
                            Circle()
                                .fill(
                                    LinearGradient(
                                        colors: [Color.hbBrand, Color.hbTeal],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .frame(width: 60, height: 60)
                                .overlay(
                                    Text(String(session.userName?.prefix(1).uppercased() ?? "U"))
                                        .font(.title2)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(.white)
                                )

                            VStack(alignment: .leading, spacing: 4) {
                                Text(session.userName ?? "User")
                                    .font(.headline)
                                Text(session.userEmail ?? "")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()
                        }
                        .padding(.vertical, 8)
                    }
                }

                // Safety Section
                Section("Safety") {
                    NavigationLink(destination: EmergencyContactsView()) {
                        Label {
                            Text("Emergency Contacts")
                        } icon: {
                            Image(systemName: "person.2.fill")
                                .foregroundStyle(.orange)
                        }
                    }
                }

                // App Section
                Section("App") {
                    NavigationLink(destination: NotificationSettingsView()) {
                        Label {
                            Text("Notifications")
                        } icon: {
                            Image(systemName: "bell.fill")
                                .foregroundStyle(.red)
                        }
                    }

                    NavigationLink(destination: PrivacyView()) {
                        Label {
                            Text("Privacy")
                        } icon: {
                            Image(systemName: "lock.fill")
                                .foregroundStyle(.blue)
                        }
                    }

                    NavigationLink(destination: AboutView()) {
                        Label {
                            Text("About")
                        } icon: {
                            Image(systemName: "info.circle.fill")
                                .foregroundStyle(.gray)
                        }
                    }
                }

                // Developer Section
                Section("Developer") {
                    Toggle(isOn: Binding(
                        get: { session.useLocalServer },
                        set: { newValue in
                            session.useLocalServer = newValue
                        }
                    )) {
                        Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Use Local Server")
                                Text(session.useLocalServer ? "Local Mac" : "Render")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "server.rack")
                                .foregroundStyle(session.useLocalServer ? .green : .purple)
                        }
                    }
                }

                // Support Section
                Section("Support") {
                    Link(destination: URL(string: "https://homeboundapp.com/help")!) {
                        Label {
                            HStack {
                                Text("Help Center")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "questionmark.circle.fill")
                                .foregroundStyle(Color.hbBrand)
                        }
                    }

                    Link(destination: URL(string: "mailto:support@homeboundapp.com")!) {
                        Label {
                            HStack {
                                Text("Contact Us")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "envelope.fill")
                                .foregroundStyle(.green)
                        }
                    }
                }

                // Resources Section
                Section("Resources") {
                    Button(action: {
                        // TODO: Implement feature request
                    }) {
                        Label {
                            HStack {
                                Text("Request a Feature")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "lightbulb.fill")
                                .foregroundStyle(.yellow)
                        }
                    }
                    .foregroundStyle(.primary)

                    Button(action: {
                        // TODO: Implement bug report
                    }) {
                        Label {
                            HStack {
                                Text("Report a Bug")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "ladybug.fill")
                                .foregroundStyle(.red)
                        }
                    }
                    .foregroundStyle(.primary)

                    Button(action: {
                        // TODO: Open App Store for rating
                    }) {
                        Label {
                            HStack {
                                Text("Rate in App Store")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "star.fill")
                                .foregroundStyle(.orange)
                        }
                    }
                    .foregroundStyle(.primary)

                    Button(action: {
                        showingClearCacheAlert = true
                    }) {
                        Label {
                            HStack {
                                Text("Clear Cache")
                                Spacer()
                                Image(systemName: "trash")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: "tray.fill")
                                .foregroundStyle(.purple)
                        }
                    }
                    .foregroundStyle(.primary)
                }

                // Version info at bottom
                Section {
                    HStack {
                        Text("Version")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("1.0.0")
                            .foregroundStyle(.secondary)
                    }
                    .listRowBackground(Color.clear)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
            .alert("Clear Cache", isPresented: $showingClearCacheAlert) {
                Button("Cancel", role: .cancel) { }
                Button("Clear", role: .destructive) {
                    LocalStorage.shared.clearAll()
                }
            } message: {
                Text("This will clear all cached trips and activities. Data will be reloaded from the server.")
            }
        }
    }
}

// MARK: - Account View
struct AccountView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var firstName = ""
    @State private var lastName = ""
    @State private var age: Int = 0
    @State private var phone = ""

    @State private var editingFirstName = false
    @State private var editingLastName = false
    @State private var editingAge = false
    @State private var editingPhone = false

    @State private var tempFirstName = ""
    @State private var tempLastName = ""
    @State private var tempAge = ""
    @State private var tempPhone = ""

    @State private var showingImagePicker = false
    @State private var selectedImage: PhotosPickerItem?
    @State private var profileImage: UIImage?

    @State private var showingDeleteAlert = false
    @State private var deleteConfirmation = ""
    @State private var isDeleting = false

    @State private var showingLogoutAlert = false

    var body: some View {
        List {
            // Profile Photo Section
            Section {
                HStack {
                    Spacer()

                    PhotosPicker(selection: $selectedImage, matching: .images) {
                        ZStack {
                            if let profileImage = profileImage {
                                Image(uiImage: profileImage)
                                    .resizable()
                                    .scaledToFill()
                                    .frame(width: 120, height: 120)
                                    .clipShape(Circle())
                            } else {
                                Circle()
                                    .fill(
                                        LinearGradient(
                                            colors: [Color.hbBrand, Color.hbTeal],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                                    .frame(width: 120, height: 120)
                                    .overlay(
                                        Text(String(firstName.prefix(1).uppercased()))
                                            .font(.largeTitle)
                                            .fontWeight(.semibold)
                                            .foregroundStyle(.white)
                                    )
                            }

                            // Camera icon overlay
                            Circle()
                                .fill(Color(.systemBackground))
                                .frame(width: 36, height: 36)
                                .overlay(
                                    Circle()
                                        .stroke(Color(.systemGray4), lineWidth: 1)
                                )
                                .overlay(
                                    Image(systemName: "camera.fill")
                                        .font(.system(size: 16))
                                        .foregroundStyle(Color.hbBrand)
                                )
                                .offset(x: 40, y: 40)
                        }
                    }
                    .onChange(of: selectedImage) { _, newItem in
                        Task {
                            if let data = try? await newItem?.loadTransferable(type: Data.self),
                               let image = UIImage(data: data) {
                                profileImage = image
                            }
                        }
                    }

                    Spacer()
                }
                .listRowBackground(Color.clear)
            }

            // Personal Information Section
            Section("Personal Information") {
                // Email (non-editable)
                HStack {
                    Text("Email")
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text(session.userEmail ?? "")
                        .foregroundStyle(.secondary)
                }

                // First Name
                HStack {
                    Text("First Name")
                        .foregroundStyle(editingFirstName ? Color.hbBrand : .primary)
                    Spacer()
                    if editingFirstName {
                        TextField("First Name", text: $tempFirstName)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                saveFirstName()
                            }
                    } else {
                        Text(firstName.isEmpty ? "Not set" : firstName)
                            .foregroundStyle(firstName.isEmpty ? .secondary : .primary)
                    }

                    Button(action: {
                        if editingFirstName {
                            saveFirstName()
                        } else {
                            tempFirstName = firstName
                            editingFirstName = true
                        }
                    }) {
                        Text(editingFirstName ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }

                // Last Name
                HStack {
                    Text("Last Name")
                        .foregroundStyle(editingLastName ? Color.hbBrand : .primary)
                    Spacer()
                    if editingLastName {
                        TextField("Last Name", text: $tempLastName)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                saveLastName()
                            }
                    } else {
                        Text(lastName.isEmpty ? "Not set" : lastName)
                            .foregroundStyle(lastName.isEmpty ? .secondary : .primary)
                    }

                    Button(action: {
                        if editingLastName {
                            saveLastName()
                        } else {
                            tempLastName = lastName
                            editingLastName = true
                        }
                    }) {
                        Text(editingLastName ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }

                // Age
                HStack {
                    Text("Age")
                        .foregroundStyle(editingAge ? Color.hbBrand : .primary)
                    Spacer()
                    if editingAge {
                        TextField("Age", text: $tempAge)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .keyboardType(.numberPad)
                            .onSubmit {
                                saveAge()
                            }
                    } else {
                        Text(age > 0 ? "\(age)" : "Not set")
                            .foregroundStyle(age > 0 ? .primary : .secondary)
                    }

                    Button(action: {
                        if editingAge {
                            saveAge()
                        } else {
                            tempAge = age > 0 ? "\(age)" : ""
                            editingAge = true
                        }
                    }) {
                        Text(editingAge ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }

                // Phone
                HStack {
                    Text("Phone")
                        .foregroundStyle(editingPhone ? Color.hbBrand : .primary)
                    Spacer()
                    if editingPhone {
                        TextField("Phone", text: $tempPhone)
                            .multilineTextAlignment(.trailing)
                            .textFieldStyle(.plain)
                            .keyboardType(.phonePad)
                            .onSubmit {
                                savePhone()
                            }
                    } else {
                        Text(phone.isEmpty ? "Not set" : phone)
                            .foregroundStyle(phone.isEmpty ? .secondary : .primary)
                    }

                    Button(action: {
                        if editingPhone {
                            savePhone()
                        } else {
                            tempPhone = phone
                            editingPhone = true
                        }
                    }) {
                        Text(editingPhone ? "Save" : "Edit")
                            .font(.subheadline)
                            .foregroundStyle(Color.hbBrand)
                    }
                }
            }

            // Log Out
            Section {
                Button(action: {
                    showingLogoutAlert = true
                }) {
                    HStack {
                        Spacer()
                        Text("Log Out")
                            .foregroundStyle(.red)
                        Spacer()
                    }
                }
            }

            // Delete Account
            Section {
                Button(action: {
                    showingDeleteAlert = true
                }) {
                    HStack {
                        Spacer()
                        if isDeleting {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle())
                                .scaleEffect(0.8)
                        } else {
                            Text("Delete Account")
                                .foregroundStyle(.red)
                        }
                        Spacer()
                    }
                }
                .disabled(isDeleting)
            }
        }
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            loadUserData()
        }
        .alert("Log Out", isPresented: $showingLogoutAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Log Out", role: .destructive) {
                Task {
                    await MainActor.run {
                        session.signOut()
                    }
                }
            }
        } message: {
            Text("Are you sure you want to log out?")
        }
        .alert("Delete Account", isPresented: $showingDeleteAlert) {
            TextField("Type DELETE to confirm", text: $deleteConfirmation)
                .textInputAutocapitalization(.characters)

            Button("Cancel", role: .cancel) {
                deleteConfirmation = ""
            }

            Button("Delete Account", role: .destructive) {
                if deleteConfirmation == "DELETE" {
                    Task {
                        await deleteAccount()
                    }
                }
            }
            .disabled(deleteConfirmation != "DELETE")
        } message: {
            Text("This action cannot be undone. All your data will be permanently deleted. Type DELETE to confirm.")
        }
    }

    private func loadUserData() {
        // Parse full name into first and last
        if let fullName = session.userName {
            let components = fullName.split(separator: " ", maxSplits: 1)
            firstName = String(components.first ?? "")
            lastName = components.count > 1 ? String(components[1]) : ""
        }
        age = session.userAge ?? 0
        phone = session.userPhone ?? ""
    }

    private func saveFirstName() {
        firstName = tempFirstName
        updateProfile()
        editingFirstName = false
    }

    private func saveLastName() {
        lastName = tempLastName
        updateProfile()
        editingLastName = false
    }

    private func saveAge() {
        if let ageValue = Int(tempAge), ageValue > 0 && ageValue < 150 {
            age = ageValue
            updateProfile()
        }
        editingAge = false
    }

    private func savePhone() {
        phone = tempPhone
        updateProfile()
        editingPhone = false
    }

    private func updateProfile() {
        Task {
            let trimmedFirstName = firstName.trimmingCharacters(in: .whitespacesAndNewlines)
            let trimmedLastName = lastName.trimmingCharacters(in: .whitespacesAndNewlines)
            _ = await session.updateProfile(
                firstName: trimmedFirstName.isEmpty ? nil : trimmedFirstName,
                lastName: trimmedLastName.isEmpty ? nil : trimmedLastName,
                age: age > 0 ? age : nil,
                phone: phone.isEmpty ? nil : phone
            )
        }
    }

    private func deleteAccount() async {
        isDeleting = true
        let success = await session.deleteAccount()
        if !success {
            isDeleting = false
        }
    }
}

// MARK: - Placeholder Views
struct NotificationSettingsView: View {
    var body: some View {
        List {
            Section("Push Notifications") {
                Toggle("Trip Reminders", isOn: .constant(true))
                Toggle("Check-in Alerts", isOn: .constant(true))
                Toggle("Emergency Notifications", isOn: .constant(true))
            }
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct PrivacyView: View {
    var body: some View {
        List {
            Section("Data & Privacy") {
                Text("Your data is encrypted and secure")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Privacy")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct AboutView: View {
    var body: some View {
        List {
            Section {
                HStack {
                    Text("Version")
                    Spacer()
                    Text("1.0.0")
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Text("Build")
                    Spacer()
                    Text("100")
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                Link("Terms of Service", destination: URL(string: "https://homeboundapp.com/terms")!)
                Link("Privacy Policy", destination: URL(string: "https://homeboundapp.com/privacy")!)
            }
        }
        .navigationTitle("About")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    SettingsView()
        .environmentObject(Session())
}