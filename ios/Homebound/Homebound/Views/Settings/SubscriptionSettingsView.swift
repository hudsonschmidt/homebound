import SwiftUI
import StoreKit

/// View for managing subscription settings
struct SubscriptionSettingsView: View {
    @EnvironmentObject var session: Session
    @StateObject private var subscriptionManager = SubscriptionManager.shared
    @Environment(\.scenePhase) private var scenePhase
    @State private var showPaywall = false
    @State private var showFeatures = false
    @State private var isLoading = true

    /// Whether the subscription is cancelled (not auto-renewing)
    /// Only applies to premium users - must have a subscription to be "cancelled"
    private var isCancelled: Bool {
        subscriptionManager.subscriptionStatus.isPremium && !subscriptionManager.willAutoRenew
    }

    var body: some View {
        List {
            // Current plan section - tappable to show features (premium only)
            Section {
                if subscriptionManager.subscriptionStatus.isPremium {
                    // Premium users can tap to see their features
                    Button {
                        showFeatures = true
                    } label: {
                        currentPlanCard
                    }
                    .buttonStyle(.plain)
                } else {
                    // Free users see static card (upgrade button below handles action)
                    currentPlanCard
                }
            }

            // Upgrade or manage section
            if subscriptionManager.subscriptionStatus.isPremium {
                Section("Manage Subscription") {
                    Button {
                        openSubscriptionManagement()
                    } label: {
                        HStack {
                            Label("Manage in Settings", systemImage: "gear")
                            Spacer()
                            Image(systemName: "arrow.up.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    // Show trial info, cancelled info, or renewal date
                    if subscriptionManager.isTrialing, let expirationDate = subscriptionManager.expirationDate {
                        HStack {
                            Label(isCancelled ? "Access ends" : "Trial ends", systemImage: isCancelled ? "calendar.badge.exclamationmark" : "clock")
                            Spacer()
                            Text(expirationDate, style: .date)
                                .foregroundStyle(isCancelled ? .red : .orange)
                        }

                        // Only show charging info if trial is NOT cancelled
                        if !isCancelled {
                            if let price = subscriptionManager.currentSubscriptionPrice,
                               let period = subscriptionManager.currentSubscriptionPeriod {
                                HStack {
                                    Label("Then \(price)/\(period)", systemImage: "creditcard")
                                    Spacer()
                                }
                            }
                        }
                    } else if let expirationDate = subscriptionManager.expirationDate {
                        if isCancelled {
                            HStack {
                                Label("Expires", systemImage: "calendar.badge.exclamationmark")
                                Spacer()
                                Text(expirationDate, style: .date)
                                    .foregroundStyle(.orange)
                            }
                        } else {
                            HStack {
                                Label("Renews", systemImage: "calendar")
                                Spacer()
                                Text(expirationDate, style: .date)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            } else {
                Section {
                    Button {
                        showPaywall = true
                    } label: {
                        HStack {
                            Label("Upgrade to Homebound+", systemImage: "star.fill")
                                .foregroundStyle(Color.hbBrand)
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            // Feature limits section
            Section("Your Plan Includes") {
                featureLimitRow(
                    icon: "person.3.fill",
                    title: "Contacts per trip",
                    value: "\(session.featureLimits.contactsPerTrip)"
                )

                featureLimitRow(
                    icon: "bookmark.fill",
                    title: "Saved trip templates",
                    value: session.featureLimits.savedTripsLimit == 0 ? "None" : "\(session.featureLimits.savedTripsLimit)"
                )

                featureLimitRow(
                    icon: "clock.arrow.circlepath",
                    title: "Trip history",
                    value: session.featureLimits.historyDays == nil ? "Unlimited" : "\(session.featureLimits.historyDays!) days"
                )

                featureLimitRow(
                    icon: "chart.bar.fill",
                    title: "Stats visible",
                    value: "\(session.featureLimits.visibleStats) of 8"
                )

                featureLimitRow(
                    icon: "timer",
                    title: "Extensions",
                    value: session.featureLimits.extensions.map { "\($0)m" }.joined(separator: ", ")
                )
            }

            // Restore purchases
            Section {
                Button {
                    Task {
                        await subscriptionManager.restorePurchases()
                        await session.loadFeatureLimits()
                    }
                } label: {
                    HStack {
                        Label("Restore Purchases", systemImage: "arrow.clockwise")
                        Spacer()
                        if subscriptionManager.isLoading {
                            ProgressView()
                        }
                    }
                }
                .disabled(subscriptionManager.isLoading)
            }
        }
        .navigationTitle("Subscription")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showPaywall) {
            PaywallView(feature: nil)
        }
        .sheet(isPresented: $showFeatures) {
            FeaturesOnlyView()
        }
        .task {
            await loadData()
        }
        .refreshable {
            await loadData()
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                // Refresh subscription status when returning to foreground
                // This catches cases where user cancels in Apple Settings app
                refreshOnForeground()
            }
        }
    }

    // MARK: - Current Plan Card

    private var currentPlanCard: some View {
        HStack(spacing: 16) {
            // Left side: Text content
            VStack(alignment: .leading, spacing: 12) {
                // Plan badge row
                HStack {
                    if subscriptionManager.subscriptionStatus.isPremium {
                        if isCancelled {
                            CancelledBadge()
                        } else if subscriptionManager.isTrialing {
                            TrialBadge()
                        } else {
                            PremiumBadge()
                        }
                    } else {
                        Text("FREE")
                            .font(.caption2.bold())
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.secondary.opacity(0.2))
                            .clipShape(Capsule())
                    }
                }

                // Title and subtitle
                VStack(alignment: .leading, spacing: 4) {
                    Text(subscriptionManager.subscriptionStatus.isPremium ? "Homebound+" : "Free Plan")
                        .font(.title2.bold())
                        .foregroundStyle(.primary)

                    if subscriptionManager.subscriptionStatus.isPremium {
                        if subscriptionManager.isTrialing {
                            if isCancelled {
                                Text("Trial cancelled")
                                    .font(.caption)
                                    .foregroundStyle(.red)
                            } else {
                                Text("Free trial active")
                                    .font(.caption)
                                    .foregroundStyle(.orange)
                            }
                        } else if isCancelled {
                            Text("Access until expiration")
                                .font(.caption)
                                .foregroundStyle(.orange)
                        } else {
                            Text("Auto-renews")
                                .font(.caption)
                                .foregroundStyle(.green)
                        }
                    } else {
                        Text("Basic features")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Spacer()

            // Right side: Icon (vertically centered)
            HStack(spacing: 8) {
                if subscriptionManager.subscriptionStatus.isPremium {
                    Image("Logo")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 56, height: 56)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                    // Chevron only for premium (card is tappable)
                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Image(systemName: "person.circle")
                        .font(.system(size: 56))
                        .foregroundStyle(.secondary)
                    // No chevron for free users (card is not tappable)
                }
            }
        }
        .padding()
        .background(Color.hbCardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .listRowInsets(EdgeInsets())
        .listRowBackground(Color.clear)
    }

    // MARK: - Feature Limit Row

    private func featureLimitRow(icon: String, title: String, value: String) -> some View {
        HStack {
            Label(title, systemImage: icon)
            Spacer()
            Text(value)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - Actions

    private func loadData() async {
        isLoading = true
        defer { isLoading = false }

        // Update from StoreKit (source of truth for subscription status)
        await subscriptionManager.updateSubscriptionStatus()

        // Refresh feature limits from backend
        await session.loadFeatureLimits()
    }

    /// Refresh subscription status when returning from background
    /// (e.g., after user cancels subscription in Apple Settings)
    private func refreshOnForeground() {
        Task {
            await subscriptionManager.updateSubscriptionStatus()
        }
    }

    private func openSubscriptionManagement() {
        Task {
            if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
                do {
                    try await AppStore.showManageSubscriptions(in: windowScene)
                } catch {
                    debugLog("[SubscriptionSettings] Failed to open subscription management: \(error)")
                }
            }
        }
    }
}

// MARK: - Features Only View

/// Shows Homebound+ features without subscription options (for already subscribed users)
private struct FeaturesOnlyView: View {
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Hero section
                    VStack(spacing: 16) {
                        HStack(spacing: 12) {
                            Image("Logo")
                                .resizable()
                                .scaledToFit()
                                .frame(width: 48, height: 48)
                                .clipShape(RoundedRectangle(cornerRadius: 10))

                            Text("Homebound+")
                                .font(.title.bold())
                                .foregroundStyle(
                                    LinearGradient(
                                        colors: [Color.hbBrand, Color.hbTeal],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    )
                                )
                        }

                        Text("Your premium features")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 8)

                    // Feature grid
                    VStack(alignment: .leading, spacing: 16) {
                        Text("What's Included")
                            .font(.headline)
                            .padding(.horizontal, 4)

                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                            FeatureCell(icon: "person.2.fill", title: "Group Trips", subtitle: "Travel with friends")
                            FeatureCell(icon: "clock.arrow.circlepath", title: "Unlimited History", subtitle: "Relive every adventure")
                            FeatureCell(icon: "platter.filled.bottom.iphone", title: "Live Activity", subtitle: "& Dynamic Island")
                            FeatureCell(icon: "widget.small.badge.plus", title: "Widgets", subtitle: "Quick trip status")
                            FeatureCell(icon: "map.fill", title: "Trip Map", subtitle: "See all your adventures")
                            FeatureCell(icon: "bookmark.fill", title: "Trip Templates", subtitle: "Start trips in seconds")
                            FeatureCell(icon: "timer", title: "Flexible Extensions", subtitle: "Up to 4 hour extensions")
                            FeatureCell(icon: "square.and.arrow.up", title: "Export Your Data", subtitle: "Download trip history")
                        }

                        // Additional features
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Also included:")
                                .font(.subheadline)
                                .fontWeight(.medium)
                                .foregroundStyle(.secondary)
                                .padding(.top, 8)

                            ForEach([
                                "5 contacts per trip",
                                "8 trip statistics",
                                "3 favorite activities",
                                "Contact groups",
                                "Custom notification messages",
                                "Custom check-in intervals"
                            ], id: \.self) { feature in
                                HStack(spacing: 8) {
                                    Image(systemName: "checkmark")
                                        .font(.caption)
                                        .fontWeight(.bold)
                                        .foregroundStyle(Color.hbBrand)
                                    Text(feature)
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        .padding(.horizontal, 4)
                    }

                    Spacer(minLength: 40)
                }
                .padding()
            }
            .navigationTitle("Your Plan")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

private struct FeatureCell: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Color.hbBrand)
                .frame(width: 36, height: 36)
                .background(Color.hbBrand.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.bold())
                    .lineLimit(1)
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .frame(height: 100)
        .background(Color.hbCardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

#Preview {
    NavigationStack {
        SubscriptionSettingsView()
            .environmentObject(Session.shared)
    }
}
