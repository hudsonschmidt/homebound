import SwiftUI

/// A simple bullet list that displays activity-specific safety tips
struct SafetyTipsCarousel: View {
    let safetyTips: [String]

    var body: some View {
        if !safetyTips.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                // Header
                HStack {
                    Image(systemName: "shield.checkered")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.9))
                    Text("Safety Tips")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.9))
                    Spacer()
                }
                .padding(.bottom, 4)

                // Bullet list
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(safetyTips.enumerated()), id: \.offset) { index, tip in
                        HStack(alignment: .top, spacing: 8) {
                            Text("•")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundStyle(.white.opacity(0.8))
                                .frame(width: 12, alignment: .leading)

                            Text(tip)
                                .font(.system(size: 12, weight: .regular))
                                .foregroundStyle(.white.opacity(0.85))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }
}

#Preview {
    ZStack {
        // Background gradient to showcase glassmorphic effect
        LinearGradient(
            colors: [
                Color.hbBrand,
                Color.hbTeal
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()

        SafetyTipsCarousel(safetyTips: [
            "Always tell someone your plans and expected return time",
            "Check weather conditions before you go",
            "Bring extra water and snacks",
            "Keep your phone charged and accessible",
            "Stay on marked trails and paths"
        ])
        .padding()
    }
}
