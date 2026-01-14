import StoreKit
import SwiftUI
import UIKit

/// Manages App Store review prompts following Apple's guidelines.
/// - Limits prompts to ~3 per year (Apple's limit)
/// - Only prompts after meaningful engagement (completed trips)
/// - Respects user experience by not over-prompting
@MainActor
final class ReviewManager {
    static let shared = ReviewManager()

    private init() {}

    // MARK: - Configuration

    /// Minimum completed trips before first review prompt
    private let minTripsForFirstPrompt = 3

    /// Trip milestones that trigger review prompts (after first)
    private let tripMilestones: Set<Int> = [5, 10, 25, 50, 100]

    /// Minimum days between review prompts
    private let minDaysBetweenPrompts = 120

    /// Maximum prompts per year (Apple's limit is ~3)
    private let maxPromptsPerYear = 3

    // MARK: - Public Methods

    /// Check if conditions are met to request a review after trip completion.
    /// Call this after successful checkout.
    func checkForReviewOpportunity(completedTripCount: Int) {
        guard shouldRequestReview(completedTripCount: completedTripCount) else {
            return
        }

        // Add small delay for better UX (let completion animations finish)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            self.requestReview()
            self.recordPrompt(tripCount: completedTripCount)
        }
    }

    // MARK: - Private Methods

    private func shouldRequestReview(completedTripCount: Int) -> Bool {
        // Check if this is a milestone
        let isFirstEligible = completedTripCount == minTripsForFirstPrompt
        let isMilestone = tripMilestones.contains(completedTripCount)

        guard isFirstEligible || isMilestone else {
            return false
        }

        // Check if we've already prompted at this trip count or higher
        if completedTripCount <= AppPreferences.shared.lastReviewPromptTripCount {
            return false
        }

        return canPromptBasedOnHistory()
    }

    private func canPromptBasedOnHistory() -> Bool {
        let prefs = AppPreferences.shared

        // Check prompts in last year
        let oneYearAgo = Date().addingTimeInterval(-365 * 24 * 60 * 60)
        let promptsThisYear = prefs.reviewPromptDates.filter { $0 > oneYearAgo }

        if promptsThisYear.count >= maxPromptsPerYear {
            return false
        }

        // Check minimum days since last prompt
        if let lastPrompt = prefs.reviewPromptDates.max() {
            let daysSinceLastPrompt = Calendar.current.dateComponents(
                [.day],
                from: lastPrompt,
                to: Date()
            ).day ?? 0

            if daysSinceLastPrompt < minDaysBetweenPrompts {
                return false
            }
        }

        return true
    }

    private func requestReview() {
        guard let windowScene = UIApplication.shared.connectedScenes
            .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene else {
            return
        }

        Task {
            try? await AppStore.requestReview(in: windowScene)
        }
    }

    private func recordPrompt(tripCount: Int) {
        var dates = AppPreferences.shared.reviewPromptDates
        dates.append(Date())
        AppPreferences.shared.reviewPromptDates = dates
        AppPreferences.shared.lastReviewPromptTripCount = tripCount
    }
}
