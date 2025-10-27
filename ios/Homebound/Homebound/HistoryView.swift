import SwiftUI

struct HistoryView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss
    @State private var allPlans: [PlanOut] = []
    @State private var isLoading = true
    @State private var selectedFilter: String = "all"
    @State private var searchText = ""

    let filters = ["all", "completed", "active", "overdue", "cancelled"]

    var filteredPlans: [PlanOut] {
        let filtered = allPlans.filter { plan in
            if selectedFilter != "all" && plan.status != selectedFilter {
                return false
            }
            if !searchText.isEmpty {
                return plan.title.localizedCaseInsensitiveContains(searchText) ||
                       (plan.location_text ?? "").localizedCaseInsensitiveContains(searchText)
            }
            return true
        }
        return filtered.sorted { $0.start_at > $1.start_at }
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
                    ScrollView {
                        VStack(spacing: 0) {
                            // Search Bar
                            HStack {
                                Image(systemName: "magnifyingglass")
                                    .foregroundStyle(.secondary)
                                TextField("Search trips...", text: $searchText)
                                    .textFieldStyle(.plain)
                            }
                            .padding(12)
                            .background(Color(.secondarySystemBackground))
                            .cornerRadius(12)
                            .padding(.horizontal)
                            .padding(.top)

                            // Filter Pills
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 10) {
                                    ForEach(filters, id: \.self) { filter in
                                        FilterPill(
                                            title: filter.capitalized,
                                            isSelected: selectedFilter == filter,
                                            count: countForFilter(filter),
                                            action: { selectedFilter = filter }
                                        )
                                    }
                                }
                                .padding(.horizontal)
                                .padding(.vertical, 10)
                            }

                            // Trip List
                            LazyVStack(spacing: 12) {
                                ForEach(filteredPlans) { plan in
                                    TripHistoryCard(plan: plan)
                                }
                            }
                            .padding(.horizontal)
                            .padding(.bottom, 20)
                        }
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

    func countForFilter(_ filter: String) -> Int {
        if filter == "all" {
            return allPlans.count
        }
        return allPlans.filter { $0.status == filter }.count
    }

    func loadAllPlans() async {
        guard let bearer = session.accessToken else { return }

        isLoading = true
        do {
            // Create URL with proper query parameters
            var urlComponents = URLComponents(url: session.url("/api/v1/plans/recent"), resolvingAgainstBaseURL: false)!
            urlComponents.queryItems = [URLQueryItem(name: "limit", value: "100")]

            let plans: [PlanOut] = try await session.api.get(
                urlComponents.url!,
                bearer: bearer
            )

            await MainActor.run {
                self.allPlans = plans
                self.isLoading = false
            }
        } catch {
            await MainActor.run {
                self.isLoading = false
            }
        }
    }
}

struct TripHistoryCard: View {
    let plan: PlanOut

    var activity: ActivityType {
        ActivityType(rawValue: plan.activity_type) ?? .other
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
                    .fill(activity.primaryColor.opacity(0.2))
                    .frame(width: 50, height: 50)
                    .overlay(
                        Text(activity.icon)
                            .font(.title2)
                    )

                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title)
                        .font(.headline)
                        .lineLimit(1)

                    HStack(spacing: 4) {
                        Image(systemName: "calendar")
                            .font(.caption)
                        Text(plan.start_at, style: .date)
                            .font(.caption)

                        Text("•")
                            .foregroundStyle(.secondary)

                        Text(formatDuration(from: plan.start_at, to: plan.eta_at))
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
                    .foregroundStyle(activity.primaryColor)
                Text(activity.displayName)
                    .font(.caption)
                    .foregroundStyle(activity.primaryColor)
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
}

struct FilterPill: View {
    let title: String
    let isSelected: Bool
    let count: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Text(title)
                    .font(.subheadline)
                    .fontWeight(isSelected ? .semibold : .regular)

                if count > 0 {
                    Text("\(count)")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            Capsule()
                                .fill(isSelected ? Color(.systemBackground) : Color(hex: "#6C63FF") ?? .purple)
                        )
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(isSelected ?
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        ) :
                        LinearGradient(
                            colors: [Color(.tertiarySystemBackground), Color(.tertiarySystemBackground)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
            )
            .foregroundStyle(isSelected ? .white : Color(.label))
        }
    }
}

#Preview {
    HistoryView()
        .environmentObject(Session())
}