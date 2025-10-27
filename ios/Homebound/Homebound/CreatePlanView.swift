import SwiftUI

struct CreatePlanView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    // Current step tracking
    @State private var currentStep = 1
    let totalSteps = 4

    // Form fields
    @State private var planTitle = ""
    @State private var selectedActivity = "other"
    @State private var location = ""
    @State private var startTime = Date()
    @State private var etaTime = Date().addingTimeInterval(7200) // 2 hours from now
    @State private var isManualETA = false
    @State private var graceMinutes: Double = 30
    @State private var showZeroGraceWarning = false
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

    var body: some View {
        NavigationStack {
            ZStack {
                // Background
                Color(.systemBackground)
                    .ignoresSafeArea()

                VStack(spacing: 0) {
                    // Progress Bar
                    ProgressIndicator(currentStep: currentStep, totalSteps: totalSteps)
                        .padding(.horizontal)
                        .padding(.top, 20)

                    // Content
                    TabView(selection: $currentStep) {
                        Step1TripDetails(
                            planTitle: $planTitle,
                            selectedActivity: $selectedActivity,
                            location: $location,
                            activities: activities
                        )
                        .tag(1)

                        Step2TimeSettings(
                            startTime: $startTime,
                            etaTime: $etaTime,
                            isManualETA: $isManualETA,
                            graceMinutes: $graceMinutes,
                            showZeroGraceWarning: $showZeroGraceWarning
                        )
                        .tag(2)

                        Step3EmergencyContacts(
                            contacts: $contacts,
                            showAddContact: $showAddContact,
                            newContactName: $newContactName,
                            newContactPhone: $newContactPhone
                        )
                        .tag(3)

                        Step4AdditionalNotes(
                            notes: $notes,
                            isCreating: $isCreating,
                            onSubmit: createPlan
                        )
                        .tag(4)
                    }
                    .tabViewStyle(.page(indexDisplayMode: .never))
                    .animation(.easeInOut, value: currentStep)

                    // Navigation Buttons
                    HStack(spacing: 16) {
                        if currentStep > 1 {
                            Button(action: { currentStep -= 1 }) {
                                HStack {
                                    Image(systemName: "chevron.left")
                                    Text("Back")
                                }
                                .frame(maxWidth: .infinity)
                                .frame(height: 50)
                                .background(Color(.tertiarySystemFill))
                                .foregroundStyle(.primary)
                                .cornerRadius(12)
                            }
                        }

                        if currentStep < totalSteps {
                            Button(action: {
                                if validateCurrentStep() {
                                    currentStep += 1
                                }
                            }) {
                                HStack {
                                    Text("Next")
                                    Image(systemName: "chevron.right")
                                }
                                .frame(maxWidth: .infinity)
                                .frame(height: 50)
                                .background(
                                    LinearGradient(
                                        colors: canProceedFromCurrentStep() ?
                                            [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal] :
                                            [Color.gray, Color.gray.opacity(0.8)],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                                .foregroundStyle(.white)
                                .cornerRadius(12)
                            }
                            .disabled(!canProceedFromCurrentStep())
                        }
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 30)
                }
            }
            .navigationTitle("New Adventure")
            .navigationBarTitleDisplayMode(.inline)
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
            .alert("Zero Grace Period Warning", isPresented: $showZeroGraceWarning) {
                Button("I Understand", role: .destructive) {
                    showZeroGraceWarning = false
                }
                Button("Set to 15 minutes", role: .cancel) {
                    graceMinutes = 15
                    showZeroGraceWarning = false
                }
            } message: {
                Text("Setting a zero grace period means your emergency contacts will be notified immediately if you don't check out on time. Are you sure?")
            }
        }
    }

    private func canProceedFromCurrentStep() -> Bool {
        switch currentStep {
        case 1:
            return !planTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
                   !location.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case 2:
            return etaTime > startTime
        case 3:
            return !contacts.isEmpty
        case 4:
            return true
        default:
            return false
        }
    }

    private func validateCurrentStep() -> Bool {
        switch currentStep {
        case 2:
            if graceMinutes == 0 && !showZeroGraceWarning {
                showZeroGraceWarning = true
                return false
            }
            return true
        default:
            return true
        }
    }

    private func createPlan() {
        guard canProceedFromCurrentStep() else { return }

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

// MARK: - Progress Indicator
struct ProgressIndicator: View {
    let currentStep: Int
    let totalSteps: Int

    var body: some View {
        HStack(spacing: 8) {
            ForEach(1...totalSteps, id: \.self) { step in
                Circle()
                    .fill(step <= currentStep ?
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        ) :
                        LinearGradient(
                            colors: [Color(.systemGray4), Color(.systemGray4)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: 8, height: 8)
                    .animation(.easeInOut, value: currentStep)
            }
        }
        .padding(.vertical, 8)
    }
}

// MARK: - Step 1: Trip Details
struct Step1TripDetails: View {
    @Binding var planTitle: String
    @Binding var selectedActivity: String
    @Binding var location: String
    let activities: [ActivityType]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Trip Details")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    Text("Let's start with the basics")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                // Title Input
                VStack(alignment: .leading, spacing: 8) {
                    Label("Adventure Name", systemImage: "pencil")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextField("e.g., Morning hike at Bear Mountain", text: $planTitle)
                        .textFieldStyle(.plain)
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)
                }

                // Activity Type Selection
                VStack(alignment: .leading, spacing: 12) {
                    Label("Activity Type", systemImage: "figure.walk")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                        ForEach(activities, id: \.self) { activity in
                            ActivityTypeButton(
                                activity: activity,
                                isSelected: selectedActivity == activity.rawValue,
                                action: { selectedActivity = activity.rawValue }
                            )
                        }
                    }
                }

                // Location Input
                VStack(alignment: .leading, spacing: 8) {
                    Label("Location", systemImage: "location.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextField("e.g., Yosemite National Park", text: $location)
                        .textFieldStyle(.plain)
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
        }
    }
}

// MARK: - Step 2: Time Settings
struct Step2TimeSettings: View {
    @Binding var startTime: Date
    @Binding var etaTime: Date
    @Binding var isManualETA: Bool
    @Binding var graceMinutes: Double
    @Binding var showZeroGraceWarning: Bool

    @State private var duration: Double = 2

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Time Settings")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    Text("When are you leaving and returning?")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                // Start Time
                VStack(alignment: .leading, spacing: 12) {
                    Label("Departure Time", systemImage: "calendar.badge.clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    DatePicker(
                        "",
                        selection: $startTime,
                        in: Date()...,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                    .datePickerStyle(.graphical)
                    .padding()
                    .background(Color(.secondarySystemFill))
                    .cornerRadius(12)
                }

                // Expected Return
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label("Expected Return", systemImage: "house.arrival")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Spacer()

                        Toggle("Manual", isOn: $isManualETA)
                            .toggleStyle(.button)
                            .tint(Color(hex: "#6C63FF") ?? .purple)
                            .font(.caption)
                    }

                    if isManualETA {
                        DatePicker(
                            "",
                            selection: $etaTime,
                            in: startTime...,
                            displayedComponents: [.date, .hourAndMinute]
                        )
                        .datePickerStyle(.graphical)
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)
                    } else {
                        VStack(spacing: 12) {
                            HStack {
                                Text("Duration")
                                    .font(.subheadline)
                                Spacer()
                                Text("\(Int(duration)) hours")
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                            }

                            Slider(value: $duration, in: 0.5...24, step: 0.5)
                                .tint(Color(hex: "#6C63FF") ?? .purple)
                                .onChange(of: duration) { newValue in
                                    etaTime = startTime.addingTimeInterval(newValue * 3600)
                                }
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)
                    }

                    // ETA Display
                    HStack {
                        Image(systemName: "clock.arrow.circlepath")
                            .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Return Time")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(etaTime, format: .dateTime.weekday().month().day().hour().minute())
                                .font(.subheadline)
                                .fontWeight(.medium)
                        }
                        Spacer()
                    }
                    .padding()
                    .background(Color(.tertiarySystemFill))
                    .cornerRadius(12)
                }

                // Grace Period
                VStack(alignment: .leading, spacing: 12) {
                    Label("Grace Period", systemImage: "hourglass")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    VStack(spacing: 12) {
                        HStack {
                            Text("Alert delay after ETA")
                                .font(.subheadline)
                            Spacer()
                            Text("\(Int(graceMinutes)) minutes")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(graceMinutes == 0 ? .red : .orange)
                        }

                        Slider(value: $graceMinutes, in: 0...120, step: 15)
                            .tint(graceMinutes == 0 ? .red : .orange)
                    }
                    .padding()
                    .background(Color(.secondarySystemFill))
                    .cornerRadius(12)

                    Text("Contacts will be notified \(Int(graceMinutes)) minutes after your ETA if you haven't checked in")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
        }
        .onAppear {
            duration = etaTime.timeIntervalSince(startTime) / 3600
        }
    }
}

// MARK: - Step 3: Emergency Contacts
struct Step3EmergencyContacts: View {
    @Binding var contacts: [EmergencyContact]
    @Binding var showAddContact: Bool
    @Binding var newContactName: String
    @Binding var newContactPhone: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Emergency Contacts")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    Text("Who should we notify if needed?")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                // Add Contact Button
                Button(action: { showAddContact = true }) {
                    HStack {
                        Image(systemName: "plus.circle.fill")
                            .font(.title2)
                        Text("Add Emergency Contact")
                            .fontWeight(.medium)
                        Spacer()
                    }
                    .padding()
                    .background(
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .foregroundStyle(.white)
                    .cornerRadius(12)
                }

                if contacts.isEmpty {
                    // Empty State
                    VStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.badge.exclamationmark")
                            .font(.system(size: 48))
                            .foregroundStyle(.orange)

                        Text("No contacts added")
                            .font(.headline)

                        Text("Add at least one emergency contact who will be notified if you don't check in on time")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                } else {
                    // Contact List
                    VStack(spacing: 12) {
                        ForEach(contacts) { contact in
                            ContactCard(contact: contact) {
                                contacts.removeAll { $0.id == contact.id }
                            }
                        }
                    }
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
        }
    }
}

// MARK: - Step 4: Additional Notes
struct Step4AdditionalNotes: View {
    @Binding var notes: String
    @Binding var isCreating: Bool
    let onSubmit: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Additional Notes")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    Text("Any extra details? (Optional)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                // Notes Input
                VStack(alignment: .leading, spacing: 8) {
                    Label("Notes", systemImage: "note.text")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextEditor(text: $notes)
                        .frame(minHeight: 150)
                        .padding(8)
                        .scrollContentBackground(.hidden)
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)

                    Text("Add any additional information that might be helpful")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                // Ready to Go Section
                VStack(spacing: 16) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 48))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )

                    Text("Ready to start your adventure?")
                        .font(.headline)

                    Text("We'll keep track of your journey and notify your contacts if needed")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 30)

                // Start Adventure Button
                Button(action: onSubmit) {
                    HStack {
                        if isCreating {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                .scaleEffect(0.9)
                        } else {
                            Image(systemName: "flag.checkered")
                            Text("Start Adventure")
                                .fontWeight(.semibold)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .foregroundStyle(.white)
                    .cornerRadius(16)
                }
                .disabled(isCreating)

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
        }
    }
}

// MARK: - Supporting Views
struct ActivityTypeButton: View {
    let activity: ActivityType
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Text(activity.icon)
                    .font(.title2)
                Text(activity.displayName)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isSelected ?
                        activity.primaryColor.opacity(0.15) :
                        Color(.secondarySystemFill)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(isSelected ? activity.primaryColor : Color.clear, lineWidth: 2)
                    )
            )
            .foregroundStyle(isSelected ? activity.primaryColor : .primary)
        }
    }
}

struct ContactCard: View {
    let contact: EmergencyContact
    let onDelete: () -> Void

    var body: some View {
        HStack {
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
            }

            Spacer()

            Button(action: onDelete) {
                Image(systemName: "trash")
                    .font(.callout)
                    .foregroundStyle(.red)
            }
        }
        .padding()
        .background(Color(.secondarySystemFill))
        .cornerRadius(12)
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