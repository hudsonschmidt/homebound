import SwiftUI

struct AchievementBadgeView: View {
    let achievement: AchievementDefinition
    let isEarned: Bool
    let size: CGFloat

    init(achievement: AchievementDefinition, isEarned: Bool, size: CGFloat = 60) {
        self.achievement = achievement
        self.isEarned = isEarned
        self.size = size
    }

    var body: some View {
        ZStack {
            // Outer decorative ring
            Circle()
                .stroke(
                    isEarned ?
                        LinearGradient(
                            colors: [
                                achievement.category.color,
                                achievement.category.color.opacity(0.6),
                                achievement.category.color
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

            // Inner circle background
            Circle()
                .fill(
                    isEarned ?
                        achievement.category.color.opacity(0.15) :
                        Color.gray.opacity(0.1)
                )
                .frame(width: size - 8, height: size - 8)

            // Icon
            Image(systemName: isEarned ? achievement.sfSymbol : "lock.fill")
                .font(.system(size: size * 0.4))
                .foregroundStyle(isEarned ? achievement.category.color : .gray)
        }
    }
}

#Preview {
    VStack(spacing: 20) {
        HStack(spacing: 20) {
            AchievementBadgeView(
                achievement: AchievementDefinition.all[0],
                isEarned: true,
                size: 60
            )
            AchievementBadgeView(
                achievement: AchievementDefinition.all[0],
                isEarned: false,
                size: 60
            )
        }
        HStack(spacing: 20) {
            AchievementBadgeView(
                achievement: AchievementDefinition.all[3],
                isEarned: true,
                size: 80
            )
            AchievementBadgeView(
                achievement: AchievementDefinition.all[6],
                isEarned: true,
                size: 80
            )
        }
    }
    .padding()
}
