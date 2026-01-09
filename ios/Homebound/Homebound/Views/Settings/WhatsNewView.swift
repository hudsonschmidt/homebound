import SwiftUI

// MARK: Model

struct WhatsNewFeature: Identifiable {
    let id = UUID()
    let icon: String
    let iconColor: Color
    let title: String
    let description: String
}

struct WhatsNewRelease {
    let version: String
    let title: String
    let features: [WhatsNewFeature]
}

// MARK: Content

enum WhatsNewContent {
    static let currentRelease = WhatsNewRelease(
        version: "\(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")",
        title: "Update 0.5.1",
        features: [
            WhatsNewFeature(
                icon: "person.3",
                iconColor: .primary,
                title: "Group Trips",
                description: "Create group trips with your friends and family."
            ),
            WhatsNewFeature(
                icon: "questionmark.circle",
                iconColor: .primary,
                title: "About Page",
                description: "New About page with app info, mission, acknowledgements, and community info."
            ),
            WhatsNewFeature(
                icon: "flag",
                iconColor: .primary,
                title: "Getting Started",
                description: "New onboarding flow to help new users get started with Homebound. Always accessible from Settings."
            ),
            WhatsNewFeature(
                icon: "figure.walk",
                iconColor: .primary,
                title: "New Activities",
                description: "Walks, canyoneering, and river rafting."
            ),
            WhatsNewFeature(
                icon: "ladybug",
                iconColor: .primary,
                title: "Bug Fixes",
                description: "Check in coords are properly saved and displayed. Privacy improvements. Location search fixes. App performance fixes. Trip history fix. And more!"
            )
        ]
    )
}

// MARK: - View

struct WhatsNewView: View {
    @Environment(\.dismiss) var dismiss
    var isFromSettings: Bool = false

    var body: some View {
        ZStack {
            Color(.systemBackground)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Header
                VStack(spacing: 16) {
                    ZStack {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [Color.hbBrand, Color.hbTeal],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 80, height: 80)

                        Image("Logo")
                            .resizable()
                            .scaledToFit()
                            .frame(width: 90, height: 90)
                    }
                    .padding(.top, 60)

                    Text("What's New")
                        .font(.largeTitle)
                        .fontWeight(.bold)

                    Text("Version \(WhatsNewContent.currentRelease.version)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.bottom, 32)

                // Features list
                ScrollView {
                    VStack(spacing: 24) {
                        ForEach(WhatsNewContent.currentRelease.features) { feature in
                            FeatureRowView(feature: feature)
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.bottom, 120)
                }
                .scrollIndicators(.hidden)
            }

            // Continue button at bottom
            VStack {
                Spacer()

                VStack(spacing: 0) {
                    LinearGradient(
                        colors: [.clear, Color(.systemBackground)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: 40)

                    Color(.systemBackground)
                        .frame(height: 70)
                        .overlay(
                            Button(action: {
                                if !isFromSettings {
                                    AppPreferences.shared.markWhatsNewAsSeen()
                                }
                                dismiss()
                            }) {
                                Text(isFromSettings ? "Done" : "Continue")
                                    .font(.headline)
                                    .foregroundStyle(.white)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 56)
                                    .background(Color.hbBrand)
                                    .cornerRadius(16)
                            }
                            .padding(.horizontal, 24),
                            alignment: .top
                        )
                        .ignoresSafeArea(edges: .bottom)
                }
                .background(Color(.systemBackground))
            }
            .allowsHitTesting(true)
        }
    }
}

// MARK: - Feature Row View

struct FeatureRowView: View {
    let feature: WhatsNewFeature

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Circle()
                .fill(feature.iconColor.opacity(0.15))
                .frame(width: 50, height: 50)
                .overlay(
                    Image(systemName: feature.icon)
                        .font(.system(size: 22))
                        .foregroundStyle(feature.iconColor)
                )

            VStack(alignment: .leading, spacing: 4) {
                Text(feature.title)
                    .font(.headline)

                Text(feature.description)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()
        }
    }
}

#Preview {
    WhatsNewView()
}

#Preview("From Settings") {
    WhatsNewView(isFromSettings: true)
}
