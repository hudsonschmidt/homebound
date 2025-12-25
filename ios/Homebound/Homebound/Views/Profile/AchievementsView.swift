import SwiftUI

// MARK: - Main Achievements Overview
struct AchievementsView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var session: Session

    var calculator: TripStatsCalculator {
        TripStatsCalculator(trips: session.allTrips)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Overall progress header
                    VStack(spacing: 4) {
                        Text("\(calculator.earnedAchievementsCount) of \(AchievementDefinition.all.count)")
                            .font(.title)
                            .fontWeight(.bold)

                        Text("achievements unlocked")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 8)

                    // Category sections with horizontal carousels
                    ForEach(AchievementCategory.allCases, id: \.self) { category in
                        AchievementCategorySectionView(
                            category: category,
                            calculator: calculator
                        )
                    }
                }
                .padding()
            }
            .background(Color(.systemBackground))
            .navigationTitle("Achievements")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Category Section with Horizontal Carousel
struct AchievementCategorySectionView: View {
    let category: AchievementCategory
    let calculator: TripStatsCalculator

    var achievements: [AchievementDefinition] {
        AchievementDefinition.achievements(for: category)
    }

    var earnedCount: Int {
        calculator.earnedCount(for: category)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header row
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: category.icon)
                        .foregroundStyle(category.color)
                    Text(category.displayName)
                        .font(.headline)
                }

                Spacer()

                NavigationLink(destination: AchievementCategoryDetailView(category: category, calculator: calculator)) {
                    Text("View All")
                        .font(.subheadline)
                        .foregroundStyle(category.color)
                }
            }

            // Subheader with unlock count
            Text("\(earnedCount) of \(achievements.count) unlocked")
                .font(.caption)
                .foregroundStyle(.secondary)

            // Horizontal carousel
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(achievements) { achievement in
                        AchievementTileView(
                            achievement: achievement,
                            isEarned: calculator.hasEarned(achievement),
                            currentValue: calculator.currentValue(for: achievement),
                            earnedDate: calculator.earnedDate(for: achievement)
                        )
                    }
                }
                .padding(.trailing, 40) // Extra padding to hint at more content
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
    }
}

// MARK: - Category Detail View (2-column grid)
struct AchievementCategoryDetailView: View {
    let category: AchievementCategory
    let calculator: TripStatsCalculator

    var achievements: [AchievementDefinition] {
        AchievementDefinition.achievements(for: category)
    }

    var earnedCount: Int {
        calculator.earnedCount(for: category)
    }

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Category header
                HStack(spacing: 12) {
                    Image(systemName: category.icon)
                        .font(.title2)
                        .foregroundStyle(category.color)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(category.displayName)
                            .font(.title2)
                            .fontWeight(.bold)

                        Text("\(earnedCount) of \(achievements.count) unlocked")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()
                }
                .padding(.bottom, 8)

                // 3-column grid of tiles
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(achievements) { achievement in
                        AchievementGridTileView(
                            achievement: achievement,
                            isEarned: calculator.hasEarned(achievement),
                            currentValue: calculator.currentValue(for: achievement),
                            earnedDate: calculator.earnedDate(for: achievement)
                        )
                    }
                }
            }
            .padding()
        }
        .background(Color(.systemBackground))
        .navigationTitle(category.displayName)
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    AchievementsView()
        .environmentObject(Session())
}

#Preview("Category Detail") {
    NavigationStack {
        AchievementCategoryDetailView(
            category: .totalTrips,
            calculator: TripStatsCalculator(trips: [])
        )
    }
}
