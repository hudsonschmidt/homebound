import SwiftUI
import Combine

/// Manages achievement notification state - tracks which achievements have been seen
/// and whether new achievements are available to celebrate.
@MainActor
class AchievementNotificationManager: ObservableObject {
    static let shared = AchievementNotificationManager()

    /// Achievements that have been earned but not yet seen by the user
    @Published private(set) var unseenAchievements: [AchievementDefinition] = []

    /// Whether there are unseen achievements to show
    @Published private(set) var hasUnseenAchievements: Bool = false

    /// Flag to track if this is the first check (to avoid showing old achievements as new)
    private var hasPerformedInitialCheck = false

    private init() {}

    /// Check for newly earned achievements that haven't been seen yet.
    /// Call this after app launch and after trip completion.
    func checkForNewAchievements(trips: [Trip]) {
        let calculator = TripStatsCalculator(trips: trips)
        let seenIds = AppPreferences.shared.seenAchievementIds

        // Find all currently earned achievements
        let earnedAchievements = AchievementDefinition.all.filter {
            calculator.hasEarned($0)
        }

        // On first check, mark all currently earned as "seen" to avoid
        // showing old achievements as new on fresh install or app update
        if !hasPerformedInitialCheck {
            hasPerformedInitialCheck = true

            // If user has never seen any achievements, mark all currently earned as seen
            if seenIds.isEmpty && !earnedAchievements.isEmpty {
                let earnedIds = Set(earnedAchievements.map { $0.id })
                AppPreferences.shared.seenAchievementIds = earnedIds
                unseenAchievements = []
                hasUnseenAchievements = false
                return
            }
        }

        // Find earned achievements that haven't been seen
        let newlyEarned = earnedAchievements.filter {
            !seenIds.contains($0.id)
        }

        unseenAchievements = newlyEarned
        hasUnseenAchievements = !newlyEarned.isEmpty
    }

    /// Mark all currently unseen achievements as seen.
    /// Call this after the user views the celebration modal.
    func markAllAsSeen() {
        let idsToMark = unseenAchievements.map { $0.id }
        var updatedIds = AppPreferences.shared.seenAchievementIds
        updatedIds.formUnion(idsToMark)
        AppPreferences.shared.seenAchievementIds = updatedIds

        unseenAchievements = []
        hasUnseenAchievements = false
    }

    /// Reset the manager state (useful for testing or logout)
    func reset() {
        unseenAchievements = []
        hasUnseenAchievements = false
        hasPerformedInitialCheck = false
    }
}
