import SwiftUI
import Combine

// MARK: - Improved Home Dashboard with Better UI & Colors
struct ImprovedHomeView: View {
    @EnvironmentObject var session: Session
    @State private var showingCreatePlan = false
    @State private var showingProfile = false
    @State private var activePlan: PlanOut?
    @State private var recentPlans: [PlanOut] = []
    @State private var timeline: [TimelineEvent] = []
    @State private var greeting = "Good morning"

    var body: some View {
        NavigationStack {
            ZStack {
                // Background Gradient
                LinearGradient(
                    colors: [
                        Color(hex: "#F0F2F5") ?? .gray,
                        Color(hex: "#FFFFFF") ?? .white
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Header Section
                        HeaderSection(greeting: greeting, showingProfile: $showingProfile)
                            .padding(.horizontal)
                            .padding(.top, 8)

                        // Active Plan Card (if exists)
                        if let plan = activePlan {
                            ImprovedActivePlanCard(plan: plan, timeline: $timeline)
                                .transition(.asymmetric(
                                    insertion: .move(edge: .top).combined(with: .opacity),
                                    removal: .scale.combined(with: .opacity)
                                ))
                        }

                        // Quick Actions Grid
                        QuickActionsGrid(
                            hasActivePlan: activePlan != nil,
                            showingCreatePlan: $showingCreatePlan,
                            onHomeSafe: { Task { await checkoutActive() } }
                        )
                        .padding(.horizontal)

                        // Statistics Cards
                        StatsSection()
                            .padding(.horizontal)

                        // Recent Activities
                        if !recentPlans.isEmpty {
                            RecentActivitiesSection(plans: recentPlans)
                        }
                    }
                    .padding(.bottom, 100)
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showingCreatePlan) {
                CreatePlanView()
            }
            .sheet(isPresented: $showingProfile) {
                ProfileView()
            }
            .task {
                updateGreeting()
                await loadActivePlan()
            }
            .refreshable {
                await loadActivePlan()
            }
        }
    }

    func updateGreeting() {
        let hour = Calendar.current.component(.hour, from: Date())
        greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
    }

    func loadActivePlan() async {
        // TODO: Fetch active plan from API
    }

    func checkoutActive() async {
        guard let plan = activePlan else { return }
        // TODO: Call checkout endpoint
    }
}

// MARK: - Header Section
struct HeaderSection: View {
    let greeting: String
    @Binding var showingProfile: Bool
    @EnvironmentObject var session: Session

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(greeting)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                Text("Stay safe on your adventures")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button(action: { showingProfile = true }) {
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
                        Image(systemName: "person.fill")
                            .foregroundStyle(.white)
                            .font(.system(size: 20))
                    )
            }
        }
    }
}

// MARK: - Improved Active Plan Card
struct ImprovedActivePlanCard: View {
    let plan: PlanOut
    @Binding var timeline: [TimelineEvent]
    @State private var timeRemaining = ""
    @State private var isOverdue = false
    @State private var progress: CGFloat = 0.5

    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var activity: ActivityType {
        ActivityType(rawValue: plan.activity_type) ?? .other
    }

    var body: some View {
        VStack(spacing: 20) {
            // Activity Header
            HStack {
                Circle()
                    .fill(activity.primaryColor.opacity(0.2))
                    .frame(width: 60, height: 60)
                    .overlay(
                        Text(activity.icon)
                            .font(.system(size: 32))
                    )

                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.title)
                        .font(.headline)
                        .lineLimit(1)
                    Text(activity.displayName)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Image(systemName: isOverdue ? "exclamationmark.triangle.fill" : "clock.fill")
                        .font(.caption)
                        .foregroundStyle(isOverdue ? .red : activity.primaryColor)
                    Text(plan.status.uppercased())
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .foregroundStyle(isOverdue ? .red : activity.primaryColor)
                }
            }

            // Progress Ring
            ZStack {
                Circle()
                    .stroke(activity.primaryColor.opacity(0.2), lineWidth: 8)
                    .frame(width: 140, height: 140)

                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(
                        LinearGradient(
                            colors: [activity.primaryColor, activity.accentColor],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        style: StrokeStyle(lineWidth: 8, lineCap: .round)
                    )
                    .frame(width: 140, height: 140)
                    .rotationEffect(.degrees(-90))
                    .animation(.easeInOut(duration: 0.5), value: progress)

                VStack(spacing: 4) {
                    Text(timeRemaining)
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundStyle(isOverdue ? .red : activity.primaryColor)
                    Text(isOverdue ? "OVERDUE" : "REMAINING")
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                }
            }

            // Location Badge
            if let location = plan.location_text {
                HStack {
                    Image(systemName: "location.fill")
                        .font(.caption)
                    Text(location)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(activity.primaryColor.opacity(0.1))
                .foregroundStyle(activity.primaryColor)
                .cornerRadius(20)
            }

            // Action Buttons
            HStack(spacing: 12) {
                ActionButton(
                    title: "Check In",
                    icon: "checkmark.circle.fill",
                    color: activity.primaryColor,
                    action: { Task { await performCheckin() } }
                )

                ActionButton(
                    title: "Extend",
                    icon: "clock.badge.plus",
                    color: .orange,
                    action: { Task { await extendTrip() } }
                )

                ActionButton(
                    title: "SOS",
                    icon: "exclamationmark.triangle.fill",
                    color: .red,
                    action: { }
                )
            }

            // Encouragement Message
            Text(activity.encouragementMessages.randomElement() ?? "Stay safe!")
                .font(.footnote)
                .italic()
                .foregroundStyle(.secondary)
                .padding(.horizontal)
        }
        .padding(24)
        .background(
            RoundedRectangle(cornerRadius: 24)
                .fill(.white)
                .shadow(color: activity.primaryColor.opacity(0.15), radius: 20, x: 0, y: 10)
        )
        .padding(.horizontal)
        .onReceive(timer) { _ in
            updateTimer()
        }
    }

    func updateTimer() {
        let now = Date()
        let eta = plan.eta_at
        let start = plan.start_at
        let totalDuration = eta.timeIntervalSince(start)
        let elapsed = now.timeIntervalSince(start)
        progress = min(max(elapsed / totalDuration, 0), 1)

        let interval = eta.timeIntervalSince(now)
        if interval < 0 {
            isOverdue = true
            let overdueInterval = abs(interval)
            let hours = Int(overdueInterval) / 3600
            let minutes = Int(overdueInterval) % 3600 / 60
            timeRemaining = String(format: "%02d:%02d", hours, minutes)
        } else {
            isOverdue = false
            let hours = Int(interval) / 3600
            let minutes = Int(interval) % 3600 / 60
            timeRemaining = String(format: "%02d:%02d", hours, minutes)
        }
    }

    func performCheckin() async {
        // TODO: Implement
    }

    func extendTrip() async {
        // TODO: Implement
    }
}

// MARK: - Quick Actions Grid
struct QuickActionsGrid: View {
    let hasActivePlan: Bool
    @Binding var showingCreatePlan: Bool
    let onHomeSafe: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            QuickActionCard(
                icon: "plus.circle.fill",
                title: "New Trip",
                subtitle: "Start adventure",
                gradient: [Color(hex: "#667EEA") ?? .blue, Color(hex: "#764BA2") ?? .purple],
                action: { showingCreatePlan = true }
            )

            if hasActivePlan {
                QuickActionCard(
                    icon: "house.fill",
                    title: "I'm Safe",
                    subtitle: "End trip",
                    gradient: [Color(hex: "#11998E") ?? .green, Color(hex: "#38EF7D") ?? .green],
                    action: onHomeSafe
                )
            } else {
                QuickActionCard(
                    icon: "clock.arrow.circlepath",
                    title: "History",
                    subtitle: "Past trips",
                    gradient: [Color(hex: "#FC466B") ?? .pink, Color(hex: "#3F5EFB") ?? .blue],
                    action: { }
                )
            }
        }
    }
}

// MARK: - Quick Action Card
struct QuickActionCard: View {
    let icon: String
    let title: String
    let subtitle: String
    let gradient: [Color]
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(
                        Circle()
                            .fill(.white.opacity(0.2))
                    )

                Spacer()

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.white)
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .frame(height: 120)
            .background(
                LinearGradient(
                    colors: gradient,
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .cornerRadius(20)
        }
    }
}

// MARK: - Stats Section
struct StatsSection: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your Stats")
                .font(.headline)

            HStack(spacing: 12) {
                ImprovedStatCard(
                    value: "28",
                    label: "Total Trips",
                    icon: "map.fill",
                    color: Color(hex: "#6C63FF") ?? .purple
                )
                ImprovedStatCard(
                    value: "100%",
                    label: "Safe Returns",
                    icon: "checkmark.shield.fill",
                    color: Color(hex: "#4ECDC4") ?? .teal
                )
                ImprovedStatCard(
                    value: "7",
                    label: "This Week",
                    icon: "calendar.badge.clock",
                    color: Color(hex: "#FF6B6B") ?? .red
                )
            }
        }
    }
}

// MARK: - Improved Stat Card
struct ImprovedStatCard: View {
    let value: String
    let label: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(color)

            Text(value)
                .font(.title3)
                .fontWeight(.bold)

            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(color.opacity(0.1))
        )
    }
}

// MARK: - Recent Activities Section
struct RecentActivitiesSection: View {
    let plans: [PlanOut]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Recent Activities")
                    .font(.headline)
                Spacer()
                Button("View All") { }
                    .font(.caption)
                    .foregroundStyle(.blue)
            }
            .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(plans.prefix(5)) { plan in
                        RecentActivityCard(plan: plan)
                    }
                }
                .padding(.horizontal)
            }
        }
    }
}

// MARK: - Recent Activity Card
struct RecentActivityCard: View {
    let plan: PlanOut

    var activity: ActivityType {
        ActivityType(rawValue: plan.activity_type) ?? .other
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(activity.icon)
                    .font(.title2)
                Spacer()
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.caption)
            }

            Text(plan.title)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)

            Text(plan.eta_at, style: .relative)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(width: 140)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(activity.primaryColor.opacity(0.1))
        )
    }
}

// MARK: - Action Button
struct ActionButton: View {
    let title: String
    let icon: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.title3)
                Text(title)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(color)
            )
        }
    }
}

// MARK: - Profile View
struct ProfileView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var session: Session

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 60, height: 60)
                            .overlay(
                                Image(systemName: "person.fill")
                                    .foregroundStyle(.white)
                                    .font(.title2)
                            )

                        VStack(alignment: .leading) {
                            Text("Adventure Enthusiast")
                                .font(.headline)
                            Text("Member since 2024")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.leading, 8)
                    }
                    .padding(.vertical, 8)
                }

                Section("Settings") {
                    Label("Emergency Contacts", systemImage: "person.2.fill")
                    Label("Notification Preferences", systemImage: "bell.fill")
                    Label("Privacy & Security", systemImage: "lock.fill")
                }

                Section("Support") {
                    Label("Help Center", systemImage: "questionmark.circle.fill")
                    Label("Contact Us", systemImage: "envelope.fill")
                    Label("About", systemImage: "info.circle.fill")
                }

                Section {
                    Button("Sign Out") {
                        session.signOut()
                        dismiss()
                    }
                    .foregroundStyle(.red)
                }
            }
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}