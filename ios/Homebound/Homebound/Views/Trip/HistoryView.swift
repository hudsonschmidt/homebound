import SwiftUI

// MARK: - Offline Disclaimer Banner
struct OfflineDisclaimerBanner: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "icloud.slash")
                .font(.title3)
                .foregroundStyle(.orange)

            VStack(alignment: .leading, spacing: 2) {
                Text("Viewing Cached Data")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Text("Showing last 25 trips. Connect to internet to see all trips.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.orange.opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.orange.opacity(0.3), lineWidth: 1)
                )
        )
    }
}

struct HistoryView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss
    @ObservedObject private var networkMonitor = NetworkMonitor.shared
    @State private var isLoading = false
    @State private var searchText = ""
    @State private var errorMessage: String?
    @State private var tripToEdit: Trip?
    @State private var deletingPlanIds: Set<Int> = []  // Track plans being deleted

    // Presentation mode - controls whether this is shown as a tab or modal
    var showAsTab: Bool = false
    var showStats: Bool = false

    // Derive from session.isOffline instead of tracking separately
    var isShowingCachedData: Bool {
        !networkMonitor.isConnected
    }

    var filteredPlans: [Trip] {
        let filtered = session.allTrips.filter { plan in
            if !searchText.isEmpty {
                return plan.title.localizedCaseInsensitiveContains(searchText) ||
                       (plan.location_text ?? "").localizedCaseInsensitiveContains(searchText)
            }
            return true
        }
        // Sort by completion time for completed trips, start time for others
        return filtered.sorted { plan1, plan2 in
            let date1: Date
            if plan1.status == "completed", let completedAt = plan1.completed_at {
                date1 = completedAt
            } else {
                date1 = plan1.start_at
            }

            let date2: Date
            if plan2.status == "completed", let completedAt = plan2.completed_at {
                date2 = completedAt
            } else {
                date2 = plan2.start_at
            }

            return date1 > date2
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Background - adapts to dark mode
                Color(.systemBackground)
                    .ignoresSafeArea()

                if isLoading && session.allTrips.isEmpty {
                    ProgressView("Loading history...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if filteredPlans.isEmpty && !isLoading {
                    EmptyHistoryView(hasSearchText: !searchText.isEmpty)
                } else {
                    List {
                        // Offline Disclaimer Banner
                        if isShowingCachedData || !networkMonitor.isConnected {
                            Section {
                                OfflineDisclaimerBanner()
                            }
                            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                            .listRowBackground(Color.clear)
                            .listRowSeparator(.hidden)
                        }

                        // Stats Section (optional - respects user preference)
                        if showStats && AppPreferences.shared.showStats && !session.allTrips.isEmpty {
                            Section {
                                TripStatsView(plans: session.allTrips)
                            }
                            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                            .listRowBackground(Color.clear)
                            .listRowSeparator(.hidden)
                        }

                        // Search Bar Section
                        Section {
                            HStack {
                                Image(systemName: "magnifyingglass")
                                    .foregroundStyle(.secondary)
                                TextField("Search trips...", text: $searchText)
                                    .textFieldStyle(.plain)
                                if !searchText.isEmpty {
                                    Button(action: { searchText = "" }) {
                                        Image(systemName: "xmark.circle.fill")
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            .padding(12)
                            .background(Color(.secondarySystemBackground))
                            .cornerRadius(12)
                        }
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)

                        // Trip List
                        Section {
                            ForEach(filteredPlans) { plan in
                                // Only non-planned trips are tappable
                                if plan.status != "planned" {
                                    ZStack {
                                        // Hidden NavigationLink (no chevron)
                                        NavigationLink(destination: TripDetailView(trip: plan)) {
                                            EmptyView()
                                        }
                                        .opacity(0)

                                        TripHistoryCard(plan: plan)
                                    }
                                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                        Button(role: .destructive) {
                                            Task {
                                                await deletePlan(plan)
                                            }
                                        } label: {
                                            Label("Delete", systemImage: "trash")
                                        }
                                    }
                                } else {
                                    // Planned trips are not tappable
                                    TripHistoryCard(plan: plan)
                                        .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                                        .listRowBackground(Color.clear)
                                        .listRowSeparator(.hidden)
                                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                            Button(role: .destructive) {
                                                Task {
                                                    await deletePlan(plan)
                                                }
                                            } label: {
                                                Label("Delete", systemImage: "trash")
                                            }

                                            Button {
                                                tripToEdit = plan
                                            } label: {
                                                Label("Edit", systemImage: "pencil")
                                            }
                                            .tint(.blue)
                                        }
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .scrollIndicators(.hidden)
                }
            }
            .navigationTitle("Trip History")
            .navigationBarTitleDisplayMode(showAsTab ? .large : .inline)
            .toolbar {
                if !showAsTab {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Done") {
                            dismiss()
                        }
                        .fontWeight(.semibold)
                    }
                }
            }
            .task {
                await loadAllPlans()
            }
            .refreshable {
                await loadAllPlans()
            }
            .alert("Error", isPresented: .constant(errorMessage != nil)) {
                Button("OK") { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
            .sheet(item: $tripToEdit) { trip in
                CreatePlanView(existingTrip: trip)
                    .environmentObject(session)
                    .onDisappear {
                        // Refresh the list after editing
                        Task {
                            await loadAllPlans()
                        }
                    }
            }
        }
    }

    func loadAllPlans() async {
        await MainActor.run {
            isLoading = true
            errorMessage = nil
        }

        // Use session.loadAllTrips() which handles caching and offline
        _ = await session.loadAllTrips()

        await MainActor.run {
            isLoading = false
        }
    }

    func deletePlan(_ plan: Trip) async {
        // Prevent double-delete: skip if already being deleted
        guard !deletingPlanIds.contains(plan.id) else {
            debugLog("[HistoryView] Skipping duplicate delete for trip #\(plan.id)")
            return
        }

        // Mark as being deleted
        await MainActor.run {
            deletingPlanIds.insert(plan.id)
            errorMessage = nil  // Clear any previous error
        }

        let success = await session.deletePlan(plan.id)

        await MainActor.run {
            deletingPlanIds.remove(plan.id)
            if !success {
                errorMessage = "Failed to delete trip"
            }
        }
    }
}

// MARK: - Empty History View
struct EmptyHistoryView: View {
    let hasSearchText: Bool

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: hasSearchText ? "magnifyingglass" : "clock.badge.xmark")
                .font(.system(size: 60))
                .foregroundStyle(Color.gray.opacity(0.5))

            Text(hasSearchText ? "No trips found" : "No Trip History")
                .font(.title2)
                .fontWeight(.semibold)

            Text(hasSearchText ? "Try a different search" : "Your completed trips will appear here")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Trip History Card
struct TripHistoryCard: View {
    let plan: Trip

    var primaryColor: Color {
        Color(hex: plan.activity.colors.primary) ?? .hbBrand
    }

    var activityIcon: String {
        plan.activity.icon
    }

    var activityName: String {
        plan.activity.name
    }

    var statusColor: Color {
        switch plan.status {
        case "active": return .orange
        case "completed": return .green
        case "overdue", "overdue_notified": return .red
        case "cancelled": return .gray
        default: return .gray
        }
    }

    // Helper to format date and time nicely (using the trip's stored timezone if provided)
    // Includes timezone abbreviation if a custom timezone was used
    func formatDateTime(_ date: Date, timezone: String? = nil) -> String {
        let formatted = DateUtils.formatDateTime(date, inTimezone: timezone)
        // Add timezone abbreviation if a custom timezone is specified
        if let tzId = timezone,
           let tz = TimeZone(identifier: tzId),
           tz != .current,
           let abbr = tz.abbreviation(for: date) {
            return "\(formatted) \(abbr)"
        }
        return formatted
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with icon, title, and status
            HStack(alignment: .top, spacing: 12) {
                // Activity Icon
                Circle()
                    .fill(primaryColor.opacity(0.2))
                    .frame(width: 48, height: 48)
                    .overlay(
                        Text(activityIcon)
                            .font(.title2)
                    )

                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title)
                        .font(.headline)
                        .lineLimit(2)

                    Text(activityName)
                        .font(.caption)
                        .foregroundStyle(primaryColor)
                        .fontWeight(.medium)
                }

                Spacer()

                // Status Badge
                Text(plan.status.capitalized)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(statusColor.opacity(0.2))
                    .foregroundStyle(statusColor)
                    .cornerRadius(8)
            }

            Divider()

            // Trip Details
            VStack(alignment: .leading, spacing: 8) {
                // Start Time (displayed in the trip's start timezone)
                InfoRow(
                    icon: "arrow.right.circle.fill",
                    iconColor: .green,
                    label: "Started",
                    value: formatDateTime(plan.start_at, timezone: plan.start_timezone)
                )

                // Finish Time
                if plan.status == "completed" {
                    if let completedAt = plan.completed_at {
                        InfoRow(
                            icon: "checkmark.circle.fill",
                            iconColor: .blue,
                            label: "Finished",
                            value: formatDateTime(completedAt)
                        )
                    } else {
                        InfoRow(
                            icon: "checkmark.circle.fill",
                            iconColor: .blue,
                            label: "Finished",
                            value: "(time unknown)"
                        )
                    }
                } else {
                    // ETA (displayed in the trip's ETA timezone)
                    InfoRow(
                        icon: "clock.fill",
                        iconColor: .orange,
                        label: "Expected",
                        value: formatDateTime(plan.eta_at, timezone: plan.eta_timezone)
                    )
                }

                // Duration
                if plan.status == "completed", let completedAt = plan.completed_at {
                    // Actual duration for completed trips
                    if let duration = DateUtils.formatDuration(from: plan.start_at, to: completedAt) {
                        InfoRow(
                            icon: "timer",
                            iconColor: .hbBrand,
                            label: "Duration",
                            value: duration
                        )
                    }
                } else if plan.status == "completed" {
                    // Completed but no completion time - show unknown
                    InfoRow(
                        icon: "timer",
                        iconColor: .hbBrand,
                        label: "Duration",
                        value: "(unknown)"
                    )
                } else {
                    // Expected duration for active/planned trips
                    if let duration = DateUtils.formatDuration(from: plan.start_at, to: plan.eta_at) {
                        InfoRow(
                            icon: "timer",
                            iconColor: .hbBrand,
                            label: "Duration",
                            value: duration
                        )
                    }
                }

                // Start Location (if trip has separate start/destination)
                if plan.has_separate_locations, let startLocation = plan.start_location_text {
                    InfoRow(
                        icon: "figure.walk.departure",
                        iconColor: .green,
                        label: "Start",
                        value: startLocation
                    )
                }

                // Location / Destination (if available)
                if let location = plan.location_text {
                    InfoRow(
                        icon: plan.has_separate_locations ? "flag.fill" : "location.fill",
                        iconColor: .red,
                        label: plan.has_separate_locations ? "Destination" : "Location",
                        value: location
                    )
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.05), radius: 5, x: 0, y: 2)
    }
}

// MARK: - Info Row Helper
struct InfoRow: View {
    let icon: String
    let iconColor: Color
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(iconColor)
                .frame(width: 16)

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 70, alignment: .leading)

            Text(value)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(1)

            Spacer(minLength: 0)
        }
    }
}

// MARK: - Trip Stats View
struct TripStatsView: View {
    let plans: [Trip]
    @State private var preferences = StatsPreferences.load()
    @State private var showingEditStats = false

    var calculator: TripStatsCalculator {
        TripStatsCalculator(trips: plans)
    }

    var favoriteActivity: (icon: String, name: String, count: Int)? {
        let completedPlans = plans.filter { $0.status == "completed" }
        let activityCounts = Dictionary(grouping: completedPlans) { plan in
            plan.activity.id
        }

        guard let mostCommon = activityCounts.max(by: { $0.value.count < $1.value.count }),
              let firstTrip = mostCommon.value.first else {
            return nil
        }

        let activity = firstTrip.activity
        return (activity.icon, activity.name, mostCommon.value.count)
    }

    var useScrolling: Bool {
        preferences.selectedStats.count > 4
    }

    var body: some View {
        VStack(spacing: 12) {
            // Header with Edit button
            HStack {
                Text("Your Adventure Stats")
                    .font(.headline)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.hbBrand, Color.hbTeal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                Spacer()
                Button(action: { showingEditStats = true }) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.title3)
                        .foregroundStyle(Color.hbBrand)
                }
            }

            // Stats Grid or Scrolling
            if useScrolling {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(Array(preferences.selectedStats.enumerated()), id: \.element) { index, statType in
                            AnimatedStatCard(
                                statType: statType,
                                value: calculator.value(for: statType),
                                delay: Double(index) * 0.1
                            )
                            .frame(width: 140)
                        }
                    }
                }
            } else {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ForEach(Array(preferences.selectedStats.enumerated()), id: \.element) { index, statType in
                        AnimatedStatCard(
                            statType: statType,
                            value: calculator.value(for: statType),
                            delay: Double(index) * 0.1
                        )
                    }
                }
            }

            // Favorite Activity (if available)
            if let favorite = favoriteActivity {
                HStack(spacing: 12) {
                    Circle()
                        .fill(Color.hbBrand.opacity(0.2))
                        .frame(width: 44, height: 44)
                        .overlay(
                            Text(favorite.icon)
                                .font(.title3)
                        )

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Favorite Activity")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(favorite.name)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }

                    Spacer()

                    Text("\(favorite.count) trips")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.hbBrand)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.hbBrand.opacity(0.1))
                        .cornerRadius(8)
                }
                .padding()
                .background(Color(.tertiarySystemBackground))
                .cornerRadius(12)
                .transition(.scale.combined(with: .opacity))
            }
        }
        .sheet(isPresented: $showingEditStats) {
            EditStatsView(preferences: $preferences)
        }
    }
}

// MARK: - Animated Stat Card
struct AnimatedStatCard: View {
    let statType: StatType
    let value: String
    let delay: Double

    @State private var appeared = false
    @State private var scale: CGFloat = 0.8

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: statType.icon)
                .font(.title2)
                .foregroundStyle(statType.color)

            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundStyle(.primary)
                .opacity(appeared ? 1 : 0)

            Text(statType.displayName)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(
            LinearGradient(
                colors: [
                    statType.color.opacity(0.1),
                    statType.color.opacity(0.05)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .cornerRadius(12)
        .scaleEffect(scale)
        .onAppear {
            // Only animate if not already appeared (prevents flickering on scroll)
            guard !appeared else { return }
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7).delay(delay)) {
                appeared = true
                scale = 1.0
            }
        }
    }
}

// MARK: - Achievement Cell
struct AchievementCell: View {
    let achievement: AchievementDefinition
    let isEarned: Bool

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: isEarned ? achievement.sfSymbol : "lock.fill")
                .font(.title2)
                .foregroundStyle(isEarned ? achievement.category.color : .gray)

            Text(achievement.title)
                .font(.caption2)
                .foregroundStyle(isEarned ? .primary : .secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isEarned ? achievement.category.color.opacity(0.1) : Color.gray.opacity(0.1))
        )
        .opacity(isEarned ? 1 : 0.5)
    }
}

// MARK: - Achievements Grid View
struct AchievementsGridView: View {
    let calculator: TripStatsCalculator
    @Binding var showingSheet: Bool

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 8), count: 4)

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Achievements")
                    .font(.headline)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color.orange, Color.yellow],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )

                Spacer()

                Text("\(calculator.earnedAchievementsCount)/\(AchievementDefinition.all.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(AchievementDefinition.all) { achievement in
                    AchievementCell(
                        achievement: achievement,
                        isEarned: calculator.hasEarned(achievement)
                    )
                }
            }
        }
        .padding()
        .background(Color(.tertiarySystemBackground))
        .cornerRadius(12)
        .contentShape(Rectangle())
        .onTapGesture {
            showingSheet = true
        }
    }
}

// MARK: - Edit Stats View
struct EditStatsView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var preferences: StatsPreferences
    @State private var selectedStats: [StatType]

    init(preferences: Binding<StatsPreferences>) {
        self._preferences = preferences
        self._selectedStats = State(initialValue: preferences.wrappedValue.selectedStats)
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Select up to 8 stats to display on your Adventure Stats dashboard")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Customize Your Stats")
                }

                Section {
                    ForEach(StatType.allCases, id: \.self) { statType in
                        HStack {
                            Image(systemName: statType.icon)
                                .foregroundStyle(statType.color)
                                .frame(width: 24)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(statType.displayName)
                                    .font(.subheadline)

                                Text(getStatDescription(statType))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            if selectedStats.contains(statType) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(statType.color)
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            toggleStat(statType)
                        }
                    }
                } header: {
                    Text("Available Stats (\(selectedStats.count)/8)")
                }

                Section {
                    Button("Reset to Default") {
                        selectedStats = StatsPreferences.defaultStats
                    }
                    .foregroundStyle(.red)
                }
            }
            .scrollIndicators(.hidden)
            .navigationTitle("Edit Stats")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        savePreferences()
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .disabled(selectedStats.isEmpty)
                }
            }
        }
    }

    func toggleStat(_ statType: StatType) {
        if selectedStats.contains(statType) {
            selectedStats.removeAll { $0 == statType }
        } else if selectedStats.count < 8 {
            selectedStats.append(statType)
        }
    }

    func savePreferences() {
        preferences.selectedStats = selectedStats
        preferences.save()
    }

    func getStatDescription(_ statType: StatType) -> String {
        switch statType {
        case .totalTrips: return "Total number of adventures"
        case .adventureTime: return "Total time on all trips"
        case .longestAdventure: return "Your longest single trip"
        case .activitiesTried: return "Different activity types"
        case .thisMonth: return "Trips this month"
        case .uniqueLocations: return "Different places visited"
        case .mostAdventurousMonth: return "Month with most trips"
        case .averageTripDuration: return "Average trip length"
        }
    }
}

#Preview {
    HistoryView()
        .environmentObject(Session())
}
