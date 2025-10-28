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
                location_lat: locationCoordinates?.latitude,
                location_lng: locationCoordinates?.longitude,
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
    @Binding var locationCoordinates: CLLocationCoordinate2D?
    @Binding var showingLocationSearch: Bool
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
        }
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
    @State private var departureHour = 9
    @State private var departureMinute = 0
    @State private var departureAMPM = 0 // 0 = AM, 1 = PM
    @State private var returnHour = 5
    @State private var returnMinute = 0
    @State private var returnAMPM = 1 // 0 = AM, 1 = PM

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
                                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
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
                                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
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
                            .background(Color(hex: "#6C63FF") ?? .purple)
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
                                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)

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
                            .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                            .cornerRadius(6)
                        }
                        .padding()
                        .background(Color(.secondarySystemFill))
                        .cornerRadius(12)

                        // Departure Time
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Departure Time", systemImage: "airplane.departure")
                                .font(.headline)
                                .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)

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

                                // Minute Picker
                                Picker("Minute", selection: $departureMinute) {
                                    ForEach([0, 15, 30, 45], id: \.self) { minute in
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

                                // Minute Picker
                                Picker("Minute", selection: $returnMinute) {
                                    ForEach([0, 15, 30, 45], id: \.self) { minute in
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

        // Update start time
        var startComponents = calendar.dateComponents([.year, .month, .day], from: selectedStartDate)
        startComponents.hour = departureHour24
        startComponents.minute = departureMinute
        if let newStart = calendar.date(from: startComponents) {
            startTime = newStart
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
                    .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
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
                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                }

                Spacer()

                Text(dateFormatter.string(from: displayedMonth))
                    .font(.headline)

                Spacer()

                Button(action: {
                    displayedMonth = calendar.date(byAdding: .month, value: 1, to: displayedMonth) ?? displayedMonth
                }) {
                    Image(systemName: "chevron.right")
                        .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 12)

            // Weekday headers
            HStack {
                ForEach(["S", "M", "T", "W", "T", "F", "S"], id: \.self) { day in
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
                            .fill(Color(hex: "#6C63FF") ?? .purple)
                            .opacity(0.2)
                    } else if isStart {
                        // Start of range
                        HStack(spacing: 0) {
                            Color.clear
                                .frame(maxWidth: .infinity)
                            Rectangle()
                                .fill(Color(hex: "#6C63FF") ?? .purple)
                                .opacity(0.1)
                                .frame(maxWidth: .infinity)
                        }

                        Circle()
                            .fill(Color(hex: "#6C63FF") ?? .purple)
                            .opacity(0.2)
                    } else if isEnd {
                        // End of range
                        HStack(spacing: 0) {
                            Rectangle()
                                .fill(Color(hex: "#6C63FF") ?? .purple)
                                .opacity(0.1)
                                .frame(maxWidth: .infinity)
                            Color.clear
                                .frame(maxWidth: .infinity)
                        }

                        Circle()
                            .fill(Color(hex: "#6C63FF") ?? .purple)
                            .opacity(0.2)
                    } else {
                        // Middle of range
                        Rectangle()
                            .fill(Color(hex: "#6C63FF") ?? .purple)
                            .opacity(0.1)
                    }
                }

                // Day number
                Text(dayNumber)
                    .font(.system(size: 16, weight: (isStart || isEnd) ? .semibold : .regular))
                    .foregroundStyle(
                        isPast ? .secondary :
                        (isStart || isEnd) ? .white :
                        isInRange ? Color(hex: "#6C63FF") ?? .purple :
                        isToday ? Color(hex: "#6C63FF") ?? .purple :
                        .primary
                    )
                    .frame(width: 35, height: 35)
                    .background(
                        Group {
                            if isStart || isEnd {
                                Circle()
                                    .fill(Color(hex: "#6C63FF") ?? .purple)
                            } else if isToday && !isInRange {
                                Circle()
                                    .stroke(Color(hex: "#6C63FF") ?? .purple, lineWidth: 1)
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