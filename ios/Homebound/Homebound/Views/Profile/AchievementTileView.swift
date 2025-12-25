import SwiftUI

// MARK: - Carousel Tile (for horizontal scrolling)
struct AchievementTileView: View {
    let achievement: AchievementDefinition
    let isEarned: Bool
    let currentValue: Int
    let earnedDate: Date?

    private var progressText: String {
        if isEarned, let date = earnedDate {
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            return formatter.string(from: date)
        } else {
            return "\(currentValue)/\(achievement.threshold)"
        }
    }

    var body: some View {
        VStack(spacing: 8) {
            AchievementBadgeView(
                achievement: achievement,
                isEarned: isEarned,
                size: 60
            )

            Text(achievement.title)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(isEarned ? .primary : .secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            Text(progressText)
                .font(.caption2)
                .foregroundStyle(isEarned ? achievement.category.color : .secondary)
                .lineLimit(1)
        }
        .frame(width: 100)
        .padding(.vertical, 12)
        .padding(.horizontal, 8)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.secondarySystemBackground))
        )
        .opacity(isEarned ? 1 : 0.7)
    }
}

// MARK: - Grid Tile (for category detail view)
struct AchievementGridTileView: View {
    let achievement: AchievementDefinition
    let isEarned: Bool
    let currentValue: Int
    let earnedDate: Date?

    private var statusText: String {
        if isEarned {
            if let date = earnedDate {
                let formatter = DateFormatter()
                formatter.dateStyle = .short
                return formatter.string(from: date)
            }
            return "Earned"
        } else {
            return "\(currentValue)/\(achievement.threshold)"
        }
    }

    var body: some View {
        VStack(spacing: 6) {
            AchievementBadgeView(
                achievement: achievement,
                isEarned: isEarned,
                size: 50
            )

            Text(achievement.title)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(isEarned ? .primary : .secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            Text(achievement.description)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            Text(statusText)
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundStyle(isEarned ? achievement.category.color : .secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .padding(.horizontal, 6)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.secondarySystemBackground))
        )
        .opacity(isEarned ? 1 : 0.7)
    }
}

#Preview("Carousel Tiles") {
    ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 12) {
            AchievementTileView(
                achievement: AchievementDefinition.all[0],
                isEarned: true,
                currentValue: 15,
                earnedDate: Date()
            )
            AchievementTileView(
                achievement: AchievementDefinition.all[1],
                isEarned: false,
                currentValue: 23,
                earnedDate: nil
            )
            AchievementTileView(
                achievement: AchievementDefinition.all[2],
                isEarned: false,
                currentValue: 23,
                earnedDate: nil
            )
        }
        .padding()
    }
}

#Preview("Grid Tiles") {
    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
        AchievementGridTileView(
            achievement: AchievementDefinition.all[0],
            isEarned: true,
            currentValue: 15,
            earnedDate: Date()
        )
        AchievementGridTileView(
            achievement: AchievementDefinition.all[1],
            isEarned: false,
            currentValue: 23,
            earnedDate: nil
        )
    }
    .padding()
}
