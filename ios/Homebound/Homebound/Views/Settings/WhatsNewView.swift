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
        title: "Update 0.3.0",
        features: [
            WhatsNewFeature(
                icon: "bell.badge",
                iconColor: .white,
                title: "Check-in from Notifications",
                description: "Quickly check in or check out directly from push notifications without opening the app."
            ),
            WhatsNewFeature(
                icon: "play",
                iconColor: .white,
                title: "Start Upcoming Trips Early",
                description: "Slide upcoming trips left on the home screen to start them early. End time will stay the same."
            ),
            WhatsNewFeature(
                icon: "point.topright.arrow.triangle.backward.to.point.bottomleft.scurvepath",
                iconColor: .white,
                title: "Separate Starting + Ending Location Support",
                description: "When planning a trip, you can now set different starting and ending locations."
            ),
            WhatsNewFeature(
                icon: "app.badge",
                iconColor: .white,
                title: "Notification Customization",
                description: "When planning a trip, you can now set how often and when to receive check-in notifications."
            ),
            WhatsNewFeature(
                icon: "globe.badge.clock",
                iconColor: .white,
                title: "Timezone Support",
                description: "Trips can now start and end in different timezones."
            ),
            WhatsNewFeature(
                icon: "envelope.badge",
                iconColor: .white,
                title: "Option to Receive Copy of Emails",
                description: "On contact selection, you can now choose to receive a copy of all emails sent to your contacts."
            ),
            WhatsNewFeature(
                icon: "questionmark.circle",
                iconColor: .white,
                title: "Incorportated Help Buttons",
                description: "Added help buttons throughout the plan creation process."
            ),
            WhatsNewFeature(
                icon: "ladybug",
                iconColor: .white,
                title: "Bug Fixes",
                description: "Deleted items no longer reappear, notification silence works, buggy ui/keyboard issues fixed, upcoming trips no longer start when editing, and more!"
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
