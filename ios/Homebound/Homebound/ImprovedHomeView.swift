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
                // Background - adapts to dark mode
                Color(.systemBackground)
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
                // Load user profile to ensure we have the latest data
                await session.loadUserProfile()
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
    @State private var notificationCountdown = ""
    @State private var progress: CGFloat = 0.5
    @State private var isPerformingAction = false
    @State private var showingSafetyTips = true  // Show by default
    @State private var currentSafetyTipIndex = 0

    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var activity: ActivityType {
        ActivityType(rawValue: plan.activity_type) ?? .other
    }

    var body: some View {
        VStack(spacing: 20) {
            // Activity Header
            HStack {
                Circle()
                    .fill(isOverdue ? Color.red.opacity(0.2) : activity.primaryColor.opacity(0.2))
                    .frame(width: 60, height: 60)
                    .overlay(
                        Text(activity.icon)
                            .font(.system(size: 32))
                    )
                    .overlay(
                        isOverdue ?
                        Circle()
                            .stroke(Color.red, lineWidth: 3)
                            .scaleEffect(1.2)
                            .opacity(0.7)
                            .animation(.easeInOut(duration: 1).repeatForever(), value: isOverdue)
                        : nil
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

            // Overdue Warning Section (if overdue)
            if isOverdue {
                VStack(spacing: 12) {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.title)
                            .foregroundStyle(.red)
                        VStack(alignment: .leading, spacing: 4) {
                            Text("YOU ARE OVERDUE")
                                .font(.headline)
                                .foregroundStyle(.red)
                            Text("Check in immediately to avoid alerting contacts")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                    .padding()
                    .background(Color.red.opacity(0.1))
                    .cornerRadius(12)

                    // Notification Countdown
                    if !notificationCountdown.isEmpty {
                        HStack {
                            Image(systemName: "bell.badge.fill")
                                .foregroundStyle(.orange)
                            Text("Notifying contacts in:")
                                .font(.subheadline)
                                .fontWeight(.medium)
                            Spacer()
                            Text(notificationCountdown)
                                .font(.system(size: 20, weight: .bold, design: .monospaced))
                                .foregroundStyle(.orange)
                        }
                        .padding()
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(12)
                    }
                }
            }

            // Progress Ring
            ZStack {
                Circle()
                    .stroke(isOverdue ? Color.red.opacity(0.2) : activity.primaryColor.opacity(0.2), lineWidth: 8)
                    .frame(width: 140, height: 140)

                Circle()
                    .trim(from: 0, to: isOverdue ? 1 : progress)
                    .stroke(
                        isOverdue ?
                        LinearGradient(
                            colors: [.red, .orange],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ) :
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
                .background(isOverdue ? Color.red.opacity(0.1) : activity.primaryColor.opacity(0.1))
                .foregroundStyle(isOverdue ? .red : activity.primaryColor)
                .cornerRadius(20)
            }

            // Action Buttons - Emphasize "I'm Safe" when overdue
            HStack(spacing: 12) {
                if !isOverdue {
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
                }

                ActionButton(
                    title: "I'm Safe",
                    icon: "house.fill",
                    color: isOverdue ? .red : .green,
                    isLoading: isPerformingAction,
                    isEmergency: isOverdue,
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

            // Encouragement Message or Urgent Message
            Text(isOverdue ? "⚠️ Please check in immediately to avoid worrying your contacts!" :
                 activity.encouragementMessages.randomElement() ?? "Stay safe!")
                .font(.footnote)
                .italic()
                .foregroundStyle(isOverdue ? .red : .secondary)
                .padding(.horizontal)

            // Safety Tips Section
            VStack(alignment: .leading, spacing: 8) {
                Button(action: { withAnimation(.easeInOut(duration: 0.3)) { showingSafetyTips.toggle() } }) {
                    HStack {
                        Image(systemName: "shield.lefthalf.filled")
                            .font(.caption)
                        Text("Safety Tips")
                            .font(.caption)
                            .fontWeight(.semibold)
                        Spacer()
                        Image(systemName: showingSafetyTips ? "chevron.up" : "chevron.down")
                            .font(.caption2)
                    }
                    .foregroundStyle(isOverdue ? .red : activity.primaryColor)
                    .padding(.horizontal, 4)
                }

                if showingSafetyTips {
                    // Display tips in a 2-column grid for better space usage
                    LazyVGrid(columns: [
                        GridItem(.flexible(), spacing: 8),
                        GridItem(.flexible(), spacing: 8)
                    ], spacing: 8) {
                        ForEach(activity.safetyTips, id: \.self) { tip in
                            HStack(alignment: .top, spacing: 4) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.caption2)
                                    .foregroundStyle(isOverdue ? .red.opacity(0.7) : activity.primaryColor.opacity(0.7))
                                Text(tip)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                                    .minimumScaleFactor(0.9)
                                Spacer(minLength: 0)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(isOverdue ? Color.red.opacity(0.05) : activity.primaryColor.opacity(0.05))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(isOverdue ? Color.red.opacity(0.1) : activity.primaryColor.opacity(0.1), lineWidth: 1)
                    )
                }
            }
            .padding(.horizontal)
            .transition(.asymmetric(insertion: .scale.combined(with: .opacity), removal: .scale.combined(with: .opacity)))
        }
        .padding(24)
        .background(
            RoundedRectangle(cornerRadius: 24)
                .fill(Color(.secondarySystemBackground))
                .overlay(
                    isOverdue ?
                    RoundedRectangle(cornerRadius: 24)
                        .stroke(Color.red.opacity(0.3), lineWidth: 2)
                    : nil
                )
                .shadow(color: isOverdue ? .red.opacity(0.2) : activity.primaryColor.opacity(0.15),
                        radius: 20, x: 0, y: 10)
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
            let seconds = Int(overdueInterval) % 60
            timeRemaining = String(format: "%02d:%02d:%02d", hours, minutes, seconds)

            // Calculate time until notification (grace period after ETA)
            let graceEndTime = eta.addingTimeInterval(Double(plan.grace_minutes * 60))
            let timeUntilNotification = graceEndTime.timeIntervalSince(now)

            if timeUntilNotification > 0 {
                let notifyHours = Int(timeUntilNotification) / 3600
                let notifyMinutes = Int(timeUntilNotification) % 3600 / 60
                let notifySeconds = Int(timeUntilNotification) % 60
                notificationCountdown = String(format: "%02d:%02d:%02d", notifyHours, notifyMinutes, notifySeconds)
            } else {
                notificationCountdown = "NOTIFIED"
            }
        } else {
            isOverdue = false
            notificationCountdown = ""
            let hours = Int(interval) / 3600
            let minutes = Int(interval) % 3600 / 60
            let seconds = Int(interval) % 60
            timeRemaining = String(format: "%02d:%02d:%02d", hours, minutes, seconds)
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
                .fill(Color(.tertiarySystemBackground))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(activity.primaryColor.opacity(0.3), lineWidth: 1)
        )
    }
}

// MARK: - Action Button
struct ActionButton: View {
    let title: String
    let icon: String
    let color: Color
    var isLoading: Bool = false
    var isEmergency: Bool = false
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
                    .overlay(
                        isEmergency && !isLoading ?
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.white, lineWidth: 2)
                            .scaleEffect(1.05)
                            .opacity(0.8)
                            .animation(.easeInOut(duration: 0.8).repeatForever(), value: isEmergency)
                        : nil
                    )
            )
        }
        .disabled(isLoading)
    }
}

// ProfileView is now in its own file (ProfileView.swift)