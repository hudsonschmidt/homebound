import SwiftUI
import StoreKit

/// View for managing subscription settings
struct SubscriptionSettingsView: View {
    @EnvironmentObject var session: Session
    @StateObject private var subscriptionManager = SubscriptionManager.shared
    @State private var subscriptionStatus: SubscriptionStatusResponse?
    @State private var showPaywall = false
    @State private var isLoading = true

    var body: some View {
        List {
            // Current plan section
            Section {
                currentPlanCard
            }

            // Upgrade or manage section
            if subscriptionManager.subscriptionStatus.isPremium {
                Section("Manage Subscription") {
                    Button {
                        openSubscriptionManagement()
                    } label: {
                        HStack {
                            Label("Manage on App Store", systemImage: "gear")
                            Spacer()
                            Image(systemName: "arrow.up.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    if let expirationDate = subscriptionManager.expirationDate {
                        HStack {
                            Label("Renews", systemImage: "calendar")
                            Spacer()
                            Text(expirationDate, style: .date)
                                .foregroundStyle(.secondary)
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
        .task {
            await loadData()
        }
        .refreshable {
            await loadData()
        }
    }

    // MARK: - Current Plan Card

    private var currentPlanCard: some View {
        VStack(spacing: 16) {
            // Plan badge
            HStack {
                if subscriptionManager.subscriptionStatus.isPremium {
                    PremiumBadge()
                } else {
                    Text("FREE")
                        .font(.caption2.bold())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.2))
                        .clipShape(Capsule())
                }

                Spacer()

                if subscriptionManager.isTrialing {
                    Text("Trial")
                        .font(.caption.bold())
                        .foregroundStyle(.orange)
                }
            }

            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(subscriptionManager.subscriptionStatus.isPremium ? "Homebound+" : "Free Plan")
                        .font(.title2.bold())

                    if subscriptionManager.subscriptionStatus.isPremium {
                        if let status = subscriptionStatus {
                            Text(status.autoRenew ? "Auto-renews" : "Expires soon")
                                .font(.caption)
                                .foregroundStyle(status.autoRenew ? .green : .orange)
                        }
                    } else {
                        Text("Basic features")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                Image(systemName: subscriptionManager.subscriptionStatus.isPremium ? "star.circle.fill" : "person.circle")
                    .font(.system(size: 44))
                    .foregroundStyle(subscriptionManager.subscriptionStatus.isPremium ? Color.hbBrand : .secondary)
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

        // Load subscription status from backend
        subscriptionStatus = await session.loadSubscriptionStatus()

        // Also update from StoreKit
        await subscriptionManager.updateSubscriptionStatus()

        // Refresh feature limits
        await session.loadFeatureLimits()
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

#Preview {
    NavigationStack {
        SubscriptionSettingsView()
            .environmentObject(Session.shared)
    }
}
