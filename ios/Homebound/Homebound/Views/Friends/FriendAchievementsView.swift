import SwiftUI

/// View showing a friend's achievements with earned status
struct FriendAchievementsView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    let friend: Friend

    @State private var achievementsResponse: FriendAchievementsResponse?
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView("Loading achievements...")
                } else if let error = errorMessage {
                    ContentUnavailableView {
                        Label("Unavailable", systemImage: "lock.fill")
                    } description: {
                        Text(error)
                    }
                } else if let response = achievementsResponse {
                    achievementsContent(response)
                }
            }
            .navigationTitle("\(friend.first_name)'s Achievements")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .task {
            await loadAchievements()
        }
    }

    @ViewBuilder
    private func achievementsContent(_ response: FriendAchievementsResponse) -> some View {
        ScrollView {
            VStack(spacing: 24) {
                // Header with count
                VStack(spacing: 4) {
                    Text("\(response.earned_count) of \(response.total_count)")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("achievements unlocked")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 8)

                // Group achievements by category
                ForEach(AchievementCategory.allCases, id: \.self) { category in
                    let categoryAchievements = response.achievements.filter {
                        $0.categoryEnum == category
                    }
                    if !categoryAchievements.isEmpty {
                        FriendAchievementCategorySection(
                            category: category,
                            achievements: categoryAchievements
                        )
                    }
                }
            }
            .padding()
        }
    }

    private func loadAchievements() async {
        isLoading = true
        errorMessage = nil

        if let response = await session.loadFriendAchievements(friendUserId: friend.user_id) {
            achievementsResponse = response
        } else {
            errorMessage = "\(friend.first_name) has disabled achievement sharing"
        }

        isLoading = false
    }
}

/// A category section showing friend's achievements
struct FriendAchievementCategorySection: View {
    let category: AchievementCategory
    let achievements: [FriendAchievement]

    var earnedCount: Int {
        achievements.filter { $0.is_earned }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: category.icon)
                        .foregroundStyle(category.color)
                    Text(category.displayName)
                        .font(.headline)
                }
                Spacer()
                Text("\(earnedCount)/\(achievements.count)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Achievements carousel
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(achievements) { achievement in
                        FriendAchievementTileView(achievement: achievement)
                    }
                }
                .padding(.trailing, 40)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(16)
    }
}

/// Individual achievement tile for friend view
struct FriendAchievementTileView: View {
    let achievement: FriendAchievement

    private var progressText: String {
        if achievement.is_earned, let date = achievement.earnedDateValue {
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            return formatter.string(from: date)
        } else {
            return "\(achievement.current_value)/\(achievement.threshold)"
        }
    }

    var body: some View {
        VStack(spacing: 8) {
            // Badge
            FriendAchievementBadgeView(
                achievement: achievement,
                size: 60
            )

            Text(achievement.title)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(achievement.is_earned ? .primary : .secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            Text(progressText)
                .font(.caption2)
                .foregroundStyle(achievement.is_earned ? (achievement.categoryEnum?.color ?? .secondary) : .secondary)
                .lineLimit(1)
        }
        .frame(width: 100)
        .padding(.vertical, 12)
        .padding(.horizontal, 8)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.tertiarySystemBackground))
        )
        .opacity(achievement.is_earned ? 1 : 0.7)
    }
}

/// Badge view for friend achievements
struct FriendAchievementBadgeView: View {
    let achievement: FriendAchievement
    let size: CGFloat

    init(achievement: FriendAchievement, size: CGFloat = 60) {
        self.achievement = achievement
        self.size = size
    }

    private var categoryColor: Color {
        achievement.categoryEnum?.color ?? .gray
    }

    var body: some View {
        ZStack {
            // Outer ring
            Circle()
                .stroke(
                    achievement.is_earned ?
                        LinearGradient(
                            colors: [
                                categoryColor,
                                categoryColor.opacity(0.6),
                                categoryColor
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ) :
                        LinearGradient(
                            colors: [Color.gray.opacity(0.3)],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                    lineWidth: 3
                )
                .frame(width: size, height: size)

            // Inner circle
            Circle()
                .fill(
                    achievement.is_earned ?
                        categoryColor.opacity(0.15) :
                        Color.gray.opacity(0.1)
                )
                .frame(width: size - 8, height: size - 8)

            // Icon
            Image(systemName: achievement.is_earned ? achievement.sf_symbol : "lock.fill")
                .font(.system(size: size * 0.4))
                .foregroundStyle(achievement.is_earned ? categoryColor : .gray)
        }
    }
}

#Preview {
    FriendAchievementsView(friend: Friend(
        user_id: 1,
        first_name: "Jane",
        last_name: "Doe",
        profile_photo_url: nil,
        member_since: "2024-01-15T00:00:00",
        friendship_since: "2024-06-01T00:00:00",
        age: 28,
        achievements_count: 12,
        total_trips: 45,
        total_adventure_hours: 120,
        favorite_activity_name: "Hiking",
        favorite_activity_icon: "hiking"
    ))
    .environmentObject(Session())
}
