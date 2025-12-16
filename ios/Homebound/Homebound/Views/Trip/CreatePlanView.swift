import SwiftUI
import CoreLocation

struct CreatePlanView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    // Edit mode support
    var existingTrip: Trip? = nil
    var isEditMode: Bool { existingTrip != nil }

    // Current step tracking
    @State private var currentStep = 1
    let totalSteps = 4

    // Form fields
    @State private var planTitle = ""
    @State private var selectedActivity = "other"
    @State private var location = ""
    @State private var locationCoordinates: CLLocationCoordinate2D?
    @State private var showingLocationSearch = false
    // Start location fields (for separate start/destination mode)
    @State private var useSeparateLocations = false
    @State private var startLocation = ""
    @State private var startLocationCoordinates: CLLocationCoordinate2D?
    @State private var showingStartLocationSearch = false
    @State private var startTime = Date()
    @State private var etaTime = Date().addingTimeInterval(7200) // 2 hours from now
    @State private var isManualETA = false
    @State private var graceMinutes: Double = Double(AppPreferences.shared.defaultGraceMinutes)
    @State private var showZeroGraceWarning = false
    @State private var notes = ""
    @State private var hasAppliedDefaults = false

    // Notification settings
    @State private var checkinIntervalMinutes: Int = 30
    @State private var useNotificationHours: Bool = false
    @State private var notifyStartHour: Int = 8   // 8:00 AM default
    @State private var notifyEndHour: Int = 22    // 10:00 PM default
    @State private var showCustomInterval: Bool = false

    // Timezone settings
    @State private var showTimezoneOptions: Bool = false
    @State private var startTimezone: TimeZone = .current
    @State private var etaTimezone: TimeZone = .current

    // Contact management
    @State private var contacts: [EmergencyContact] = []
    @State private var showAddContact = false
    @State private var newContactName = ""
    @State private var newContactEmail = ""

    // UI State
    @State private var isCreating = false
    @State private var showError = false
    @State private var errorMessage = ""

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

                    // Content - using Group with switch to prevent swipe navigation
                    Group {
                        switch currentStep {
                        case 1:
                            Step1TripDetails(
                                planTitle: $planTitle,
                                selectedActivity: $selectedActivity,
                                location: $location,
                                locationCoordinates: $locationCoordinates,
                                showingLocationSearch: $showingLocationSearch,
                                useSeparateLocations: $useSeparateLocations,
                                startLocation: $startLocation,
                                startLocationCoordinates: $startLocationCoordinates,
                                showingStartLocationSearch: $showingStartLocationSearch,
                                activities: activities
                            )
                        case 2:
                            Step2TimeSettings(
                                startTime: $startTime,
                                etaTime: $etaTime,
                                isManualETA: $isManualETA,
                                graceMinutes: $graceMinutes,
                                showZeroGraceWarning: $showZeroGraceWarning,
                                isEditMode: isEditMode,
                                checkinIntervalMinutes: $checkinIntervalMinutes,
                                useNotificationHours: $useNotificationHours,
                                notifyStartHour: $notifyStartHour,
                                notifyEndHour: $notifyEndHour,
                                showCustomInterval: $showCustomInterval,
                                showTimezoneOptions: $showTimezoneOptions,
                                startTimezone: $startTimezone,
                                etaTimezone: $etaTimezone
                            )
                        case 3:
                            Step3EmergencyContacts(
                                contacts: $contacts,
                                showAddContact: $showAddContact,
                                newContactName: $newContactName,
                                newContactEmail: $newContactEmail
                            )
                            .environmentObject(session)
                        case 4:
                            Step4AdditionalNotes(
                                notes: $notes,
                                isCreating: $isCreating,
                                isEditMode: isEditMode,
                                onSubmit: createPlan
                            )
                        default:
                            EmptyView()
                        }
                    }
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
            .navigationTitle(isEditMode ? "Edit Trip" : "New Adventure")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                // Apply default activity from preferences (only once)
                if !hasAppliedDefaults {
                    hasAppliedDefaults = true

                    if let trip = existingTrip {
                        // Pre-populate fields from existing trip for edit mode
                        planTitle = trip.title
                        selectedActivity = trip.activity.name.lowercased().replacingOccurrences(of: " ", with: "_")
                        location = trip.location_text ?? ""
                        if let lat = trip.location_lat, let lng = trip.location_lng, lat != 0 || lng != 0 {
                            locationCoordinates = CLLocationCoordinate2D(latitude: lat, longitude: lng)
                        }
                        // Pre-populate start location fields
                        useSeparateLocations = trip.has_separate_locations
                        if trip.has_separate_locations {
                            startLocation = trip.start_location_text ?? ""
                            if let lat = trip.start_lat, let lng = trip.start_lng, lat != 0 || lng != 0 {
                                startLocationCoordinates = CLLocationCoordinate2D(latitude: lat, longitude: lng)
                            }
                        }
                        startTime = trip.start_at
                        etaTime = trip.eta_at
                        isManualETA = true  // Treat existing ETA as manually set
                        graceMinutes = Double(trip.grace_minutes)
                        notes = trip.notes ?? ""

                        // Pre-populate notification settings
                        checkinIntervalMinutes = trip.checkin_interval_min ?? 30
                        if let startHour = trip.notify_start_hour, let endHour = trip.notify_end_hour {
                            useNotificationHours = true
                            notifyStartHour = startHour
                            notifyEndHour = endHour
                        }

                        // Pre-populate timezone settings
                        if let startTz = trip.start_timezone, let tz = TimeZone(identifier: startTz) {
                            showTimezoneOptions = true
                            startTimezone = tz
                        }
                        if let etaTz = trip.eta_timezone, let tz = TimeZone(identifier: etaTz) {
                            showTimezoneOptions = true
                            etaTimezone = tz
                        }

                        // Pre-populate contacts from existing trip
                        let contactIds = [trip.contact1, trip.contact2, trip.contact3].compactMap { $0 }
                        for contactId in contactIds {
                            if let savedContact = session.contacts.first(where: { $0.id == contactId }) {
                                contacts.append(EmergencyContact(
                                    name: savedContact.name,
                                    email: savedContact.email,
                                    savedContactId: savedContact.id
                                ))
                            }
                        }
                    } else if let defaultActivityId = AppPreferences.shared.defaultActivityId,
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
                    // Advance to next step after user confirms
                    currentStep += 1
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
            let hasTitle = !planTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            let hasDestination = !location.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            if useSeparateLocations {
                let hasStart = !startLocation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                return hasTitle && hasDestination && hasStart
            }
            return hasTitle && hasDestination
        case 2:
            // Return time must be after start time AND in the future
            let now = Date()
            return etaTime > startTime && etaTime > now
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
        proceedWithPlanCreation()
    }

    private func proceedWithPlanCreation() {
        isCreating = true

        Task {
            // Step 1: Handle contacts - use existing IDs or create new ones
            // Note: All contacts must be saved to create a trip (backend requires contact IDs)
            var contactIds: [Int] = []
            for contact in contacts {
                if let savedId = contact.savedContactId {
                    // Use existing saved contact ID (no duplication)
                    contactIds.append(savedId)
                } else {
                    // New contact - save it to get an ID for the trip
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

            // Get user's timezone identifier (e.g., "America/New_York")
            let userTimezone = TimeZone.current.identifier

            if isEditMode, let tripId = existingTrip?.id {
                // Update existing trip
                let updates = TripUpdateRequest(
                    title: planTitle.trimmingCharacters(in: .whitespacesAndNewlines),
                    activity: selectedActivity,
                    start: startTime,
                    eta: etaTime,
                    grace_min: Int(graceMinutes),
                    location_text: location.trimmingCharacters(in: .whitespacesAndNewlines),
                    gen_lat: locationCoordinates?.latitude,
                    gen_lon: locationCoordinates?.longitude,
                    start_location_text: useSeparateLocations ? startLocation.trimmingCharacters(in: .whitespacesAndNewlines) : nil,
                    start_lat: useSeparateLocations ? startLocationCoordinates?.latitude : nil,
                    start_lon: useSeparateLocations ? startLocationCoordinates?.longitude : nil,
                    has_separate_locations: useSeparateLocations,
                    notes: notes.isEmpty ? nil : notes,
                    contact1: contactIds.count > 0 ? contactIds[0] : nil,
                    contact2: contactIds.count > 1 ? contactIds[1] : nil,
                    contact3: contactIds.count > 2 ? contactIds[2] : nil,
                    timezone: userTimezone,
                    start_timezone: showTimezoneOptions ? startTimezone.identifier : nil,
                    eta_timezone: showTimezoneOptions ? etaTimezone.identifier : nil,
                    checkin_interval_min: checkinIntervalMinutes,
                    notify_start_hour: useNotificationHours ? notifyStartHour : nil,
                    notify_end_hour: useNotificationHours ? notifyEndHour : nil
                )

                let updatedTrip = await session.updateTrip(tripId, updates: updates)

                await MainActor.run {
                    isCreating = false
                    if updatedTrip != nil {
                        // Notify that a trip was updated so lists can refresh
                        NotificationCenter.default.post(name: .tripCreated, object: nil)
                        dismiss()
                    } else {
                        errorMessage = session.lastError.isEmpty ? "Failed to update trip" : session.lastError
                        showError = true
                    }
                }
            } else {
                // Create new plan
                let plan = TripCreateRequest(
                    title: planTitle.trimmingCharacters(in: .whitespacesAndNewlines),
                    activity: selectedActivity,
                    start: startTime,
                    eta: etaTime,
                    grace_min: Int(graceMinutes),
                    location_text: location.trimmingCharacters(in: .whitespacesAndNewlines),
                    gen_lat: locationCoordinates?.latitude,
                    gen_lon: locationCoordinates?.longitude,
                    start_location_text: useSeparateLocations ? startLocation.trimmingCharacters(in: .whitespacesAndNewlines) : nil,
                    start_lat: useSeparateLocations ? startLocationCoordinates?.latitude : nil,
                    start_lon: useSeparateLocations ? startLocationCoordinates?.longitude : nil,
                    has_separate_locations: useSeparateLocations,
                    notes: notes.isEmpty ? nil : notes,
                    contact1: contactIds.count > 0 ? contactIds[0] : nil,
                    contact2: contactIds.count > 1 ? contactIds[1] : nil,
                    contact3: contactIds.count > 2 ? contactIds[2] : nil,
                    timezone: userTimezone,
                    start_timezone: showTimezoneOptions ? startTimezone.identifier : nil,
                    eta_timezone: showTimezoneOptions ? etaTimezone.identifier : nil,
                    checkin_interval_min: checkinIntervalMinutes,
                    notify_start_hour: useNotificationHours ? notifyStartHour : nil,
                    notify_end_hour: useNotificationHours ? notifyEndHour : nil
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
    // Start location bindings for separate start/destination mode
    @Binding var useSeparateLocations: Bool
    @Binding var startLocation: String
    @Binding var startLocationCoordinates: CLLocationCoordinate2D?
    @Binding var showingStartLocationSearch: Bool
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

                // Location Mode Toggle
                VStack(alignment: .leading, spacing: 8) {
                    Toggle(isOn: $useSeparateLocations) {
                        HStack {
                            Image(systemName: useSeparateLocations ? "arrow.triangle.swap" : "mappin.circle")
                                .foregroundStyle(useSeparateLocations ? Color.hbAccent : .secondary)
                            Text(useSeparateLocations ? "Start + Destination" : "Single Location")
                                .font(.subheadline)
                        }
                    }
                    .tint(.hbAccent)
                    .padding()
                    .background(Color(.secondarySystemFill))
                    .cornerRadius(12)
                }

                // Location Selection(s)
                if useSeparateLocations {
                    // Start Location
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Start Location", systemImage: "figure.walk.departure")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Button(action: {
                            showingStartLocationSearch = true
                        }) {
                            HStack {
                                if startLocation.isEmpty {
                                    Text("Where are you starting from?")
                                        .foregroundStyle(.secondary)
                                } else {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(startLocation)
                                            .foregroundStyle(.primary)
                                            .lineLimit(1)

                                        if startLocationCoordinates != nil {
                                            Text("Location saved")
                                                .font(.caption2)
                                                .foregroundStyle(.green)
                                        }
                                    }
                                }

                                Spacer()

                                Image(systemName: startLocation.isEmpty ? "magnifyingglass" : "checkmark.circle.fill")
                                    .foregroundStyle(startLocation.isEmpty ? Color.secondary : Color.green)
                            }
                            .padding()
                            .background(Color(.secondarySystemFill))
                            .cornerRadius(12)
                        }
                    }

                    // Destination Location
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Destination", systemImage: "flag.fill")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Button(action: {
                            showingLocationSearch = true
                        }) {
                            HStack {
                                if location.isEmpty {
                                    Text("Where are you going?")
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
                } else {
                    // Single Location Selection
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
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
            .onTapGesture {
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .scrollIndicators(.hidden)
        .sheet(isPresented: $showingLocationSearch) {
            LocationSearchView(
                selectedLocation: $location,
                selectedCoordinates: $locationCoordinates,
                isPresented: $showingLocationSearch
            )
        }
        .sheet(isPresented: $showingStartLocationSearch) {
            LocationSearchView(
                selectedLocation: $startLocation,
                selectedCoordinates: $startLocationCoordinates,
                isPresented: $showingStartLocationSearch
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
    var isEditMode: Bool = false

    // Notification settings bindings
    @Binding var checkinIntervalMinutes: Int
    @Binding var useNotificationHours: Bool
    @Binding var notifyStartHour: Int
    @Binding var notifyEndHour: Int
    @Binding var showCustomInterval: Bool

    // Timezone settings bindings
    @Binding var showTimezoneOptions: Bool
    @Binding var startTimezone: TimeZone
    @Binding var etaTimezone: TimeZone

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
    @State private var showCalendarHelp = false

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

    var isReturnTimeValid: Bool {
        // Return time must be after start time AND in the future
        let now = Date()
        return etaTime > startTime && etaTime > now
    }

    private var returnTimeString: String {
        "\(returnHour):\(String(format: "%02d", returnMinute)) \(returnAMPM == 0 ? "AM" : "PM")"
    }

    private var departureTimeString: String {
        "\(departureHour):\(String(format: "%02d", departureMinute)) \(departureAMPM == 0 ? "AM" : "PM")"
    }

    // MARK: - Header Section
    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Time Settings")
                    .font(.largeTitle)
                    .fontWeight(.bold)

                Button(action: { showCalendarHelp = true }) {
                    Image(systemName: "questionmark.circle.fill")
                        .font(.title3)
                        .foregroundStyle(Color.hbBrand.opacity(0.7))
                }
            }
            Text(!showingTimeSelection ? "Select your trip dates" : "Set departure and return/arrival times")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.top, 20)
    }

    // MARK: - Date Range Display
    @ViewBuilder
    private var dateRangeDisplay: some View {
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
    }

    // MARK: - Date Selection Phase
    @ViewBuilder
    private var dateSelectionPhase: some View {
        VStack(spacing: 20) {
            VStack(spacing: 0) {
                dateRangeDisplay

                MultiDatePicker(
                    startDate: $selectedStartDate,
                    endDate: $selectedEndDate
                )
                .padding()
                .background(Color(.secondarySystemFill))
                .cornerRadius(12, corners: [.bottomLeft, .bottomRight])
            }

            datesSummarySection
        }
    }

    // MARK: - Dates Summary Section
    @ViewBuilder
    private var datesSummarySection: some View {
        VStack {
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

            // ---------------------------------------------------------
            HStack(alignment: .top, spacing: 8) {
                Text("Starting: Now")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Ending at: \(returnTimeString)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Grace period: \(Int(graceMinutes)) min")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .background(Color(.tertiarySystemFill))
            .cornerRadius(12)
        }
    }

    // MARK: - Date Range Summary Header
    @ViewBuilder
    private var dateRangeSummaryHeader: some View {
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
    }

    // MARK: - Time Picker Component
    @ViewBuilder
    private func timePicker(hourBinding: Binding<Int>, minuteBinding: Binding<Int>, ampmBinding: Binding<Int>) -> some View {
        HStack(spacing: 4) {
            // Looping hour picker (1-12)
            LoopingHourPicker(selection: hourBinding)
                .frame(width: 50, height: 100)
                .clipped()

            Text(":")
                .font(.title2)
                .fontWeight(.medium)

            // Looping minute picker (0-59)
            LoopingMinutePicker(selection: minuteBinding)
                .frame(width: 60, height: 100)
                .clipped()

            // Looping AM/PM picker
            LoopingAMPMPicker(selection: ampmBinding)
                .frame(width: 60, height: 100)
                .clipped()

            Spacer()
        }
        .padding(.horizontal)
    }

    // MARK: - Departure Time Section
    @ViewBuilder
    private var departureTimeSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Departure Time", systemImage: "airplane.departure")
                    .font(.headline)
                    .foregroundStyle(Color.hbBrand)

                Spacer()

                if isSelectedDateToday {
                    Button(isStartingNow ? "Start Later" : "Starting Now") {
                        isStartingNow.toggle()
                    }
                    .font(.caption)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(isStartingNow ? Color(.tertiarySystemFill) : Color.hbBrand)
                    .foregroundStyle(isStartingNow ? Color.hbBrand : .white)
                    .cornerRadius(6)
                }
            }

            if isStartingNow && isSelectedDateToday {
                startingNowDisplay
            } else {
                departureTimePickerContent
            }
        }
        .padding()
        .background(Color(.secondarySystemFill))
        .cornerRadius(12)
    }

    @ViewBuilder
    private var startingNowDisplay: some View {
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
    }

    @ViewBuilder
    private var departureTimePickerContent: some View {
        Group {
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

            timePicker(hourBinding: $departureHour, minuteBinding: $departureMinute, ampmBinding: $departureAMPM)

            Text("\(selectedStartDate.formatted(.dateTime.weekday(.wide).month(.wide).day())) at \(departureTimeString)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Return Time Section
    @ViewBuilder
    private var returnTimeSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Return/Arrival Time", systemImage: "airplane.arrival")
                    .font(.headline)
                    .foregroundStyle(isReturnTimeValid ? Color.orange : Color.red)

                Spacer()

                if !isReturnTimeValid {
                    Text("Must be in future")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .fontWeight(.medium)
                }
            }

            timePicker(hourBinding: $returnHour, minuteBinding: $returnMinute, ampmBinding: $returnAMPM)

            if isReturnTimeValid {
                Text("\(selectedEndDate.formatted(.dateTime.weekday(.wide).month(.wide).day())) at \(returnTimeString)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                    Text("Return/Arrival time must be in the future")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }

            Text("If your trip is taking place out of service, plan your return/arrival time to be when you know you will be back in coverage, that way the grace period can be used effectively.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(isReturnTimeValid ? Color(.secondarySystemFill) : Color.red.opacity(0.1))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isReturnTimeValid ? Color.clear : Color.red.opacity(0.5), lineWidth: 1)
        )
        .cornerRadius(12)
    }

    // MARK: - Grace Period Section
    @ViewBuilder
    private var gracePeriodSection: some View {
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

                Slider(value: $graceMinutes, in: 0...120, step: 1)
                    .tint(graceMinutes == 0 ? .red : .orange)

                graceQuickSelectButtons
            }

            graceWarningText
        }
        .padding()
        .background(Color(.secondarySystemFill))
        .cornerRadius(12)
    }

    @ViewBuilder
    private var graceQuickSelectButtons: some View {
        HStack(spacing: 8) {
            ForEach([0, 15, 30, 60], id: \.self) { minutes in
                Button(action: {
                    graceMinutes = Double(minutes)
                }) {
                    let isSelected = graceMinutes == Double(minutes)
                    Text("\(minutes)m")
                        .font(.caption)
                        .fontWeight(isSelected ? .semibold : .regular)
                        .foregroundStyle(isSelected ? .white : Color.primary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(graceButtonBackground(minutes: minutes, isSelected: isSelected))
                        .cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func graceButtonBackground(minutes: Int, isSelected: Bool) -> Color {
        if isSelected {
            return minutes == 0 ? Color.red : Color.orange
        }
        return Color(.tertiarySystemFill)
    }

    @ViewBuilder
    private var graceWarningText: some View {
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

    // MARK: - Notification Settings Section
    private var notificationSettingsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Check-in Reminders", systemImage: "bell.badge")
                .font(.headline)
                .foregroundStyle(Color.hbBrand)

            VStack(spacing: 16) {
                // Check-in interval picker
                VStack(alignment: .leading, spacing: 8) {
                    Text("Reminder frequency")
                        .font(.subheadline)

                    HStack(spacing: 12) {
                        ForEach([15, 30, 60, 120], id: \.self) { minutes in
                            Button(action: {
                                checkinIntervalMinutes = minutes
                                showCustomInterval = false
                            }) {
                                Text(minutes < 60 ? "\(minutes)m" : "\(minutes/60)h")
                                    .font(.subheadline)
                                    .fontWeight(checkinIntervalMinutes == minutes && !showCustomInterval ? .semibold : .regular)
                                    .foregroundStyle(checkinIntervalMinutes == minutes && !showCustomInterval ? .white : .primary)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 10)
                                    .padding(.horizontal, 4)
                                    .background(checkinIntervalMinutes == minutes && !showCustomInterval ? Color.hbBrand : Color(.tertiarySystemFill))
                                    .cornerRadius(8)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    // Custom button on separate row
                    Button(action: { showCustomInterval = true }) {
                        Text("Custom")
                            .font(.subheadline)
                            .fontWeight(showCustomInterval || ![15, 30, 60, 120].contains(checkinIntervalMinutes) ? .semibold : .regular)
                            .foregroundStyle(showCustomInterval || ![15, 30, 60, 120].contains(checkinIntervalMinutes) ? .white : .primary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(showCustomInterval || ![15, 30, 60, 120].contains(checkinIntervalMinutes) ? Color.hbBrand : Color(.tertiarySystemFill))
                            .cornerRadius(8)
                    }
                    .buttonStyle(.plain)

                    // Custom interval input
                    if showCustomInterval || ![15, 30, 60, 120].contains(checkinIntervalMinutes) {
                        HStack {
                            TextField("Minutes", value: $checkinIntervalMinutes, format: .number)
                                .keyboardType(.numberPad)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 80)
                            Text("minutes")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Text("How often you'll be reminded to check in during your trip")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Notification hours toggle (available for all trips)
                Divider()
                    .padding(.vertical, 4)

                VStack(alignment: .leading, spacing: 12) {
                    Toggle(isOn: $useNotificationHours) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Set notification hours")
                                .font(.subheadline)
                            Text("Only receive reminders during specific hours")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    if useNotificationHours {
                        VStack(alignment: .leading, spacing: 16) {
                            HStack {
                                Text("From")
                                    .font(.subheadline)
                                Spacer()
                                Text(formatHour(notifyStartHour))
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                                Stepper("", value: $notifyStartHour, in: 0...23)
                                    .labelsHidden()
                            }

                            HStack {
                                Text("Until")
                                    .font(.subheadline)
                                Spacer()
                                Text(formatHour(notifyEndHour))
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                                Stepper("", value: $notifyEndHour, in: 0...23)
                                    .labelsHidden()
                            }

                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "exclamationmark.shield.fill")
                                    .foregroundStyle(.orange)
                                    .font(.caption)
                                Text("Emergency alerts during grace period always come through")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding()
                        .background(Color(.tertiarySystemFill))
                        .cornerRadius(8)
                    }
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemFill))
        .cornerRadius(12)
    }

    private func formatHour(_ hour: Int) -> String {
        if hour == 0 { return "12:00 AM" }
        if hour == 12 { return "12:00 PM" }
        if hour < 12 { return "\(hour):00 AM" }
        return "\(hour - 12):00 PM"
    }

    // MARK: - Timezone Settings Section
    private var timezoneSettingsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showTimezoneOptions.toggle()
                }
            }) {
                HStack {
                    Image(systemName: "globe")
                        .foregroundStyle(showTimezoneOptions ? Color.hbBrand : .secondary)
                    Text("Different timezone?")
                        .font(.subheadline)
                        .foregroundStyle(showTimezoneOptions ? Color.hbBrand : .primary)
                    Spacer()
                    Image(systemName: showTimezoneOptions ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding()
                .background(Color(.secondarySystemFill))
                .cornerRadius(12)
            }
            .buttonStyle(.plain)

            if showTimezoneOptions {
                VStack(spacing: 16) {
                    // Start time timezone
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Start time timezone")
                            .font(.subheadline)
                            .fontWeight(.medium)

                        TimezonePicker(selectedTimezone: $startTimezone)
                    }

                    Divider()

                    // Return time timezone
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Return time timezone")
                            .font(.subheadline)
                            .fontWeight(.medium)

                        TimezonePicker(selectedTimezone: $etaTimezone)
                    }

                    // Info note
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "info.circle")
                            .foregroundStyle(.secondary)
                            .font(.caption)
                        Text("Times will be converted to UTC for storage. Your contacts will see times in their local timezone.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
                .background(Color(.tertiarySystemFill))
                .cornerRadius(12)
            }
        }
    }

    // MARK: - Time Selection Phase
    @ViewBuilder
    private var timeSelectionPhase: some View {
        VStack(spacing: 20) {
            dateRangeSummaryHeader
            departureTimeSection
            returnTimeSection
            gracePeriodSection
            notificationSettingsSection
            timezoneSettingsSection
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                headerSection

                if !showingTimeSelection {
                    dateSelectionPhase
                } else {
                    timeSelectionPhase
                }

                Spacer(minLength: 100)
            }
            .padding(.horizontal)
        }
        .scrollIndicators(.hidden)
        .scrollDismissesKeyboard(.interactively)
        .onAppear {
            // When editing an existing trip, don't default to "Starting Now"
            // This preserves the trip's scheduled start time
            if isEditMode {
                isStartingNow = false
            }

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
        .sheet(isPresented: $showCalendarHelp) {
            HelpSheet(
                title: "Time Settings",
                message: "Select when you're leaving and when you expect to return. The grace period is extra time before your contacts are notified if you haven't checked in."
            )
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

                // Your Contacts Section
                VStack(alignment: .leading, spacing: 12) {
                    HStack{
                        Text("Your Contacts (\(contacts.count)/3 selected)")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                        // Required contact message when none selected
                        if contacts.isEmpty && !savedContacts.isEmpty {
                            HStack {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundStyle(Color.orange)
                                Text("≥1 contact required")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        if contacts.count >= 3 {
                            HStack {
                                Image(systemName: "info.circle.fill")
                                    .foregroundStyle(Color.orange)
                                Text("Max contacts added")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    if isLoadingSaved {
                        HStack {
                            Spacer()
                            ProgressView()
                            Spacer()
                        }
                        .padding(.vertical, 20)
                    } else if savedContacts.isEmpty {
                        // Empty state - no saved contacts
                        VStack(spacing: 12) {
                            Image(systemName: "person.crop.circle.badge.questionmark")
                                .font(.system(size: 36))
                                .foregroundStyle(.secondary)
                            Text("No saved contacts yet")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 20)
                    } else {
                        // Inline contact list with toggle selection
                        ForEach(savedContacts) { contact in
                            ContactSelectionRow(
                                contact: contact,
                                isSelected: isContactSelected(contact),
                                canSelect: contacts.count < 3 || isContactSelected(contact)
                            ) { selected in
                                toggleContact(contact, selected: selected)
                            }
                        }
                    }

                    // Add New Contact Button
                    Button(action: { showAddContact = true }) {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                                .font(.title3)
                            Text("Add New Contact")
                                .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.hbAccent)
                        .foregroundStyle(.white)
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
        .scrollIndicators(.hidden)
        .task {
            isLoadingSaved = true
            await loadContacts()
        }
    }

    private func loadContacts() async {
        let loaded = await session.loadContacts()
        await MainActor.run {
            self.savedContacts = loaded
            self.isLoadingSaved = false
            debugLog("DEBUG: Loaded \(loaded.count) saved contacts")
        }
    }

    private func isContactSelected(_ contact: Contact) -> Bool {
        contacts.contains { $0.savedContactId == contact.id }
    }

    private func toggleContact(_ contact: Contact, selected: Bool) {
        if selected {
            // Add contact if under limit
            if contacts.count < 3 {
                contacts.append(EmergencyContact(
                    name: contact.name,
                    email: contact.email,
                    savedContactId: contact.id
                ))
            }
        } else {
            // Remove contact
            contacts.removeAll { $0.savedContactId == contact.id }
        }
    }
}

// MARK: - Step 4: Additional Notes
struct Step4AdditionalNotes: View {
    @Binding var notes: String
    @Binding var isCreating: Bool
    var isEditMode: Bool = false
    let onSubmit: () -> Void
    @State private var showNotesHelp = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Additional Notes")
                            .font(.largeTitle)
                            .fontWeight(.bold)

                        Button(action: { showNotesHelp = true }) {
                            Image(systemName: "questionmark.circle.fill")
                                .font(.title3)
                                .foregroundStyle(Color.hbBrand.opacity(0.7))
                        }
                    }
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
                    Image(systemName: isEditMode ? "pencil.circle.fill" : "checkmark.circle.fill")
                        .font(.system(size: 48))
                        .foregroundStyle(Color.hbAccent)

                    Text(isEditMode ? "Ready to save changes?" : "Ready to start your adventure?")
                        .font(.headline)

                    Text(isEditMode ? "Your trip details will be updated" : "We'll keep track of your journey and notify your contacts if needed")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 30)

                // Start Adventure / Save Changes Button
                Button(action: onSubmit) {
                    HStack {
                        if isCreating {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                .scaleEffect(0.9)
                        } else {
                            Image(systemName: isEditMode ? "checkmark" : "flag.checkered")
                            Text(isEditMode ? "Save Changes" : "Start Adventure")
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
        .scrollIndicators(.hidden)
        .sheet(isPresented: $showNotesHelp) {
            HelpSheet(
                title: "Additional Notes",
                message: "Add any extra details your contacts might need, like your planned route, who you're with, or specific locations you'll visit."
            )
        }
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
                    .scrollIndicators(.hidden)
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
                                guard !saved.email.isEmpty else {
                                    return nil
                                }
                                // Don't add duplicates
                                guard !selectedContacts.contains(where: { $0.email == saved.email }) else {
                                    return nil
                                }
                                return EmergencyContact(
                                    name: saved.name,
                                    email: saved.email,
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
                    .fill(isSelected ? Color.hbBrand : Color.hbAccent)
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

                    if !contact.email.isEmpty {
                        Text(contact.email)
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
            .padding(.vertical, 8)
            .padding(.horizontal, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isSelected ? Color.hbBrand.opacity(0.1) : Color(.secondarySystemFill))
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!canSelect && !isSelected)
    }
}

// MARK: - Help Sheet
struct HelpSheet: View {
    let title: String
    let message: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Image(systemName: "questionmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(Color.hbBrand)

                Text(message)
                    .font(.body)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)

                Spacer()
            }
            .padding()
            .padding(.top, 20)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .presentationDetents([.medium])
        }
    }
}

// MARK: - Looping Pickers
struct LoopingHourPicker: View {
    @Binding var selection: Int

    // Create a large range of repeated hours for looping effect
    private let repetitions = 100
    private let hours = Array(1...12)

    private var allHours: [Int] {
        var result: [Int] = []
        for _ in 0..<repetitions {
            result.append(contentsOf: hours)
        }
        return result
    }

    // Find the middle index for the current selection
    private func middleIndex(for hour: Int) -> Int {
        let middleRepetition = repetitions / 2
        let indexInCycle = hour - 1 // Convert 1-12 to 0-11
        return middleRepetition * 12 + indexInCycle
    }

    var body: some View {
        Picker("Hour", selection: Binding(
            get: { middleIndex(for: selection) },
            set: { newIndex in
                selection = allHours[newIndex]
            }
        )) {
            ForEach(Array(allHours.enumerated()), id: \.offset) { index, hour in
                Text("\(hour)")
                    .tag(index)
            }
        }
        .pickerStyle(.wheel)
    }
}

struct LoopingMinutePicker: View {
    @Binding var selection: Int

    // Create a large range of repeated minutes for looping effect
    private let repetitions = 100
    private let minutes = Array(0..<60)

    private var allMinutes: [Int] {
        var result: [Int] = []
        for _ in 0..<repetitions {
            result.append(contentsOf: minutes)
        }
        return result
    }

    // Find the middle index for the current selection
    private func middleIndex(for minute: Int) -> Int {
        let middleRepetition = repetitions / 2
        return middleRepetition * 60 + minute
    }

    var body: some View {
        Picker("Minute", selection: Binding(
            get: { middleIndex(for: selection) },
            set: { newIndex in
                selection = allMinutes[newIndex]
            }
        )) {
            ForEach(Array(allMinutes.enumerated()), id: \.offset) { index, minute in
                Text(String(format: "%02d", minute))
                    .tag(index)
            }
        }
        .pickerStyle(.wheel)
    }
}

struct LoopingAMPMPicker: View {
    @Binding var selection: Int

    // Create a large range of repeated AM/PM for looping effect
    private let repetitions = 100
    private let values = [0, 1] // 0 = AM, 1 = PM

    private var allValues: [Int] {
        var result: [Int] = []
        for _ in 0..<repetitions {
            result.append(contentsOf: values)
        }
        return result
    }

    // Find the middle index for the current selection
    private func middleIndex(for value: Int) -> Int {
        let middleRepetition = repetitions / 2
        return middleRepetition * 2 + value
    }

    var body: some View {
        Picker("AM/PM", selection: Binding(
            get: { middleIndex(for: selection) },
            set: { newIndex in
                selection = allValues[newIndex]
            }
        )) {
            ForEach(Array(allValues.enumerated()), id: \.offset) { index, value in
                Text(value == 0 ? "AM" : "PM")
                    .tag(index)
            }
        }
        .pickerStyle(.wheel)
    }
}

// MARK: - Timezone Picker
struct TimezonePicker: View {
    @Binding var selectedTimezone: TimeZone
    @State private var showingPicker = false
    @State private var searchText = ""

    // Common US timezones at the top
    private let commonTimezones: [(id: String, abbrev: String, name: String)] = [
        ("America/Los_Angeles", "PT", "Pacific Time"),
        ("America/Denver", "MT", "Mountain Time"),
        ("America/Chicago", "CT", "Central Time"),
        ("America/New_York", "ET", "Eastern Time"),
        ("America/Anchorage", "AKT", "Alaska Time"),
        ("Pacific/Honolulu", "HT", "Hawaii Time"),
    ]

    // All available timezones
    private var allTimezones: [TimeZone] {
        TimeZone.knownTimeZoneIdentifiers
            .compactMap { TimeZone(identifier: $0) }
            .sorted { $0.identifier < $1.identifier }
    }

    private var filteredTimezones: [TimeZone] {
        if searchText.isEmpty {
            return allTimezones
        }
        return allTimezones.filter { tz in
            tz.identifier.localizedCaseInsensitiveContains(searchText) ||
            (tz.abbreviation() ?? "").localizedCaseInsensitiveContains(searchText)
        }
    }

    private func formatTimezone(_ tz: TimeZone) -> String {
        let offset = tz.secondsFromGMT()
        let hours = offset / 3600
        let minutes = abs(offset % 3600) / 60
        let sign = hours >= 0 ? "+" : ""
        if minutes == 0 {
            return "UTC\(sign)\(hours)"
        } else {
            return "UTC\(sign)\(hours):\(String(format: "%02d", minutes))"
        }
    }

    private func currentTimeIn(_ tz: TimeZone) -> String {
        let formatter = DateFormatter()
        formatter.timeZone = tz
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: Date())
    }

    var body: some View {
        Button(action: { showingPicker = true }) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    // Check if it's a common timezone
                    if let common = commonTimezones.first(where: { $0.id == selectedTimezone.identifier }) {
                        Text(common.name)
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                        Text("\(common.abbrev) (\(formatTimezone(selectedTimezone))) - \(currentTimeIn(selectedTimezone))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text(selectedTimezone.identifier.replacingOccurrences(of: "_", with: " "))
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                        Text("\(formatTimezone(selectedTimezone)) - \(currentTimeIn(selectedTimezone))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .background(Color(.secondarySystemFill))
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showingPicker) {
            NavigationStack {
                List {
                    // Current device timezone
                    Section("Current") {
                        Button(action: {
                            selectedTimezone = .current
                            showingPicker = false
                        }) {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Device Timezone")
                                        .font(.subheadline)
                                        .foregroundStyle(.primary)
                                    Text("\(TimeZone.current.identifier) - \(currentTimeIn(.current))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if selectedTimezone.identifier == TimeZone.current.identifier {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(Color.hbBrand)
                                }
                            }
                        }
                    }

                    // Common US timezones
                    Section("Common") {
                        ForEach(commonTimezones, id: \.id) { tz in
                            if let timezone = TimeZone(identifier: tz.id) {
                                Button(action: {
                                    selectedTimezone = timezone
                                    showingPicker = false
                                }) {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(tz.name)
                                                .font(.subheadline)
                                                .foregroundStyle(.primary)
                                            Text("\(tz.abbrev) (\(formatTimezone(timezone))) - \(currentTimeIn(timezone))")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                        Spacer()
                                        if selectedTimezone.identifier == tz.id {
                                            Image(systemName: "checkmark")
                                                .foregroundStyle(Color.hbBrand)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // All timezones (searchable)
                    Section("All Timezones") {
                        ForEach(filteredTimezones, id: \.identifier) { tz in
                            Button(action: {
                                selectedTimezone = tz
                                showingPicker = false
                            }) {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(tz.identifier.replacingOccurrences(of: "_", with: " "))
                                            .font(.subheadline)
                                            .foregroundStyle(.primary)
                                        Text("\(formatTimezone(tz)) - \(currentTimeIn(tz))")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if selectedTimezone.identifier == tz.identifier {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(Color.hbBrand)
                                    }
                                }
                            }
                        }
                    }
                }
                .searchable(text: $searchText, prompt: "Search timezones")
                .navigationTitle("Select Timezone")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { showingPicker = false }
                    }
                }
            }
        }
    }
}

#Preview {
    CreatePlanView()
        .environmentObject(Session())
}