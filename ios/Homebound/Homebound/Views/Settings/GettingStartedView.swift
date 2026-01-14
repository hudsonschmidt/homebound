import SwiftUI

// MARK: - Model

struct GettingStartedStep: Identifiable {
    let id = UUID()
    let icon: String
    let iconColor: Color
    let title: String
    let subtitle: String
    let description: String
}

// MARK: - Content

enum GettingStartedContent {
    static let steps: [GettingStartedStep] = [
        GettingStartedStep(
            icon: "map.fill",
            iconColor: Color.hbBrand,
            title: "Create",
            subtitle: "Plan your adventure",
            description: "Choose your activity, set your destination, and pick when you expect to return. Homebound keeps track so someone always knows your plan."
        ),
        GettingStartedStep(
            icon: "person.2.fill",
            iconColor: .orange,
            title: "Safety",
            subtitle: "Let someone know",
            description: "Select friends or family who will be notified about your trip. They'll know when you leave and when to expect you back."
        ),
        GettingStartedStep(
            icon: "figure.hiking",
            iconColor: .blue,
            title: "Adventure",
            subtitle: "Explore the world",
            description: "Start your trip and watch the countdown. Check in during your adventure to let contacts know you're safe."
        ),
        GettingStartedStep(
            icon: "fireworks",
            iconColor: Color.hbTeal,
            title: "Homebound",
            subtitle: "Home safe",
            description: "Tap \"I'm Safe\" when you make it wherever your adventures took you. If you don't check out in time, your safety contacts will be automatically notified. (Following a grace period you set up front.)"
        ),
        GettingStartedStep(
            icon: "person.fill.questionmark",
            iconColor: Color(hex: "#2596be") ?? Color.teal,
            title: "Why?",
            subtitle: "What can you use Homebound for?",
            description: "Anything you want! The idea for this app originally was to encourage more people to explore our beautiful Earth, staying safe while doing so. But throughout development, this app has turned into something bigger. Read more in the About section of Settings."
        )
    ]
}

// MARK: - View

struct GettingStartedView: View {
    @EnvironmentObject var preferences: AppPreferences
    @Environment(\.dismiss) var dismiss
    var isFromSettings: Bool = false

    @State private var currentPage: Int = 0

    private var isLastPage: Bool {
        currentPage == GettingStartedContent.steps.count - 1
    }

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

                    Text("Getting Started")
                        .font(.largeTitle)
                        .fontWeight(.bold)

                    Text("How Homebound keeps you safe")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.bottom, 16)

                // Paged content
                TabView(selection: $currentPage) {
                    ForEach(Array(GettingStartedContent.steps.enumerated()), id: \.element.id) { index, step in
                        GettingStartedStepView(step: step)
                            .tag(index)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))

                // Bottom controls
                VStack(spacing: 0) {
                    LinearGradient(
                        colors: [.clear, Color(.systemBackground)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: 40)

                    Color(.systemBackground)
                        .frame(height: 120)
                        .overlay(
                            VStack(spacing: 16) {
                                // Page indicators
                                HStack(spacing: 8) {
                                    ForEach(0..<GettingStartedContent.steps.count, id: \.self) { index in
                                        Circle()
                                            .fill(index == currentPage ? Color.hbBrand : Color.gray.opacity(0.3))
                                            .frame(width: 8, height: 8)
                                    }
                                }

                                // Continue/Get Started button
                                Button(action: {
                                    if isLastPage {
                                        if !isFromSettings {
                                            preferences.markGettingStartedAsSeen()
                                        }
                                        dismiss()
                                    } else {
                                        currentPage += 1
                                    }
                                }) {
                                    Text(isLastPage ? (isFromSettings ? "Done" : "Get Started") : "Continue")
                                        .font(.headline)
                                        .foregroundStyle(.white)
                                        .frame(maxWidth: .infinity)
                                        .frame(height: 56)
                                        .background(Color.hbBrand)
                                        .cornerRadius(16)
                                }
                                .padding(.horizontal, 24)
                            },
                            alignment: .top
                        )
                        .ignoresSafeArea(edges: .bottom)
                }
            }
        }
    }
}

// MARK: - Step View

struct GettingStartedStepView: View {
    let step: GettingStartedStep

    var body: some View {
        VStack(spacing: 20) {
            Spacer()

            Circle()
                .fill(step.iconColor.opacity(0.15))
                .frame(width: 80, height: 80)
                .overlay(
                    Image(systemName: step.icon)
                        .font(.system(size: 36))
                        .foregroundStyle(step.iconColor)
                )

            VStack(spacing: 8) {
                Text(step.title)
                    .font(.title2)
                    .fontWeight(.bold)
                    .multilineTextAlignment(.center)

                Text(step.subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Text(step.description)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 24)

            Spacer()
            Spacer()
        }
        .padding(.horizontal, 16)
    }
}

// MARK: - Previews

#Preview {
    GettingStartedView()
        .environmentObject(AppPreferences.shared)
}

#Preview("From Settings") {
    GettingStartedView(isFromSettings: true)
        .environmentObject(AppPreferences.shared)
}
