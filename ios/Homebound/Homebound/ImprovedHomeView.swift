import SwiftUI
import Combine

// MARK: - Improved Home Dashboard with Better UI & Colors
struct ImprovedHomeView: View {
    @EnvironmentObject var session: Session
    @State private var showingCreatePlan = false
    @State private var showingProfile = false
    @State private var showingHistory = false
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

                        // Active Plan Card (if exists) - Takes up significant space
                        if let plan = session.activePlan {
                            ImprovedActivePlanCard(plan: plan, timeline: $timeline)
                                .frame(minHeight: UIScreen.main.bounds.height * 0.5)
                                .transition(.asymmetric(
                                    insertion: .move(edge: .top).combined(with: .opacity),
                                    removal: .scale.combined(with: .opacity)
                                ))
                                .animation(.spring(response: 0.5, dampingFraction: 0.8), value: session.activePlan)
                        }

                        // Quick Actions Grid
                        QuickActionsGrid(
                            hasActivePlan: session.activePlan != nil,
                            showingCreatePlan: $showingCreatePlan,
                            showingHistory: $showingHistory,
                            onHomeSafe: { Task { await session.completePlan() } }
                        )
                        .padding(.horizontal)

                        // Recent Activities (only show if no active plan)
                        if session.activePlan == nil && !recentPlans.isEmpty {
                            RecentActivitiesSection(plans: recentPlans)
                        }
                    }
                    .padding(.bottom, 100)
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showingCreatePlan) {
                CreatePlanView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingProfile) {
                ProfileView()
                    .environmentObject(session)
            }
            .sheet(isPresented: $showingHistory) {
                HistoryView()
                    .environmentObject(session)
            }
            .task {
                updateGreeting()
                await session.loadActivePlan()
            }
            .refreshable {
                await session.loadActivePlan()
            }
        }
    }

    func updateGreeting() {
        let hour = Calendar.current.component(.hour, from: Date())
        greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"
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
                Text("\(greeting)\(session.userName != nil ? ", \(session.userName!)" : "")")
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
    @EnvironmentObject var session: Session
    @State private var timeRemaining = ""
    @State private var isOverdue = false
    @State private var progress: CGFloat = 0.5
    @State private var isPerformingAction = false

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
                    isLoading: isPerformingAction,
                    action: {
                        Task {
                            isPerformingAction = true
                            _ = await session.checkIn()
                            isPerformingAction = false
                        }
                    }
                )

                ActionButton(
                    title: "I'm Safe",
                    icon: "house.fill",
                    color: .green,
                    isLoading: isPerformingAction,
                    action: {
                        Task {
                            isPerformingAction = true
                            _ = await session.completePlan()
                            isPerformingAction = false
                        }
                    }
                )

                ActionButton(
                    title: "Extend",
                    icon: "plus.circle.fill",
                    color: .orange,
                    isLoading: isPerformingAction,
                    action: {
                        Task {
                            isPerformingAction = true
                            _ = await session.extendPlan()
                            isPerformingAction = false
                        }
                    }
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

}

// MARK: - Quick Actions Grid
struct QuickActionsGrid: View {
    let hasActivePlan: Bool
    @Binding var showingCreatePlan: Bool
    @Binding var showingHistory: Bool
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
                    action: { showingHistory = true }
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
    var isLoading: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                if isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        .scaleEffect(0.8)
                } else {
                    Image(systemName: icon)
                        .font(.title3)
                }
                Text(title)
                    .font(.caption2)
                    .fontWeight(.medium)
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isLoading ? color.opacity(0.7) : color)
            )
        }
        .disabled(isLoading)
    }
}

// ProfileView is now in its own file (ProfileView.swift)