import StoreKit
import Foundation
import Combine

/// Product identifiers for App Store Connect
///
/// Reference Names (for App Store Connect display):
/// - "Homebound+ Monthly"
/// - "Homebound+ Yearly"
enum SubscriptionProduct: String, CaseIterable {
    case monthlyPlus = "com.homeboundapp.homebound.plus.monthly"
    case yearlyPlus = "com.homeboundapp.homebound.plus.yearly"

    var displayName: String {
        switch self {
        case .monthlyPlus: return "Monthly"
        case .yearlyPlus: return "Yearly"
        }
    }

    var period: String {
        switch self {
        case .monthlyPlus: return "month"
        case .yearlyPlus: return "year"
        }
    }
}

/// Manages StoreKit 2 purchases and subscription status
@MainActor
final class SubscriptionManager: ObservableObject {
    static let shared = SubscriptionManager()

    @Published private(set) var products: [Product] = []
    @Published private(set) var purchasedProductIDs: Set<String> = []
    @Published private(set) var subscriptionStatus: SubscriptionStatus = .free
    @Published private(set) var isLoading = false
    @Published var purchaseError: String?

    /// The current subscription expiration date, if any
    @Published private(set) var expirationDate: Date?

    /// Whether the user is in a trial period
    @Published private(set) var isTrialing = false

    /// Whether the subscription will auto-renew (false = cancelled)
    @Published private(set) var willAutoRenew: Bool = true

    /// Whether the subscription is in a billing grace period
    @Published private(set) var isInGracePeriod = false

    /// Whether the last backend sync succeeded
    @Published var lastBackendSyncSucceeded = true

    private var transactionListener: Task<Void, Error>?

    /// Flag to prevent concurrent status updates (race condition protection)
    private var isUpdatingStatus = false

    /// Flag to prevent concurrent purchases
    private var isPurchasing = false

    enum SubscriptionStatus: Equatable {
        case free
        case plus(expiresAt: Date?, isTrialing: Bool)
        case gracePeriod(expiresAt: Date?)  // Billing retry in progress
        case expired

        var isPremium: Bool {
            switch self {
            case .plus, .gracePeriod: return true
            case .free, .expired: return false
            }
        }

        var displayName: String {
            switch self {
            case .free: return "Free"
            case .plus: return "Homebound+"
            case .gracePeriod: return "Homebound+"
            case .expired: return "Expired"
            }
        }
    }

    private init() {
        // Start listening for transactions immediately
        transactionListener = listenForTransactions()

        // Load products on init
        Task {
            await loadProducts()
            await updateSubscriptionStatus()
        }
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Product Loading

    /// Load available products from App Store
    func loadProducts() async {
        isLoading = true
        defer { isLoading = false }

        do {
            let productIDs = SubscriptionProduct.allCases.map { $0.rawValue }
            debugLog("[SubscriptionManager] Requesting products: \(productIDs)")
            products = try await Product.products(for: Set(productIDs))
            products.sort { $0.price < $1.price }  // Sort by price (monthly first)
            debugLog("[SubscriptionManager] Loaded \(products.count) products: \(products.map { $0.id })")

            if products.isEmpty {
                debugLog("[SubscriptionManager] ⚠️ No products returned - check App Store Connect configuration")
            }
        } catch {
            debugLog("[SubscriptionManager] Failed to load products: \(error)")
            purchaseError = "Failed to load subscription options. Please try again later."
        }
    }

    // MARK: - Purchase

    /// Purchase a subscription product
    /// - Parameter product: The product to purchase
    /// - Returns: True if purchase was successful
    func purchase(_ product: Product) async -> Bool {
        // Prevent concurrent purchases (race condition protection)
        guard !isPurchasing else {
            debugLog("[SubscriptionManager] Purchase already in progress, ignoring")
            return false
        }

        isPurchasing = true
        isLoading = true
        purchaseError = nil
        defer {
            isLoading = false
            isPurchasing = false
        }

        do {
            let result = try await product.purchase()

            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)

                debugLog("[SubscriptionManager] Purchase successful: \(transaction.productID)")

                // Send to backend for server-side validation
                await verifyWithBackend(transaction: transaction)

                // Finish transaction
                await transaction.finish()

                // Update local status
                await updateSubscriptionStatus()

                return true

            case .userCancelled:
                debugLog("[SubscriptionManager] User cancelled purchase")
                return false

            case .pending:
                debugLog("[SubscriptionManager] Purchase pending approval")
                purchaseError = "Purchase is pending approval"
                return false

            @unknown default:
                debugLog("[SubscriptionManager] Unknown purchase result")
                return false
            }
        } catch StoreKitError.userCancelled {
            debugLog("[SubscriptionManager] User cancelled (StoreKitError)")
            return false
        } catch {
            purchaseError = error.localizedDescription
            debugLog("[SubscriptionManager] Purchase failed: \(error)")
            return false
        }
    }

    // MARK: - Restore Purchases

    /// Restore previous purchases
    func restorePurchases() async {
        isLoading = true
        purchaseError = nil
        defer { isLoading = false }

        do {
            try await AppStore.sync()
            await updateSubscriptionStatus()
            debugLog("[SubscriptionManager] Purchases restored")
        } catch {
            purchaseError = "Failed to restore purchases: \(error.localizedDescription)"
            debugLog("[SubscriptionManager] Restore failed: \(error)")
        }
    }

    // MARK: - Transaction Handling

    /// Listen for transaction updates (renewals, refunds, etc.)
    private func listenForTransactions() -> Task<Void, Error> {
        Task.detached { [weak self] in
            // Check if task was cancelled before starting
            guard !Task.isCancelled else { return }

            for await result in Transaction.updates {
                // Check cancellation at each iteration to properly clean up
                guard !Task.isCancelled else {
                    break
                }

                // Verify self still exists (prevent memory leak)
                guard let self = self else {
                    break
                }

                do {
                    let transaction = try self.checkVerifiedNonisolated(result)

                    // Verify with backend and update status on main actor
                    await self.handleTransactionUpdate(transaction)
                } catch {
                    await MainActor.run {
                        debugLog("[SubscriptionManager] Transaction update failed: \(error)")
                    }
                }
            }
        }
    }

    /// Non-isolated version of checkVerified for use in detached tasks
    private nonisolated func checkVerifiedNonisolated<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified(_, let error):
            throw error
        case .verified(let safe):
            return safe
        }
    }

    /// Handle a transaction update on the main actor
    private func handleTransactionUpdate(_ transaction: Transaction) async {
        debugLog("[SubscriptionManager] Transaction update: \(transaction.productID)")

        await verifyWithBackend(transaction: transaction)
        await transaction.finish()
        await updateSubscriptionStatus()
    }

    /// Verify a transaction result
    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified(_, let error):
            throw error
        case .verified(let safe):
            return safe
        }
    }

    // MARK: - Backend Verification

    /// Send transaction to backend for server-side validation
    private func verifyWithBackend(transaction: Transaction) async {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        // Check if this is a trial purchase
        let isTrial = transaction.offer?.paymentMode == .freeTrial

        // Get auto-renew status and grace period info from subscription status
        var autoRenew = true  // Default to true for new purchases
        var gracePeriodExpiresDate: Date?
        var isInGracePeriod = false

        if let product = products.first(where: { $0.id == transaction.productID }),
           let subscription = product.subscription {
            do {
                let statuses = try await subscription.status
                for status in statuses {
                    if case .verified(let renewalInfo) = status.renewalInfo {
                        autoRenew = renewalInfo.willAutoRenew

                        // Check for grace period (billing retry in progress)
                        if let gracePeriodExpires = renewalInfo.gracePeriodExpirationDate {
                            gracePeriodExpiresDate = gracePeriodExpires
                            isInGracePeriod = gracePeriodExpires > Date()
                        }
                        break
                    }
                }
            } catch {
                debugLog("[SubscriptionManager] Failed to get renewal info for backend: \(error)")
            }
        }

        let request = VerifyPurchaseRequest(
            transactionId: String(transaction.id),
            originalTransactionId: String(transaction.originalID),
            productId: transaction.productID,
            purchaseDate: formatter.string(from: transaction.purchaseDate),
            expiresDate: transaction.expirationDate.map { formatter.string(from: $0) },
            environment: transaction.environment == .sandbox ? "sandbox" : "production",
            isFamilyShared: transaction.ownershipType == .familyShared,
            autoRenew: autoRenew,
            isTrial: isTrial,
            gracePeriodExpiresDate: gracePeriodExpiresDate.map { formatter.string(from: $0) },
            isInGracePeriod: isInGracePeriod
        )

        await Session.shared.verifyPurchase(request)
    }

    // MARK: - Status Updates

    /// Update subscription status from current entitlements
    func updateSubscriptionStatus() async {
        // Prevent concurrent status updates (race condition protection)
        guard !isUpdatingStatus else {
            debugLog("[SubscriptionManager] Status update already in progress, skipping")
            return
        }

        isUpdatingStatus = true
        defer { isUpdatingStatus = false }

        // Check current entitlements
        for await result in Transaction.currentEntitlements {
            do {
                let transaction = try checkVerified(result)

                // Check if transaction was revoked (refunded)
                if transaction.revocationDate != nil {
                    debugLog("[SubscriptionManager] Transaction revoked: \(transaction.productID)")
                    continue  // Skip revoked transactions
                }

                if transaction.productType == .autoRenewable {
                    // Check for grace period status first
                    let gracePeriodInfo = await checkGracePeriodStatus(for: transaction.productID)

                    if let expDate = transaction.expirationDate {
                        // Use UTC for consistent comparison
                        let nowUTC = Date()

                        // Check if in grace period (expired but billing retry in progress)
                        if gracePeriodInfo.isInGracePeriod {
                            self.subscriptionStatus = .gracePeriod(expiresAt: gracePeriodInfo.gracePeriodExpiresDate)
                            self.expirationDate = gracePeriodInfo.gracePeriodExpiresDate ?? expDate
                            self.isTrialing = false
                            self.isInGracePeriod = true
                            self.purchasedProductIDs.insert(transaction.productID)

                            debugLog("[SubscriptionManager] Subscription in grace period: \(transaction.productID)")
                            return
                        }

                        // Check if subscription is still valid
                        if expDate > nowUTC {
                            // Check if this is a trial/introductory offer
                            // Use multiple methods for reliable trial detection:
                            // 1. Transaction's offer info (primary)
                            // 2. Subscription status API (fallback)
                            var isTrial = transaction.offer?.paymentMode == .freeTrial

                            // Also check via subscription status API for more reliability
                            if !isTrial, let product = products.first(where: { $0.id == transaction.productID }),
                               let subscription = product.subscription {
                                if let statuses = try? await subscription.status {
                                    for status in statuses {
                                        if case .verified(let renewalInfo) = status.renewalInfo {
                                            // Check if currently in intro offer period
                                            if renewalInfo.offer?.type == .introductory {
                                                isTrial = true
                                            }
                                            break
                                        }
                                    }
                                }
                            }

                            self.subscriptionStatus = .plus(
                                expiresAt: expDate,
                                isTrialing: isTrial
                            )
                            self.expirationDate = expDate
                            self.isTrialing = isTrial
                            self.isInGracePeriod = false
                            self.purchasedProductIDs.insert(transaction.productID)

                            // Get renewal info to check if subscription will auto-renew
                            let previousAutoRenew = self.willAutoRenew
                            await updateRenewalStatus(for: transaction.productID)

                            // Sync with backend if auto-renew status changed (e.g., user cancelled)
                            if previousAutoRenew != self.willAutoRenew {
                                debugLog("[SubscriptionManager] Auto-renew status changed: \(previousAutoRenew) -> \(self.willAutoRenew), syncing with backend")
                                await verifyWithBackend(transaction: transaction)
                            }

                            debugLog("[SubscriptionManager] Active subscription: \(transaction.productID), expires: \(expDate), willAutoRenew: \(willAutoRenew)")
                            return
                        }
                    }
                }
            } catch {
                debugLog("[SubscriptionManager] Entitlement check failed: \(error)")
            }
        }

        // No valid subscription found
        self.subscriptionStatus = .free
        self.expirationDate = nil
        self.isTrialing = false
        self.isInGracePeriod = false
        self.willAutoRenew = true  // Reset to default
        self.purchasedProductIDs.removeAll()
        debugLog("[SubscriptionManager] No active subscription")
    }

    /// Debug only: Reset subscription state to free tier for testing
    func resetForDebug() {
        subscriptionStatus = .free
        purchasedProductIDs.removeAll()
        expirationDate = nil
        isTrialing = false
        isInGracePeriod = false
        willAutoRenew = true
        debugLog("[SubscriptionManager] DEBUG: Subscription state reset to free")
    }

    /// Check if subscription is in Apple's billing grace period
    private func checkGracePeriodStatus(for productID: String) async -> (isInGracePeriod: Bool, gracePeriodExpiresDate: Date?) {
        guard let product = products.first(where: { $0.id == productID }),
              let subscription = product.subscription else {
            return (false, nil)
        }

        do {
            let statuses = try await subscription.status
            for status in statuses {
                // Check if in billing retry/grace period
                if case .verified(let renewalInfo) = status.renewalInfo {
                    // Check for grace period - subscription is expired but Apple is retrying billing
                    if renewalInfo.gracePeriodExpirationDate != nil {
                        return (true, renewalInfo.gracePeriodExpirationDate)
                    }
                }
            }
        } catch {
            debugLog("[SubscriptionManager] Failed to check grace period: \(error)")
        }

        return (false, nil)
    }

    /// Update the auto-renew status from StoreKit's subscription status
    private func updateRenewalStatus(for productID: String) async {
        guard let product = products.first(where: { $0.id == productID }),
              let subscription = product.subscription else {
            debugLog("[SubscriptionManager] Could not find product for renewal status: \(productID)")
            // If products haven't loaded, try to load them and retry
            if products.isEmpty {
                await loadProducts()
                if let product = products.first(where: { $0.id == productID }),
                   let subscription = product.subscription {
                    await fetchRenewalInfo(from: subscription)
                    return
                }
            }
            // Default to true (assume active) when we can't determine status
            self.willAutoRenew = true
            return
        }

        await fetchRenewalInfo(from: subscription)
    }

    /// Helper to fetch renewal info from a subscription
    private func fetchRenewalInfo(from subscription: Product.SubscriptionInfo) async {
        do {
            let statuses = try await subscription.status
            for status in statuses {
                // Check renewal info for auto-renew status
                if case .verified(let renewalInfo) = status.renewalInfo {
                    self.willAutoRenew = renewalInfo.willAutoRenew
                    debugLog("[SubscriptionManager] Renewal status - willAutoRenew: \(renewalInfo.willAutoRenew)")
                    return
                }
            }
            // No verified renewal info found - assume active
            self.willAutoRenew = true
        } catch {
            debugLog("[SubscriptionManager] Failed to get renewal status: \(error)")
            // On error, assume active to avoid falsely showing cancelled
            self.willAutoRenew = true
        }
    }

    // MARK: - Helpers

    /// Get the monthly product
    var monthlyProduct: Product? {
        products.first { $0.id == SubscriptionProduct.monthlyPlus.rawValue }
    }

    /// Get the yearly product
    var yearlyProduct: Product? {
        products.first { $0.id == SubscriptionProduct.yearlyPlus.rawValue }
    }

    /// Calculate savings for yearly vs monthly
    var yearlySavingsPercentage: Int? {
        guard let monthly = monthlyProduct,
              let yearly = yearlyProduct else { return nil }

        let monthlyAnnual = NSDecimalNumber(decimal: monthly.price * 12).doubleValue
        let yearlyPrice = NSDecimalNumber(decimal: yearly.price).doubleValue
        let savings = (monthlyAnnual - yearlyPrice) / monthlyAnnual * 100
        return Int(savings.rounded())
    }

    /// Format price for display
    func formattedPrice(for product: Product) -> String {
        product.displayPrice
    }

    /// Format price per month for yearly subscription
    func formattedMonthlyPrice(for product: Product) -> String? {
        guard product.id == SubscriptionProduct.yearlyPlus.rawValue else { return nil }
        let monthlyPrice = product.price / 12
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.locale = product.priceFormatStyle.locale
        return formatter.string(from: monthlyPrice as NSNumber)
    }

    /// Get the current subscription's display price (for showing what user will be charged)
    var currentSubscriptionPrice: String? {
        guard let productId = purchasedProductIDs.first,
              let product = products.first(where: { $0.id == productId }) else {
            return nil
        }
        return product.displayPrice
    }

    /// Get the current subscription's billing period description
    var currentSubscriptionPeriod: String? {
        guard let productId = purchasedProductIDs.first else { return nil }
        if productId == SubscriptionProduct.yearlyPlus.rawValue {
            return "year"
        } else {
            return "month"
        }
    }
}

// MARK: - Session Extension

extension Session {
    /// Verify a purchase with the backend
    /// - Returns: True if verification succeeded, false otherwise
    @discardableResult
    func verifyPurchase(_ request: VerifyPurchaseRequest) async -> Bool {
        guard let token = accessToken else {
            debugLog("[Session] No access token for purchase verification")
            await MainActor.run {
                SubscriptionManager.shared.lastBackendSyncSucceeded = false
            }
            return false
        }

        let url = baseURL.appendingPathComponent("/api/v1/subscriptions/verify-purchase")

        do {
            let response: VerifyPurchaseResponse = try await api.post(url, body: request, bearer: token)
            debugLog("[Session] Purchase verified: \(response.message)")

            // Reload feature limits after verification
            await loadFeatureLimits()

            await MainActor.run {
                SubscriptionManager.shared.lastBackendSyncSucceeded = true
            }
            return true
        } catch {
            debugLog("[Session] Failed to verify purchase: \(error)")
            await MainActor.run {
                SubscriptionManager.shared.lastBackendSyncSucceeded = false
            }
            return false
        }
    }
}
