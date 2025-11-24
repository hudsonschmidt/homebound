import SwiftUI

struct HistoryView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss
    @State private var allPlans: [PlanOut] = []
    @State private var isLoading = true
    @State private var searchText = ""

    var filteredPlans: [PlanOut] {
        let filtered = allPlans.filter { plan in
            if !searchText.isEmpty {
                return plan.title.localizedCaseInsensitiveContains(searchText) ||
                       (plan.location_text ?? "").localizedCaseInsensitiveContains(searchText)
            }
            return true
        }
        // Sort by completion time for completed trips, start time for others
        return filtered.sorted { plan1, plan2 in
            let date1: Date
            if plan1.status == "completed", let completedStr = plan1.completed_at,
               let completedDate = parseDate(completedStr) {
                date1 = completedDate
            } else {
                date1 = plan1.start_at
            }

            let date2: Date
            if plan2.status == "completed", let completedStr = plan2.completed_at,
               let completedDate = parseDate(completedStr) {
                date2 = completedDate
            } else {
                date2 = plan2.start_at
            }

            return date1 > date2
        }
    }

    // Helper function for parsing dates (used in sorting and display)
    private func parseDate(_ dateString: String) -> Date? {
        // Try ISO8601 format first
        let iso8601Formatter = ISO8601DateFormatter()
        iso8601Formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso8601Formatter.date(from: dateString) {
            return date
        }

        // Try without fractional seconds
        iso8601Formatter.formatOptions = [.withInternetDateTime]
        if let date = iso8601Formatter.date(from: dateString) {
            return date
        }

        // Try custom format for backend timestamps
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        if let date = formatter.date(from: dateString) {
            return date
        }

        return nil
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Background - adapts to dark mode
                Color(.systemBackground)
                    .ignoresSafeArea()

                if isLoading {
                    ProgressView("Loading trips...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if filteredPlans.isEmpty {
                    VStack(spacing: 20) {
                        Image(systemName: "map.fill")
                            .font(.system(size: 60))
                            .foregroundStyle(Color.gray.opacity(0.5))

                        Text("No trips found")
                            .font(.title2)
                            .fontWeight(.semibold)

                        Text(searchText.isEmpty ? "Start your first adventure!" : "Try a different search")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    VStack(spacing: 0) {
                        // Search Bar
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
                        .padding(.horizontal)
                        .padding(.vertical)

                        // Trip List using List for swipe actions
                        List {
                            ForEach(filteredPlans) { plan in
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
                                    }
                            }
                        }
                        .listStyle(.plain)
                        .scrollContentBackground(.hidden)
                    }
                }
            }
            .navigationTitle("Trip History")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
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
    }

    func loadAllPlans() async {
        guard let bearer = session.accessToken else { return }

        isLoading = true
        do {
            // Backend returns all trips ordered by created_at DESC (most recent first)
            let plans: [PlanOut] = try await session.api.get(
                session.url("/api/v1/trips/"),
                bearer: bearer
            )

            print("[HistoryView] 📥 Loaded \(plans.count) total trips from backend")
            plans.forEach { plan in
                print("[HistoryView] - '\(plan.title)': status=\(plan.status), completed_at=\(plan.completed_at ?? "nil")")
            }

            await MainActor.run {
                self.allPlans = plans
                self.isLoading = false
            }
        } catch {
            print("[HistoryView] ❌ Failed to load history: \(error)")
            if let decodingError = error as? DecodingError {
                print("[HistoryView] Decoding error details: \(decodingError)")
            }

            await MainActor.run {
                self.isLoading = false
                session.lastError = "Failed to load history: \(error.localizedDescription)"
            }
        }
    }

    func deletePlan(_ plan: PlanOut) async {
        let success = await session.deletePlan(plan.id)
        if success {
            await MainActor.run {
                // Remove the plan from the list
                self.allPlans.removeAll { $0.id == plan.id }
            }
        }
    }
}

struct TripHistoryCard: View {
    let plan: PlanOut

    var primaryColor: Color {
        Color(hex: plan.activity.colors.primary) ?? .purple
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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                // Activity Icon
                Circle()
                    .fill(primaryColor.opacity(0.2))
                    .frame(width: 50, height: 50)
                    .overlay(
                        Text(activityIcon)
                            .font(.title2)
                    )

                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title)
                        .font(.headline)
                        .lineLimit(1)

                    HStack(spacing: 4) {
                        Image(systemName: plan.status == "completed" ? "checkmark.circle" : "calendar")
                            .font(.caption)

                        // Show completion time for completed trips, otherwise show start time
                        if plan.status == "completed" {
                            if let completedAtStr = plan.completed_at, !completedAtStr.isEmpty {
                                if let completedDate = parseDate(completedAtStr) {
                                    // Show actual completion time
                                    Text("Finished:")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(completedDate, style: .date)
                                        .font(.caption)
                                    Text("at")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(completedDate, style: .time)
                                        .font(.caption)
                                } else {
                                    Text("Parse error")
                                        .font(.caption2)
                                        .foregroundStyle(.red)
                                }
                            } else {
                                Text("No completion time")
                                    .font(.caption2)
                                    .foregroundStyle(.orange)
                            }
                        } else {
                            Text(plan.start_at, style: .date)
                                .font(.caption)

                            Text("•")
                                .foregroundStyle(.secondary)

                            Text(formatDuration(from: plan.start_at, to: plan.eta_at))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Spacer()

                // Status Badge
                Text(plan.status.capitalized)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(statusColor.opacity(0.2))
                    .foregroundStyle(statusColor)
                    .cornerRadius(12)
            }

            // Location (if available)
            if let location = plan.location_text {
                HStack {
                    Image(systemName: "location.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(location)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            // Activity Type
            HStack {
                Image(systemName: "figure.walk")
                    .font(.caption)
                    .foregroundStyle(primaryColor)
                Text(activityName)
                    .font(.caption)
                    .foregroundStyle(primaryColor)
                    .fontWeight(.medium)
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.05), radius: 5, x: 0, y: 2)
    }

    func formatDuration(from start: Date, to end: Date) -> String {
        let interval = end.timeIntervalSince(start)
        let hours = Int(interval) / 3600
        let minutes = Int(interval) % 3600 / 60

        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }

    func parseDate(_ dateString: String) -> Date? {
        // Try ISO8601 format first
        let iso8601Formatter = ISO8601DateFormatter()
        iso8601Formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso8601Formatter.date(from: dateString) {
            return date
        }

        // Try without fractional seconds
        iso8601Formatter.formatOptions = [.withInternetDateTime]
        if let date = iso8601Formatter.date(from: dateString) {
            return date
        }

        // Try custom format for backend timestamps
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        formatter.timeZone = TimeZone(identifier: "UTC")
        if let date = formatter.date(from: dateString) {
            return date
        }

        return nil
    }
}

#Preview {
    HistoryView()
        .environmentObject(Session())
}