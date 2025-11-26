import SwiftUI
import CoreLocation

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
    @State private var locationCoordinates: CLLocationCoordinate2D?
    @State private var showingLocationSearch = false
    @State private var startTime = Date()
    @State private var etaTime = Date().addingTimeInterval(7200) // 2 hours from now
    @State private var isManualETA = false
    @State private var graceMinutes: Double = Double(AppPreferences.shared.defaultGraceMinutes)
    @State private var showZeroGraceWarning = false
    @State private var notes = ""
    @State private var hasAppliedDefaults = false

    // Contact management
    @State private var contacts: [EmergencyContact] = []
    @State private var showAddContact = false
    @State private var newContactName = ""
    @State private var newContactEmail = ""

    // UI State
    @State private var isCreating = false
    @State private var showError = false
    @State private var errorMessage = ""

    // Contact confirmation dialog
    @State private var showSaveContactConfirmation = false
    @State private var contactsToConfirm: [EmergencyContact] = []
    @State private var contactsToSave: [EmergencyContact] = []

    // Activities from session (dynamic from database)
    var activities: [ActivityTypeAdapter] {
        session.activities.toAdapters()
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Background - tap to dismiss keyboard
                Color(.systemBackground)
                    .ignoresSafeArea()
                    .onTapGesture {
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    }

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
                            locationCoordinates: $locationCoordinates,
                            showingLocationSearch: $showingLocationSearch,
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
                            newContactEmail: $newContactEmail
                        )
                        .environmentObject(session)
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
                                // Dismiss keyboard before proceeding
                                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
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
                                .background(canProceedFromCurrentStep() ? Color.hbAccent : Color.gray)
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
            .onAppear {
                // Apply default activity from preferences (only once)
                if !hasAppliedDefaults {
                    hasAppliedDefaults = true
                    if let defaultActivityId = AppPreferences.shared.defaultActivityId,
                       let activity = session.activities.first(where: { $0.id == defaultActivityId }) {
                        selectedActivity = activity.name.lowercased().replacingOccurrences(of: " ", with: "_")
                    }
                }
            }
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
                    email: $newContactEmail,
                    onAdd: {
                        let contact = EmergencyContact(
                            name: newContactName,
                            email: newContactEmail
                        )
                        contacts.append(contact)
                        newContactName = ""
                        newContactEmail = ""
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
            .confirmationDialog(
                "Save Contacts?",
                isPresented: $showSaveContactConfirmation,
                titleVisibility: .visible
            ) {
                Button("Save to My Contacts") {
                    contactsToSave = contactsToConfirm
                    proceedWithPlanCreation()
                }
                Button("Don't Save") {
                    contactsToSave = []
                    proceedWithPlanCreation()
                }
                Button("Cancel", role: .cancel) {
                    contactsToConfirm = []
                }
            } message: {
                if contactsToConfirm.count == 1 {
                    Text("Would you like to save \(contactsToConfirm[0].name) to your saved contacts for future trips?")
                } else {
                    Text("Would you like to save these \(contactsToConfirm.count) contacts to your saved contacts for future trips?")
                }
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

        // Check if there are any new contacts that need to be saved
        let newContacts = contacts.filter { $0.savedContactId == nil }

        if !newContacts.isEmpty {
            // Show confirmation dialog for saving new contacts
            contactsToConfirm = newContacts
            showSaveContactConfirmation = true
            return
        }

        // If no new contacts or user confirmed, proceed with plan creation
        proceedWithPlanCreation()
    }

    private func proceedWithPlanCreation() {
        isCreating = true

        Task {
            // Step 1: Handle contacts - use existing IDs or create new ones if user confirmed
            var contactIds: [Int] = []
            for contact in contacts {
                if let savedId = contact.savedContactId {
                    // Use existing saved contact ID (no duplication)
                    contactIds.append(savedId)
                } else if contactsToSave.contains(where: { $0.id == contact.id }) {
                    // User confirmed to save this new contact
                    if let savedContact = await session.addContact(name: contact.name, email: contact.email) {
                        contactIds.append(savedContact.id)
                    } else {
                        await MainActor.run {
                            isCreating = false
                            errorMessage = "Failed to save contact: \(contact.name)"
                            showError = true
                        }
                        return
                    }
                } else {
                    // New contact that user chose not to save - we still need to handle this
                    // For now, we'll create it temporarily to get an ID
                    // TODO: Backend should support ephemeral contacts for trips
                    if let savedContact = await session.addContact(name: contact.name, email: contact.email) {
                        contactIds.append(savedContact.id)
                    } else {
                        await MainActor.run {
                            isCreating = false
                            errorMessage = "Failed to add contact: \(contact.name)"
                            showError = true
                        }
                        return
                    }
                }
            }

            // Step 2: Create plan with contact IDs
            let plan = TripCreateRequest(
                title: planTitle.trimmingCharacters(in: .whitespacesAndNewlines),
                activity: selectedActivity,
                start: startTime,
                eta: etaTime,
                grace_min: Int(graceMinutes),
                location_text: location.trimmingCharacters(in: .whitespacesAndNewlines),
                gen_lat: locationCoordinates?.latitude,
                gen_lon: locationCoordinates?.longitude,
                notes: notes.isEmpty ? nil : notes,
                contact1: contactIds.count > 0 ? contactIds[0] : nil,
                contact2: contactIds.count > 1 ? contactIds[1] : nil,
                contact3: contactIds.count > 2 ? contactIds[2] : nil
            )

            let createdPlan = await session.createPlan(plan)

            await MainActor.run {
                isCreating = false
                if createdPlan != nil {
                    // Notify that a trip was created so UpcomingTripsSection can refresh
                    NotificationCenter.default.post(name: .tripCreated, object: nil)
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
                    .fill(step <= currentStep ? Color.hbAccent : Color(.systemGray4))
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
    @Binding var locationCoordinates: CLLocationCoordinate2D?
    @Binding var showingLocationSearch: Bool
    let activities: [ActivityTypeAdapter]

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
                        .submitLabel(.done)
                }

                // Activity Type Selection
                VStack(alignment: .leading, spacing: 12) {
                    Label("Activity Type", systemImage: "figure.walk")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 100))], spacing: 12) {
                        ForEach(activities, id: \.id) { activity in
                            ActivityTypeButton(
                                activity: activity,
                                isSelected: selectedActivity == activity.rawValue,
                                action: { selectedActivity = activity.rawValue }
                            )
                        }
                    }
                }

                // Location Selection
                VStack(alignment: .leading, spacing: 8) {
                    Label("Location", systemImage: "location.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button(action: {
                        showingLocationSearch = true
                    }) {
                        HStack {
                            if location.isEmpty {
                                Text("Search for a place...")
                                    .foregroundStyle(.secondary)
                            } else {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(location)
                                        .foregroundStyle(.primary)
                                        .lineLimit(1)

                                    if locationCoordinates != nil {
                                        Text("Location saved")
                                            .font(.caption2)
                                            .foregroundStyle(.green)
                                    }
                                }
                            }

                            Spacer()

                            Image(systemName: location.isEmpty ? "magnifyingglass" : "checkmark.circle.fill")
                                .foregroundStyle(location.isEmpty ? Color.secondary : Color.green)
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)
                    }
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .sheet(isPresented: $showingLocationSearch) {
            LocationSearchView(
                selectedLocation: $location,
                selectedCoordinates: $locationCoordinates,
                isPresented: $showingLocationSearch
            )
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

    @State private var selectedStartDate = Date()
    @State private var selectedEndDate = Date()
    @State private var showingTimeSelection = false
    @State private var isStartingNow = true // New: toggle for starting now vs later
    @State private var departureHour = 9
    @State private var departureMinute = 0
    @State private var departureAMPM = 0 // 0 = AM, 1 = PM
    @State private var returnHour = 11  // 11:00 AM (2 hours after default 9:00 AM departure)
    @State private var returnMinute = 0
    @State private var returnAMPM = 0 // 0 = AM (changed from 1 PM to match default 2-hour trip)

    // For the date range visualization
    var dateRangeString: String {
        if Calendar.current.isDate(selectedStartDate, inSameDayAs: selectedEndDate) {
            return selectedStartDate.formatted(.dateTime.weekday(.wide).month(.wide).day())
        } else {
            let start = selectedStartDate.formatted(.dateTime.month(.abbreviated).day())
            let end = selectedEndDate.formatted(.dateTime.month(.abbreviated).day())
            return "\(start) - \(end)"
        }
    }

    var tripDurationString: String {
        let duration = selectedEndDate.timeIntervalSince(selectedStartDate)
        let days = Int(duration / 86400)

        if days == 0 {
            return "Same day trip"
        } else if days == 1 {
            return "Overnight trip"
        } else {
            return "\(days + 1) day trip"
        }
    }

    var isSelectedDateToday: Bool {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let selectedDay = calendar.startOfDay(for: selectedStartDate)
        return today == selectedDay
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text("Time Settings")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    Text(!showingTimeSelection ? "Select your trip dates" : "Set departure and return times")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 20)

                if !showingTimeSelection {
                    // PHASE 1: Date Selection
                    VStack(spacing: 20) {
                        // Instructions
                        HStack {
                            Image(systemName: "info.circle.fill")
                                .foregroundStyle(Color.hbBrand)
                            Text("Tap departure date, then tap return date")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(12)

                        // Single Calendar for Date Range
                        VStack(spacing: 0) {
                            // Custom date range display
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Departure")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(selectedStartDate.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()))
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                }

                                Image(systemName: "arrow.right")
                                    .foregroundStyle(.secondary)
                                    .padding(.horizontal)

                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Return")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(selectedEndDate.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()))
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                }

                                Spacer()
                            }
                            .padding()
                            .background(Color(.secondarySystemFill))
                            .cornerRadius(12, corners: [.topLeft, .topRight])

                            // Multi-date picker using DatePicker
                            MultiDatePicker(
                                startDate: $selectedStartDate,
                                endDate: $selectedEndDate
                            )
                            .padding()
                            .background(Color(.secondarySystemFill))
                            .cornerRadius(12, corners: [.bottomLeft, .bottomRight])
                        }

                        // Selected dates summary
                        HStack {
                            Image(systemName: "calendar.badge.checkmark")
                                .foregroundStyle(Color.hbBrand)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(dateRangeString)
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                Text(tripDurationString)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()

                            Button("Set Times") {
                                showingTimeSelection = true
                            }
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(Color.hbBrand)
                            .foregroundStyle(.white)
                            .cornerRadius(8)
                        }
                        .padding()
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(12)
                    }
                } else {
                    // PHASE 2: Time Selection
                    VStack(spacing: 20) {
                        // Date Range Summary with Edit Button
                        HStack {
                            Image(systemName: "calendar.circle.fill")
                                .font(.title2)
                                .foregroundStyle(Color.hbBrand)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(dateRangeString)
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                Text(tripDurationString)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            Button("Change Dates") {
                                showingTimeSelection = false
                            }
                            .font(.caption)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color(.tertiarySystemFill))
                            .foregroundStyle(Color.hbBrand)
                            .cornerRadius(6)
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)

                        // Departure Time
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Label("Departure Time", systemImage: "airplane.departure")
                                    .font(.headline)
                                    .foregroundStyle(Color.hbBrand)

                                Spacer()

                                // Only show "Starting Now" toggle if selected date is today
                                if isSelectedDateToday {
                                    Button(isStartingNow ? "Start Later" : "Starting Now") {
                                        isStartingNow.toggle()
                                    }
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(isStartingNow ? Color(.tertiarySystemFill) : (Color.hbBrand))
                                    .foregroundStyle(isStartingNow ? (Color.hbBrand) : .white)
                                    .cornerRadius(6)
                                }
                            }

                            if isStartingNow && isSelectedDateToday {
                                // Starting Now UI (only shown when today is selected)
                                HStack {
                                    Image(systemName: "clock.fill")
                                        .font(.title2)
                                        .foregroundStyle(Color.hbBrand)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("Starting Now")
                                            .font(.headline)
                                        Text("Trip will begin immediately when created")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                }
                                .padding()
                                .background(Color.hbBrand.opacity(0.1))
                                .cornerRadius(8)
                            } else {
                                // Show helpful message for future dates
                                if !isSelectedDateToday {
                                    HStack {
                                        Image(systemName: "info.circle")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text("Set departure time for \(selectedStartDate.formatted(date: .abbreviated, time: .omitted))")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    .padding(.bottom, 4)
                                }

                                // Custom time picker
                                HStack(spacing: 4) {
                                    // Hour Picker (12-hour format)
                                    Picker("Hour", selection: $departureHour) {
                                        ForEach(1...12, id: \.self) { hour in
                                            Text("\(hour)")
                                                .tag(hour)
                                        }
                                    }
                                    .pickerStyle(.wheel)
                                    .frame(width: 50, height: 100)
                                    .clipped()

                                    Text(":")
                                        .font(.title2)
                                        .fontWeight(.medium)

                                    // Minute Picker (every minute)
                                    Picker("Minute", selection: $departureMinute) {
                                        ForEach(0..<60, id: \.self) { minute in
                                            Text(String(format: "%02d", minute))
                                                .tag(minute)
                                        }
                                    }
                                    .pickerStyle(.wheel)
                                    .frame(width: 60, height: 100)
                                    .clipped()

                                    // AM/PM Picker
                                    Picker("AM/PM", selection: $departureAMPM) {
                                        Text("AM").tag(0)
                                        Text("PM").tag(1)
                                    }
                                    .pickerStyle(.wheel)
                                    .frame(width: 60, height: 100)
                                    .clipped()

                                    Spacer()
                                }
                                .padding(.horizontal)

                                Text("\(selectedStartDate.formatted(.dateTime.weekday(.wide).month(.wide).day())) at \(departureHour):\(String(format: "%02d", departureMinute)) \(departureAMPM == 0 ? "AM" : "PM")")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)

                        // Return Time
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Return Time", systemImage: "airplane.arrival")
                                .font(.headline)
                                .foregroundStyle(Color.orange)

                            HStack(spacing: 4) {
                                // Hour Picker (12-hour format)
                                Picker("Hour", selection: $returnHour) {
                                    ForEach(1...12, id: \.self) { hour in
                                        Text("\(hour)")
                                            .tag(hour)
                                    }
                                }
                                .pickerStyle(.wheel)
                                .frame(width: 50, height: 100)
                                .clipped()

                                Text(":")
                                    .font(.title2)
                                    .fontWeight(.medium)

                                // Minute Picker (every minute)
                                Picker("Minute", selection: $returnMinute) {
                                    ForEach(0..<60, id: \.self) { minute in
                                        Text(String(format: "%02d", minute))
                                            .tag(minute)
                                    }
                                }
                                .pickerStyle(.wheel)
                                .frame(width: 60, height: 100)
                                .clipped()

                                // AM/PM Picker
                                Picker("AM/PM", selection: $returnAMPM) {
                                    Text("AM").tag(0)
                                    Text("PM").tag(1)
                                }
                                .pickerStyle(.wheel)
                                .frame(width: 60, height: 100)
                                .clipped()

                                Spacer()
                            }
                            .padding(.horizontal)

                            Text("\(selectedEndDate.formatted(.dateTime.weekday(.wide).month(.wide).day())) at \(returnHour):\(String(format: "%02d", returnMinute)) \(returnAMPM == 0 ? "AM" : "PM")")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)

                        // Grace Period
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Grace Period", systemImage: "hourglass")
                                .font(.headline)
                                .foregroundStyle(.orange)

                            VStack(spacing: 16) {
                                HStack {
                                    Text("Alert delay after return time")
                                        .font(.subheadline)
                                    Spacer()
                                    Text("\(Int(graceMinutes)) min")
                                        .font(.subheadline)
                                        .fontWeight(.semibold)
                                        .foregroundStyle(graceMinutes == 0 ? .red : .orange)
                                }

                                // Slider from 0 to 120 minutes
                                Slider(value: $graceMinutes, in: 0...120, step: 5)
                                    .tint(graceMinutes == 0 ? .red : .orange)

                                // Quick select buttons
                                HStack(spacing: 8) {
                                    ForEach([0, 15, 30, 60], id: \.self) { minutes in
                                        Button(action: {
                                            graceMinutes = Double(minutes)
                                        }) {
                                            Text("\(minutes)m")
                                                .font(.caption)
                                                .fontWeight(graceMinutes == Double(minutes) ? .semibold : .regular)
                                                .foregroundStyle(graceMinutes == Double(minutes) ? .white : Color.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 8)
                                                .background(
                                                    graceMinutes == Double(minutes) ?
                                                        (minutes == 0 ? Color.red : Color.orange) :
                                                        Color(.tertiarySystemFill)
                                                )
                                                .cornerRadius(8)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            if graceMinutes == 0 {
                                HStack {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .foregroundStyle(.red)
                                    Text("Contacts will be notified immediately if you're late")
                                        .font(.caption)
                                        .foregroundStyle(.red)
                                }
                            } else {
                                Text("Contacts will be notified \(Int(graceMinutes)) minutes after your return time")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)
                    }
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
        }
        .onAppear {
            // Initialize with current date/time values
            selectedStartDate = startTime
            selectedEndDate = etaTime

            let calendar = Calendar.current
            let startHour24 = calendar.component(.hour, from: startTime)
            let endHour24 = calendar.component(.hour, from: etaTime)

            // Convert 24-hour to 12-hour format for departure
            if startHour24 == 0 {
                departureHour = 12
                departureAMPM = 0
            } else if startHour24 < 12 {
                departureHour = startHour24
                departureAMPM = 0
            } else if startHour24 == 12 {
                departureHour = 12
                departureAMPM = 1
            } else {
                departureHour = startHour24 - 12
                departureAMPM = 1
            }

            // Convert 24-hour to 12-hour format for return
            if endHour24 == 0 {
                returnHour = 12
                returnAMPM = 0
            } else if endHour24 < 12 {
                returnHour = endHour24
                returnAMPM = 0
            } else if endHour24 == 12 {
                returnHour = 12
                returnAMPM = 1
            } else {
                returnHour = endHour24 - 12
                returnAMPM = 1
            }

            departureMinute = calendar.component(.minute, from: startTime)
            returnMinute = calendar.component(.minute, from: etaTime)
        }
        .onChange(of: isStartingNow) { _, _ in updateDates() }
        .onChange(of: departureHour) { _, _ in updateDates() }
        .onChange(of: departureMinute) { _, _ in updateDates() }
        .onChange(of: departureAMPM) { _, _ in updateDates() }
        .onChange(of: returnHour) { _, _ in updateDates() }
        .onChange(of: returnMinute) { _, _ in updateDates() }
        .onChange(of: returnAMPM) { _, _ in updateDates() }
        .onChange(of: selectedStartDate) { _, _ in updateDates() }
        .onChange(of: selectedEndDate) { _, _ in updateDates() }
        .onChange(of: showingTimeSelection) { _, newValue in
            if newValue {
                // When transitioning to time selection, ensure dates are properly set
                updateDates()
            }
        }
    }

    private func updateDates() {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let selectedDay = calendar.startOfDay(for: selectedStartDate)
        let isSelectedDateToday = today == selectedDay

        // Update start time
        // Only use "Starting Now" if the selected date is today
        if isStartingNow && isSelectedDateToday {
            // When starting now and date is today, use current time
            startTime = Date()
        } else {
            // For future dates or when "Start Later" is selected, use the selected time
            // Convert 12-hour to 24-hour for departure
            var departureHour24: Int
            if departureHour == 12 && departureAMPM == 0 {
                // 12 AM = 0
                departureHour24 = 0
            } else if departureHour == 12 && departureAMPM == 1 {
                // 12 PM = 12
                departureHour24 = 12
            } else if departureAMPM == 0 {
                // AM hours (1-11 AM)
                departureHour24 = departureHour
            } else {
                // PM hours (1-11 PM)
                departureHour24 = departureHour + 12
            }

            var startComponents = calendar.dateComponents([.year, .month, .day], from: selectedStartDate)
            startComponents.hour = departureHour24
            startComponents.minute = departureMinute
            if let newStart = calendar.date(from: startComponents) {
                startTime = newStart
            }
        }

        // Convert 12-hour to 24-hour for return
        var returnHour24: Int
        if returnHour == 12 && returnAMPM == 0 {
            // 12 AM = 0
            returnHour24 = 0
        } else if returnHour == 12 && returnAMPM == 1 {
            // 12 PM = 12
            returnHour24 = 12
        } else if returnAMPM == 0 {
            // AM hours (1-11 AM)
            returnHour24 = returnHour
        } else {
            // PM hours (1-11 PM)
            returnHour24 = returnHour + 12
        }

        // Update end time
        var endComponents = calendar.dateComponents([.year, .month, .day], from: selectedEndDate)
        endComponents.hour = returnHour24
        endComponents.minute = returnMinute
        if let newEnd = calendar.date(from: endComponents) {
            etaTime = newEnd
        }
    }
}

// Multi-date picker component
struct MultiDatePicker: View {
    @Binding var startDate: Date
    @Binding var endDate: Date
    @State private var selectedDates: Set<DateComponents> = []

    var dateRange: ClosedRange<Date>? {
        startDate <= endDate ? startDate...endDate : nil
    }

    var body: some View {
        VStack {
            // Custom calendar with range selection
            CalendarView(
                startDate: $startDate,
                endDate: $endDate,
                selectedDates: $selectedDates
            )

            // Reset button
            if !selectedDates.isEmpty {
                Button(action: {
                    selectedDates.removeAll()
                    startDate = Date()
                    endDate = Date()
                }) {
                    HStack {
                        Image(systemName: "arrow.counterclockwise")
                        Text("Reset Dates")
                    }
                    .font(.caption)
                    .foregroundStyle(Color.hbBrand)
                }
                .padding(.top, 8)
            }
        }
    }
}

// Custom calendar view with date range highlighting
struct CalendarView: View {
    @Binding var startDate: Date
    @Binding var endDate: Date
    @Binding var selectedDates: Set<DateComponents>

    @State private var displayedMonth = Date()
    @State private var selectionState: SelectionState = .selectingStart

    enum SelectionState {
        case selectingStart
        case selectingEnd
    }

    let calendar = Calendar.current
    let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM yyyy"
        return formatter
    }()

    var monthDays: [Date?] {
        guard let monthRange = calendar.range(of: .day, in: .month, for: displayedMonth),
              let firstOfMonth = calendar.date(from: calendar.dateComponents([.year, .month], from: displayedMonth)) else {
            return []
        }

        let firstWeekday = calendar.component(.weekday, from: firstOfMonth) - 1
        let previousMonthDays = Array(repeating: nil as Date?, count: firstWeekday)

        let monthDays = monthRange.compactMap { day -> Date? in
            calendar.date(byAdding: .day, value: day - 1, to: firstOfMonth)
        }

        return previousMonthDays + monthDays
    }

    var body: some View {
        VStack(spacing: 0) {
            // Month navigation header
            HStack {
                Button(action: {
                    displayedMonth = calendar.date(byAdding: .month, value: -1, to: displayedMonth) ?? displayedMonth
                }) {
                    Image(systemName: "chevron.left")
                        .foregroundStyle(Color.hbBrand)
                }

                Spacer()

                Text(dateFormatter.string(from: displayedMonth))
                    .font(.headline)

                Spacer()

                Button(action: {
                    displayedMonth = calendar.date(byAdding: .month, value: 1, to: displayedMonth) ?? displayedMonth
                }) {
                    Image(systemName: "chevron.right")
                        .foregroundStyle(Color.hbBrand)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 12)

            // Weekday headers
            HStack {
                ForEach(Array(["S", "M", "T", "W", "T", "F", "S"].enumerated()), id: \.offset) { index, day in
                    Text(day)
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 8)

            // Calendar grid
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 8) {
                ForEach(Array(monthDays.enumerated()), id: \.offset) { index, date in
                    if let date = date {
                        DayView(
                            date: date,
                            isSelected: isDateSelected(date),
                            isInRange: isDateInRange(date),
                            isStart: calendar.isDate(date, inSameDayAs: startDate),
                            isEnd: calendar.isDate(date, inSameDayAs: endDate),
                            isToday: calendar.isDateInToday(date),
                            isPast: date < calendar.startOfDay(for: Date())
                        ) {
                            selectDate(date)
                        }
                    } else {
                        Color.clear
                            .frame(height: 35)
                    }
                }
            }
            .padding(.horizontal)
        }
    }

    private func isDateSelected(_ date: Date) -> Bool {
        calendar.isDate(date, inSameDayAs: startDate) || calendar.isDate(date, inSameDayAs: endDate)
    }

    private func isDateInRange(_ date: Date) -> Bool {
        let start = calendar.startOfDay(for: startDate)
        let end = calendar.startOfDay(for: endDate)
        let current = calendar.startOfDay(for: date)

        if start <= end {
            return current >= start && current <= end
        } else {
            return false
        }
    }

    private func selectDate(_ date: Date) {
        // Don't allow selecting dates in the past
        guard date >= calendar.startOfDay(for: Date()) else { return }

        let components = calendar.dateComponents([.year, .month, .day], from: date)

        switch selectionState {
        case .selectingStart:
            startDate = date
            endDate = date
            selectedDates.removeAll()
            selectedDates.insert(components)
            selectionState = .selectingEnd

        case .selectingEnd:
            if date < startDate {
                // If selecting earlier date, make it the new start
                endDate = startDate
                startDate = date
            } else {
                endDate = date
            }

            // Update selected dates to include range
            selectedDates.removeAll()
            var current = startDate
            while current <= endDate {
                let comp = calendar.dateComponents([.year, .month, .day], from: current)
                selectedDates.insert(comp)
                current = calendar.date(byAdding: .day, value: 1, to: current) ?? current
            }

            selectionState = .selectingStart
        }
    }
}

// Individual day view in the calendar
struct DayView: View {
    let date: Date
    let isSelected: Bool
    let isInRange: Bool
    let isStart: Bool
    let isEnd: Bool
    let isToday: Bool
    let isPast: Bool
    let action: () -> Void

    private var dayNumber: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "d"
        return formatter.string(from: date)
    }

    var body: some View {
        Button(action: action) {
            ZStack {
                // Range background
                if isInRange {
                    if isStart && isEnd {
                        // Single day selection
                        Circle()
                            .fill(Color.hbBrand)
                            .opacity(0.2)
                    } else if isStart {
                        // Start of range
                        HStack(spacing: 0) {
                            Color.clear
                                .frame(maxWidth: .infinity)
                            Rectangle()
                                .fill(Color.hbBrand)
                                .opacity(0.1)
                                .frame(maxWidth: .infinity)
                        }

                        Circle()
                            .fill(Color.hbBrand)
                            .opacity(0.2)
                    } else if isEnd {
                        // End of range
                        HStack(spacing: 0) {
                            Rectangle()
                                .fill(Color.hbBrand)
                                .opacity(0.1)
                                .frame(maxWidth: .infinity)
                            Color.clear
                                .frame(maxWidth: .infinity)
                        }

                        Circle()
                            .fill(Color.hbBrand)
                            .opacity(0.2)
                    } else {
                        // Middle of range
                        Rectangle()
                            .fill(Color.hbBrand)
                            .opacity(0.1)
                    }
                }

                // Day number
                Text(dayNumber)
                    .font(.system(size: 16, weight: (isStart || isEnd) ? .semibold : .regular))
                    .foregroundStyle(
                        isPast ? .secondary :
                        (isStart || isEnd) ? .white :
                        isInRange ? Color.hbBrand :
                        isToday ? Color.hbBrand :
                        .primary
                    )
                    .frame(width: 35, height: 35)
                    .background(
                        Group {
                            if isStart || isEnd {
                                Circle()
                                    .fill(Color.hbBrand)
                            } else if isToday && !isInRange {
                                Circle()
                                    .stroke(Color.hbBrand, lineWidth: 1)
                            }
                        }
                    )
            }
            .frame(height: 35)
        }
        .disabled(isPast)
    }
}

// Helper for rounded corners
extension View {
    func cornerRadius(_ radius: CGFloat, corners: UIRectCorner) -> some View {
        clipShape(RoundedCorner(radius: radius, corners: corners))
    }
}

struct RoundedCorner: Shape {
    var radius: CGFloat = .infinity
    var corners: UIRectCorner = .allCorners

    func path(in rect: CGRect) -> Path {
        let path = UIBezierPath(roundedRect: rect, byRoundingCorners: corners, cornerRadii: CGSize(width: radius, height: radius))
        return Path(path.cgPath)
    }
}

// MARK: - Step 3: Emergency Contacts
struct Step3EmergencyContacts: View {
    @EnvironmentObject var session: Session
    @Binding var contacts: [EmergencyContact]
    @Binding var showAddContact: Bool
    @Binding var newContactName: String
    @Binding var newContactEmail: String

    @State private var savedContacts: [Contact] = []
    @State private var isLoadingSaved = false
    @State private var showingContacts = false

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

                // Action Buttons
                HStack(spacing: 12) {
                    // Select from Saved Contacts
                    Button(action: {
                        Task {
                            isLoadingSaved = true
                            await loadContacts()
                            showingContacts = true
                        }
                    }) {
                        HStack {
                            if isLoadingSaved {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "person.crop.circle.badge.checkmark")
                                    .font(.title3)
                            }
                            Text("Choose Saved")
                                .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .foregroundStyle(Color.hbBrand)
                        .cornerRadius(12)
                    }
                    .disabled(isLoadingSaved)

                    // Add New Contact
                    Button(action: { showAddContact = true }) {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                                .font(.title3)
                            Text("Add New")
                                .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.hbAccent)
                        .foregroundStyle(.white)
                        .cornerRadius(12)
                    }
                }

                if contacts.isEmpty {
                    // Empty State
                    VStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.badge.exclamationmark")
                            .font(.system(size: 48))
                            .foregroundStyle(.orange)

                        Text("No contacts selected")
                            .font(.headline)

                        Text("Choose from your saved contacts or add new ones. At least one emergency contact is required.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                } else {
                    // Selected Contacts
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Selected Contacts (\(contacts.count)/3)")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        ForEach(contacts) { contact in
                            ContactCard(contact: contact) {
                                contacts.removeAll { $0.id == contact.id }
                            }
                        }
                    }

                    if contacts.count >= 3 {
                        HStack {
                            Image(systemName: "info.circle.fill")
                                .foregroundStyle(Color.orange)
                            Text("Maximum of 3 contacts reached")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding()
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(8)
                    }
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .task {
            await loadContacts()
        }
        .sheet(isPresented: $showingContacts) {
            ContactsSelectionSheet(
                savedContacts: savedContacts,
                selectedContacts: $contacts,
                isPresented: $showingContacts
            )
        }
    }

    private func loadContacts() async {
        let loaded = await session.loadContacts()
        await MainActor.run {
            self.savedContacts = loaded
            self.isLoadingSaved = false
            print("DEBUG: Loaded \(loaded.count) saved contacts")
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
                        .foregroundStyle(Color.hbAccent)

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
                    .background(Color.hbAccent)
                    .foregroundStyle(.white)
                    .cornerRadius(16)
                }
                .disabled(isCreating)

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            }
        }
        .scrollDismissesKeyboard(.interactively)
    }
}

// MARK: - Supporting Views
struct ActivityTypeButton: View {
    let activity: ActivityTypeAdapter
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
                .fill(Color.hbAccent)
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
                Text(contact.email)
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
    let email: String
    let savedContactId: Int?  // If nil, this is a new contact; if set, it's from saved contacts

    init(name: String, email: String, savedContactId: Int? = nil) {
        self.name = name
        self.email = email
        self.savedContactId = savedContactId
    }
}

struct AddContactSheet: View {
    @Binding var name: String
    @Binding var email: String
    let onAdd: () -> Void
    @Environment(\.dismiss) var dismiss

    var isValidEmail: Bool {
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        email.contains("@")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Contact Name", text: $name)
                    TextField("Email Address", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
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
                    .disabled(name.isEmpty || !isValidEmail)
                }
            }
        }
    }
}

// MARK: - Saved Contacts Selection Sheet
struct ContactsSelectionSheet: View {
    let savedContacts: [Contact]
    @Binding var selectedContacts: [EmergencyContact]
    @Binding var isPresented: Bool
    @State private var tempSelection: Set<Int> = []

    var body: some View {
        NavigationStack {
            VStack {
                if savedContacts.isEmpty {
                    // Empty state
                    VStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.badge.questionmark")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary)

                        Text("No Saved Contacts")
                            .font(.headline)

                        Text("You haven't saved any emergency contacts yet. Add contacts in Settings to quickly select them here.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                    .frame(maxHeight: .infinity)
                } else {
                    List {
                        ForEach(savedContacts) { contact in
                            ContactSelectionRow(
                                contact: contact,
                                isSelected: tempSelection.contains(contact.id),
                                canSelect: tempSelection.count < 3 || tempSelection.contains(contact.id)
                            ) { selected in
                                if selected {
                                    tempSelection.insert(contact.id)
                                } else {
                                    tempSelection.remove(contact.id)
                                }
                            }
                        }

                        if tempSelection.count >= 3 {
                            Section {
                                HStack {
                                    Image(systemName: "info.circle.fill")
                                        .foregroundStyle(Color.orange)
                                    Text("Maximum of 3 contacts can be selected")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .listRowBackground(Color(.tertiarySystemFill))
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Choose Contacts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        isPresented = false
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Add Selected") {
                        // Convert saved contacts to emergency contacts
                        let newContacts = savedContacts
                            .filter { tempSelection.contains($0.id) }
                            .compactMap { saved -> EmergencyContact? in
                                // Only include contacts with an email
                                guard let email = saved.email, !email.isEmpty else {
                                    return nil
                                }
                                // Don't add duplicates
                                guard !selectedContacts.contains(where: { $0.email == email }) else {
                                    return nil
                                }
                                return EmergencyContact(
                                    name: saved.name,
                                    email: email,
                                    savedContactId: saved.id  // Pass the saved contact ID to prevent duplication
                                )
                            }

                        // Add to selected contacts (up to 3 total)
                        for contact in newContacts {
                            if selectedContacts.count < 3 {
                                selectedContacts.append(contact)
                            }
                        }

                        isPresented = false
                    }
                    .fontWeight(.semibold)
                    .disabled(tempSelection.isEmpty)
                }
            }
        }
        .onAppear {
            // Pre-select contacts that are already selected
            tempSelection = Set(
                selectedContacts.compactMap { selected in
                    savedContacts.first(where: { $0.email == selected.email })?.id
                }
            )
        }
    }
}

struct ContactSelectionRow: View {
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
            HStack {
                // Contact Icon
                Circle()
                    .fill(Color.hbAccent)
                    .frame(width: 40, height: 40)
                    .overlay(
                        Text(contact.name.prefix(1).uppercased())
                            .font(.headline)
                            .foregroundStyle(.white)
                    )

                VStack(alignment: .leading, spacing: 2) {
                    Text(contact.name)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)

                    if let email = contact.email, !email.isEmpty {
                        Text(email)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(isSelected ? (Color.hbBrand) : Color(.tertiaryLabel))
                    .opacity(canSelect ? 1.0 : 0.5)
            }
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
        .disabled(!canSelect && !isSelected)
    }
}

#Preview {
    CreatePlanView()
        .environmentObject(Session())
}