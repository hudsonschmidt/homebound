import SwiftUI

struct CreatePlanView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    // Form fields
    @State private var planTitle = ""
    @State private var selectedActivity = "other"
    @State private var location = ""
    @State private var startTime = Date()
    @State private var duration: Double = 2 // hours
    @State private var graceMinutes: Double = 30
    @State private var notes = ""

    // Contact management
    @State private var contacts: [EmergencyContact] = []
    @State private var showAddContact = false
    @State private var newContactName = ""
    @State private var newContactPhone = ""

    // UI State
    @State private var isCreating = false
    @State private var showError = false
    @State private var errorMessage = ""

    // Activities array for the selector
    let activities = ActivityType.allCases

    var etaTime: Date {
        let hoursInSeconds = duration * 3600
        return startTime.addingTimeInterval(hoursInSeconds)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Background - adapts to dark mode
                Color(.systemBackground)
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Plan Details Card
                        VStack(alignment: .leading, spacing: 20) {
                            SectionHeader(title: "Trip Details", icon: "map.fill")

                            // Title
                            FloatingLabelTextField(
                                placeholder: "What's your adventure?",
                                text: $planTitle,
                                icon: "pencil"
                            )

                            // Activity Type
                            VStack(alignment: .leading, spacing: 8) {
                                Label("Activity Type", systemImage: "figure.walk")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)

                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 12) {
                                        ForEach(activities, id: \.self) { activity in
                                            ActivityChip(
                                                activity: activity,
                                                isSelected: selectedActivity == activity.rawValue,
                                                action: { selectedActivity = activity.rawValue }
                                            )
                                        }
                                    }
                                }
                            }

                            // Location
                            FloatingLabelTextField(
                                placeholder: "Where are you going?",
                                text: $location,
                                icon: "location.fill"
                            )
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )

                        // Time Settings Card
                        VStack(alignment: .leading, spacing: 20) {
                            SectionHeader(title: "Time Settings", icon: "clock.fill")

                            // Start Time
                            VStack(alignment: .leading, spacing: 8) {
                                Label("Departure Time", systemImage: "calendar.badge.clock")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)

                                DatePicker(
                                    "",
                                    selection: $startTime,
                                    in: Date()...,
                                    displayedComponents: [.date, .hourAndMinute]
                                )
                                .datePickerStyle(.compact)
                                .labelsHidden()
                            }

                            // Duration Slider
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Label("Expected Duration", systemImage: "timer")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\(Int(duration)) hours")
                                        .font(.subheadline)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                                }

                                Slider(value: $duration, in: 0.5...24, step: 0.5)
                                    .tint(Color(hex: "#6C63FF") ?? .purple)
                            }

                            // ETA Display
                            HStack {
                                Label("Expected Return", systemImage: "house.arrival")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(etaTime, style: .date)
                                    .fontWeight(.medium)
                                +
                                Text(" at ")
                                    .fontWeight(.medium)
                                +
                                Text(etaTime, style: .time)
                                    .fontWeight(.medium)
                            }
                            .padding()
                            .background(
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(Color(.tertiarySystemFill))
                            )

                            // Grace Period
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Label("Grace Period", systemImage: "hourglass")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\(Int(graceMinutes)) minutes")
                                        .font(.subheadline)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(.orange)
                                }

                                Slider(value: $graceMinutes, in: 15...120, step: 15)
                                    .tint(.orange)

                                Text("We'll notify your contacts if you don't check in by \(Int(graceMinutes)) minutes after your ETA")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )

                        // Emergency Contacts Card
                        VStack(alignment: .leading, spacing: 20) {
                            HStack {
                                SectionHeader(title: "Emergency Contacts", icon: "person.2.fill")
                                Spacer()
                                Button(action: { showAddContact = true }) {
                                    Image(systemName: "plus.circle.fill")
                                        .font(.title2)
                                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                                }
                            }

                            if contacts.isEmpty {
                                HStack {
                                    Image(systemName: "person.crop.circle.badge.exclamationmark")
                                        .font(.title3)
                                        .foregroundStyle(.orange)
                                    Text("Add at least one emergency contact")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(Color.orange.opacity(0.1))
                                )
                            } else {
                                ForEach(contacts) { contact in
                                    ContactRow(contact: contact) {
                                        contacts.removeAll { $0.id == contact.id }
                                    }
                                }
                            }
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )

                        // Notes Card
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Additional Notes", icon: "note.text")

                            TextField("Any additional details...", text: $notes, axis: .vertical)
                                .textFieldStyle(.plain)
                                .lineLimit(3...6)
                                .padding(12)
                                .background(
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(Color.gray.opacity(0.1))
                                )
                        }
                        .padding(20)
                        .background(
                            RoundedRectangle(cornerRadius: 20)
                                .fill(Color(.secondarySystemBackground))
                                .shadow(color: .black.opacity(0.05), radius: 10, x: 0, y: 2)
                        )

                        // Create Button
                        Button(action: createPlan) {
                            HStack {
                                if isCreating {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                        .scaleEffect(0.9)
                                } else {
                                    Image(systemName: "checkmark.circle.fill")
                                    Text("Start Adventure")
                                        .fontWeight(.semibold)
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(
                                LinearGradient(
                                    colors: canCreatePlan ?
                                        [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal] :
                                        [Color.gray, Color.gray.opacity(0.8)],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .foregroundStyle(.white)
                            .cornerRadius(16)
                        }
                        .disabled(!canCreatePlan || isCreating)
                        .padding(.top, 10)
                    }
                    .padding()
                }
            }
            .navigationTitle("New Adventure")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
            }
            .sheet(isPresented: $showAddContact) {
                AddContactSheet(
                    name: $newContactName,
                    phone: $newContactPhone,
                    onAdd: {
                        let contact = EmergencyContact(
                            name: newContactName,
                            phone: newContactPhone
                        )
                        contacts.append(contact)
                        newContactName = ""
                        newContactPhone = ""
                        showAddContact = false
                    }
                )
            }
            .alert("Error", isPresented: $showError) {
                Button("OK") {}
            } message: {
                Text(errorMessage)
            }
        }
    }

    private var canCreatePlan: Bool {
        !planTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !location.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !contacts.isEmpty
    }

    private func createPlan() {
        guard canCreatePlan else { return }

        isCreating = true

        Task {
            let plan = PlanCreate(
                title: planTitle.trimmingCharacters(in: .whitespacesAndNewlines),
                activity_type: selectedActivity,
                start_at: startTime,
                eta_at: etaTime,
                grace_minutes: Int(graceMinutes),
                location_text: location.trimmingCharacters(in: .whitespacesAndNewlines),
                notes: notes.isEmpty ? nil : notes,
                contacts: contacts.map { ContactIn(name: $0.name, phone: $0.phone, email: nil, notify_on_overdue: true) }
            )

            let createdPlan = await session.createPlan(plan)

            await MainActor.run {
                isCreating = false
                if createdPlan != nil {
                    dismiss()
                } else {
                    errorMessage = session.lastError.isEmpty ? "Failed to create plan" : session.lastError
                    showError = true
                }
            }
        }
    }
}

// MARK: - Supporting Views
struct SectionHeader: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.headline)
            .foregroundStyle(.primary)
    }
}

struct FloatingLabelTextField: View {
    let placeholder: String
    @Binding var text: String
    let icon: String

    var body: some View {
        HStack {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)

            TextField(placeholder, text: $text)
                .textFieldStyle(.plain)
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.tertiarySystemFill))
        )
    }
}

struct ActivityChip: View {
    let activity: ActivityType
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(activity.icon)
                    .font(.system(size: 18))
                Text(activity.displayName)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 20)
                    .fill(isSelected ?
                        LinearGradient(
                            colors: [activity.primaryColor, activity.secondaryColor],
                            startPoint: .leading,
                            endPoint: .trailing
                        ) :
                        LinearGradient(
                            colors: [Color(.tertiarySystemFill), Color(.tertiarySystemFill)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
            )
            .foregroundStyle(isSelected ? .white : .primary)
        }
    }
}

struct ContactRow: View {
    let contact: EmergencyContact
    let onDelete: () -> Void

    var body: some View {
        HStack {
            Image(systemName: "person.circle.fill")
                .font(.title2)
                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)

            VStack(alignment: .leading, spacing: 2) {
                Text(contact.name)
                    .font(.subheadline)
                    .fontWeight(.medium)
                Text(contact.phone)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button(action: onDelete) {
                Image(systemName: "xmark.circle.fill")
                    .font(.title3)
                    .foregroundStyle(.red)
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.quaternarySystemFill))
        )
    }
}

struct EmergencyContact: Identifiable {
    let id = UUID()
    let name: String
    let phone: String
}

struct AddContactSheet: View {
    @Binding var name: String
    @Binding var phone: String
    let onAdd: () -> Void
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Contact Name", text: $name)
                    TextField("Phone Number", text: $phone)
                        .keyboardType(.phonePad)
                }
            }
            .navigationTitle("Add Contact")
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
                    .disabled(name.isEmpty || phone.isEmpty)
                }
            }
        }
    }
}

#Preview {
    CreatePlanView()
        .environmentObject(Session())
}