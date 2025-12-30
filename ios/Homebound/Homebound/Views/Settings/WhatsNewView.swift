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
                icon: "person.2",
                iconColor: .white,
                title: "More info on Friends",
                description: "See more details about your friends, including their adventure stats and achievements."
            ),
            WhatsNewFeature(
                icon: "person.crop.circle.badge.checkmark",
                iconColor: .white,
                title: "Request Check in",
                description: "Send a notification to your friends to check in on their adventures."
            ),
            WhatsNewFeature(
                icon: "location",
                iconColor: .white,
                title: "Live Location",
                description: "See your friend's live location during an adventure for added safety. (Opt-in only)"
            ),
            WhatsNewFeature(
                icon: "qrcode",
                iconColor: .white,
                title: "QR Code and Invite Link lasts forever",
                description: "Invite links and QR codes are no longer single use no longer expire."
            ),
            WhatsNewFeature(
                icon: "text.page",
                iconColor: .white,
                title: "See more details in Trip History",
                description: "Click past trips to see more detailed stats and maps of your adventures."
            ),
            WhatsNewFeature(
                icon: "ladybug",
                iconColor: .white,
                title: "Bug Fixes",
                description: "Light mode bug. Friends page updates more. UI switching improvements. Coordinate logging bug."
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
                .padding(.horizontal, 24)
                .padding(.bottom, 34)
                .background(
                    LinearGradient(
                        colors: [.clear, Color(.systemBackground)],
                        startPoint: .top,
                        endPoint: .center
                    )
                    .frame(height: 100)
                    .allowsHitTesting(false)
                )
            }
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
