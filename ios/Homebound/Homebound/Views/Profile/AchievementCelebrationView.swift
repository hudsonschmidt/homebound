import SwiftUI

/// Full-screen celebration modal for newly unlocked achievements.
/// Shows each achievement with a badge reveal animation.
struct AchievementCelebrationView: View {
    let achievements: [AchievementDefinition]
    let onDismiss: () -> Void

    @State private var showBadges = false
    @State private var currentIndex = 0

    private var isSingleAchievement: Bool {
        achievements.count == 1
    }

    var body: some View {
        ZStack {
            // Dark overlay background
            Color.black.opacity(0.9)
                .ignoresSafeArea()

            VStack(spacing: 32) {
                Spacer()

                // Title
                VStack(spacing: 8) {
                    Image(systemName: "trophy.fill")
                        .font(.system(size: 40))
                        .foregroundStyle(.orange)

                    Text(isSingleAchievement ? "Achievement Unlocked!" : "Achievements Unlocked!")
                        .font(.title)
                        .fontWeight(.bold)
                        .foregroundStyle(.white)

                    if !isSingleAchievement {
                        Text("\(achievements.count) new achievements")
                            .font(.subheadline)
                            .foregroundStyle(.white.opacity(0.7))
                    }
                }

                // Achievement badges
                if isSingleAchievement, let achievement = achievements.first {
                    // Single achievement - centered display
                    singleAchievementView(achievement)
                        .scaleEffect(showBadges ? 1.0 : 0.5)
                        .opacity(showBadges ? 1.0 : 0.0)
                } else {
                    // Multiple achievements - horizontal scroll
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 32) {
                            ForEach(Array(achievements.enumerated()), id: \.element.id) { index, achievement in
                                achievementCard(achievement, index: index)
                                    .scaleEffect(showBadges ? 1.0 : 0.5)
                                    .opacity(showBadges ? 1.0 : 0.0)
                            }
                        }
                        .padding(.horizontal, 40)
                    }
                }

                Spacer()

                // Continue button
                Button(action: onDismiss) {
                    Text("Continue")
                        .font(.headline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.hbBrand)
                        .cornerRadius(12)
                }
                .padding(.horizontal, 40)
                .padding(.bottom, 40)
            }
        }
        .onAppear {
            // Badge reveal animation - allowed per CLAUDE.md (similar to AnimatedStatCard)
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                showBadges = true
            }
        }
    }

    @ViewBuilder
    private func singleAchievementView(_ achievement: AchievementDefinition) -> some View {
        VStack(spacing: 20) {
            AchievementBadgeView(
                achievement: achievement,
                isEarned: true,
                size: 120
            )

            VStack(spacing: 8) {
                Text(achievement.title)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundStyle(.white)

                Text(achievement.description)
                    .font(.body)
                    .foregroundStyle(.white.opacity(0.8))
                    .multilineTextAlignment(.center)

                Text(achievement.category.displayName)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(achievement.category.color)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(achievement.category.color.opacity(0.2))
                    .cornerRadius(8)
            }
        }
        .padding(.horizontal, 40)
    }

    @ViewBuilder
    private func achievementCard(_ achievement: AchievementDefinition, index: Int) -> some View {
        VStack(spacing: 16) {
            AchievementBadgeView(
                achievement: achievement,
                isEarned: true,
                size: 100
            )

            VStack(spacing: 6) {
                Text(achievement.title)
                    .font(.headline)
                    .fontWeight(.bold)
                    .foregroundStyle(.white)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)

                Text(achievement.description)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.7))
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(width: 140)
    }
}

#Preview("Single Achievement") {
    AchievementCelebrationView(
        achievements: [AchievementDefinition.all[0]],
        onDismiss: {}
    )
}

#Preview("Multiple Achievements") {
    AchievementCelebrationView(
        achievements: Array(AchievementDefinition.all.prefix(4)),
        onDismiss: {}
    )
}
