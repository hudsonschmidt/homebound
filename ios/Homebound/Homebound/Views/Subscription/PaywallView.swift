import SwiftUI
import StoreKit

/// Paywall view for upgrading to Homebound+
struct PaywallView: View {
    @EnvironmentObject var session: Session
    @StateObject private var subscriptionManager = SubscriptionManager.shared
    @Environment(\.dismiss) var dismiss

    /// The feature that triggered the paywall (for contextual messaging)
    var feature: PremiumFeature? = nil

    @State private var selectedProduct: Product?
    @State private var isEligibleForTrial: Bool = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Hero section
                    heroSection

                    // Feature that triggered paywall (if any)
                    if let feature = feature {
                        triggeredFeatureCard(feature)
                    }

                    // Feature highlights
                    featureHighlights

                    // Pricing options
                    pricingOptions

                    // Subscribe button
                    subscribeButton

                    // Restore purchases
                    Button("Restore Purchases") {
                        Task {
                            await subscriptionManager.restorePurchases()
                            if subscriptionManager.subscriptionStatus.isPremium {
                                // Reload feature limits after successful restore
                                await session.loadFeatureLimits()
                                dismiss()
                            }
                        }
                    }
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                    // Legal text
                    legalText
                }
                .padding()
            }
            .navigationTitle("Homebound+")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            .overlay {
                if subscriptionManager.isLoading {
                    loadingOverlay
                }
            }
            .alert("Error", isPresented: .constant(subscriptionManager.purchaseError != nil)) {
                Button("OK") { subscriptionManager.purchaseError = nil }
            } message: {
                Text(subscriptionManager.purchaseError ?? "")
            }
            .task {
                // Load products when paywall appears
                if subscriptionManager.products.isEmpty {
                    await subscriptionManager.loadProducts()
                }
                // Pre-select yearly (better value)
                if selectedProduct == nil {
                    selectedProduct = subscriptionManager.yearlyProduct ?? subscriptionManager.monthlyProduct
                }
                // Check trial eligibility for selected product
                await checkTrialEligibility()
            }
            .onChange(of: selectedProduct) { _, _ in
                Task {
                    await checkTrialEligibility()
                }
            }
        }
    }

    // MARK: - Hero Section

    private var heroSection: some View {
        VStack(spacing: 16) {
            // Logo and title
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

            Text("Unlock the full adventure experience")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    // MARK: - Triggered Feature Card

    private func triggeredFeatureCard(_ feature: PremiumFeature) -> some View {
        HStack(spacing: 16) {
            Image(systemName: feature.icon)
                .font(.title2)
                .foregroundStyle(Color.hbBrand)
                .frame(width: 44, height: 44)
                .background(Color.hbBrand.opacity(0.1))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text("Unlock \(feature.rawValue)")
                    .font(.headline)
                Text(feature.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding()
        .background(Color.hbCardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    // MARK: - Feature Highlights

    private var featureHighlights: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Everything in Plus")
                .font(.headline)
                .padding(.horizontal, 4)

            // Premium feature grid
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                PaywallFeatureRow(icon: "person.2.fill", title: "Group Trips", subtitle: "Travel with friends")
                PaywallFeatureRow(icon: "clock.arrow.circlepath", title: "Unlimited History", subtitle: "Relive every adventure")
                PaywallFeatureRow(icon: "platter.filled.bottom.iphone", title: "Live Activity", subtitle: "& Dynamic Island")
                PaywallFeatureRow(icon: "map.fill", title: "Trip Map", subtitle: "See all your adventures")
                PaywallFeatureRow(icon: "bookmark.fill", title: "Trip Templates", subtitle: "Start trips in seconds")
                PaywallFeatureRow(icon: "text.bubble.fill", title: "Custom Messages", subtitle: "Personalize notifications")
            }

            // Additional features bullet list
            VStack(alignment: .leading, spacing: 8) {
                Text("Also included:")
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)

                ForEach(additionalFeatures, id: \.self) { feature in
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
    }

    private var additionalFeatures: [String] {
        [
            "5 contacts per trip (vs 2 free)",
            "8 trip statistics (vs 2 free)",
            "Pin 3 favorite activities",
            "Sort contacts by group",
            "Custom check-in intervals"
        ]
    }

    // MARK: - Pricing Options

    private var pricingOptions: some View {
        VStack(spacing: 12) {
            if subscriptionManager.products.isEmpty && !subscriptionManager.isLoading {
                // No products loaded - show error state
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.title)
                        .foregroundStyle(.orange)
                    Text("Unable to load subscription options")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Button("Retry") {
                        Task {
                            await subscriptionManager.loadProducts()
                        }
                    }
                    .font(.subheadline.bold())
                    .foregroundStyle(Color.hbBrand)
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.hbCardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            } else if subscriptionManager.isLoading {
                ProgressView("Loading options...")
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                ForEach(subscriptionManager.products, id: \.id) { product in
                    PricingCard(
                        product: product,
                        isSelected: selectedProduct?.id == product.id,
                        isTrialEligible: selectedProduct?.id == product.id ? isEligibleForTrial : false,
                        savingsPercentage: product.id == SubscriptionProduct.yearlyPlus.rawValue
                            ? subscriptionManager.yearlySavingsPercentage
                            : nil,
                        monthlyPrice: subscriptionManager.formattedMonthlyPrice(for: product)
                    ) {
                        selectedProduct = product
                    }
                }
            }
        }
    }

    // MARK: - Trial Eligibility

    /// Check if user is eligible for the free trial on the selected product
    private func checkTrialEligibility() async {
        guard let product = selectedProduct,
              let subscription = product.subscription else {
            isEligibleForTrial = false
            return
        }

        // Check if product has a trial offer
        guard let intro = subscription.introductoryOffer,
              intro.paymentMode == .freeTrial else {
            isEligibleForTrial = false
            return
        }

        // Check if user is actually eligible (hasn't used trial before)
        isEligibleForTrial = await subscription.isEligibleForIntroOffer
    }

    // MARK: - Subscribe Button

    /// Whether to show the trial button (product has trial AND user is eligible)
    private var selectedProductHasTrial: Bool {
        isEligibleForTrial
    }

    /// Get the trial duration string for the selected product (e.g., "7-Day")
    private var trialDurationString: String? {
        guard isEligibleForTrial,
              let product = selectedProduct,
              let subscription = product.subscription,
              let intro = subscription.introductoryOffer,
              intro.paymentMode == .freeTrial else {
            return nil
        }

        let period = intro.period
        let value = period.value

        switch period.unit {
        case .day:
            return "\(value)-Day"
        case .week:
            return value == 1 ? "1-Week" : "\(value)-Week"
        case .month:
            return value == 1 ? "1-Month" : "\(value)-Month"
        case .year:
            return value == 1 ? "1-Year" : "\(value)-Year"
        @unknown default:
            return nil
        }
    }

    private var subscribeButton: some View {
        Button {
            guard let product = selectedProduct else { return }
            Task {
                let success = await subscriptionManager.purchase(product)
                if success {
                    await session.loadFeatureLimits()
                    dismiss()
                }
            }
        } label: {
            HStack {
                if selectedProductHasTrial {
                    if let duration = trialDurationString {
                        Text("Start \(duration) Free Trial")
                    } else {
                        Text("Start Free Trial")
                    }
                } else {
                    Text("Subscribe Now")
                    if let product = selectedProduct {
                        Text("- \(product.displayPrice)/\(product.id == SubscriptionProduct.yearlyPlus.rawValue ? "year" : "month")")
                    }
                }
            }
        }
        .buttonStyle(HBPrimaryButtonStyle())
        .disabled(selectedProduct == nil || subscriptionManager.isLoading)
    }

    // MARK: - Legal Text

    private var legalText: some View {
        VStack(spacing: 8) {
            Text("Subscriptions automatically renew unless cancelled at least 24 hours before the end of the current period. Manage subscriptions in Settings.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Link("Terms of Service", destination: URL(string: "https://www.homeboundapp.com/termsofservice/")!)
                Link("Privacy Policy", destination: URL(string: "https://www.homeboundapp.com/privacypolicy/")!)
                Link("EULA", destination: URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!)
            }
            .font(.caption2)
        }
        .padding(.top, 8)
    }

    // MARK: - Loading Overlay

    private var loadingOverlay: some View {
        ZStack {
            Color.black.opacity(0.3)
                .ignoresSafeArea()

            VStack(spacing: 16) {
                ProgressView()
                    .scaleEffect(1.5)
                Text("Processing...")
                    .font(.headline)
            }
            .padding(32)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }
}

// MARK: - Paywall Feature Row

private struct PaywallFeatureRow: View {
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

// MARK: - Pricing Card

private struct PricingCard: View {
    let product: Product
    let isSelected: Bool
    /// Whether the user is eligible for the free trial (hasn't used it before)
    let isTrialEligible: Bool
    let savingsPercentage: Int?
    let monthlyPrice: String?
    let onSelect: () -> Void

    /// Get the trial period description from the product's introductory offer
    /// Only returns a value if the product has a trial AND user is eligible
    private var trialDescription: String? {
        // Only show trial info if user is actually eligible
        guard isTrialEligible else { return nil }

        guard let subscription = product.subscription,
              let intro = subscription.introductoryOffer,
              intro.paymentMode == .freeTrial else {
            return nil
        }

        let period = intro.period
        let value = period.value

        switch period.unit {
        case .day:
            return "\(value)-day free trial"
        case .week:
            return value == 1 ? "1-week free trial" : "\(value)-week free trial"
        case .month:
            return value == 1 ? "1-month free trial" : "\(value)-month free trial"
        case .year:
            return value == 1 ? "1-year free trial" : "\(value)-year free trial"
        @unknown default:
            return "Free trial"
        }
    }

    var body: some View {
        Button(action: onSelect) {
            HStack {
                // Selection indicator
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(isSelected ? Color.hbBrand : .secondary)

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(product.id == SubscriptionProduct.yearlyPlus.rawValue ? "Yearly" : "Monthly")
                            .font(.headline)

                        if let savings = savingsPercentage, savings > 0 {
                            Text("Save \(savings)%")
                                .font(.caption.bold())
                                .foregroundStyle(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Color.hbBrand)
                                .clipShape(Capsule())
                        }
                    }

                    if let trialDescription = trialDescription {
                        HStack(spacing: 4) {
                            Text(trialDescription)
                                .font(.caption.bold())
                                .foregroundStyle(.green)
                            if let monthlyPrice = monthlyPrice {
                                Text("•")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("\(monthlyPrice)/mo")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    } else if let monthlyPrice = monthlyPrice {
                        Text("\(monthlyPrice)/month")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Text(product.displayPrice)
                        .font(.title3.bold())
                    if trialDescription != nil {
                        Text("after trial")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(Color.hbCardBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(isSelected ? Color.hbBrand : Color.clear, lineWidth: 2)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Premium Badge View

/// Small badge to indicate premium features throughout the app
struct PremiumBadge: View {
    var body: some View {
        HStack(spacing: 4) {
            Image("Logo")
                .resizable()
                .scaledToFit()
                .frame(width: 12, height: 12)
            Text("PLUS")
        }
        .font(.caption2.bold())
        .foregroundStyle(.white)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            LinearGradient(
                colors: [Color.hbBrand, Color.hbTeal],
                startPoint: .leading,
                endPoint: .trailing
            )
        )
        .clipShape(Capsule())
    }
}

/// Badge to indicate trial subscription status
struct TrialBadge: View {
    var body: some View {
        Text("TRIAL")
            .font(.caption2.bold())
            .foregroundStyle(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color.orange)
            .clipShape(Capsule())
    }
}

/// Badge to indicate cancelled subscription (still has access until expiration)
struct CancelledBadge: View {
    var body: some View {
        Text("EXPIRES")
            .font(.caption2.bold())
            .foregroundStyle(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color.red.opacity(0.8))
            .clipShape(Capsule())
    }
}

// MARK: - Locked Feature Overlay

/// Overlay to show when a premium feature is locked
struct LockedFeatureOverlay: View {
    let feature: PremiumFeature
    @State private var showPaywall = false

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.largeTitle)
                .foregroundStyle(.secondary)

            Text("Homebound+ Feature")
                .font(.headline)

            Text(feature.description)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button("Upgrade") {
                showPaywall = true
            }
            .font(.subheadline.bold())
            .foregroundStyle(.white)
            .padding(.horizontal, 24)
            .padding(.vertical, 10)
            .background(Color.hbBrand)
            .clipShape(Capsule())
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.ultraThinMaterial)
        .sheet(isPresented: $showPaywall) {
            PaywallView(feature: feature)
        }
    }
}

// MARK: - View Extension for Premium Gating

extension View {
    /// Show paywall when tapping if feature is not available
    func premiumGated(
        feature: PremiumFeature,
        session: Session,
        showPaywall: Binding<Bool>
    ) -> some View {
        self.onTapGesture {
            if !session.canUse(feature: feature) {
                showPaywall.wrappedValue = true
            }
        }
    }
}

#Preview {
    PaywallView(feature: .groupTrips)
        .environmentObject(Session.shared)
}
