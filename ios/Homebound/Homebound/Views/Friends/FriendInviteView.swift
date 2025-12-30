import SwiftUI
import CoreImage.CIFilterBuiltins

/// View for creating and sharing friend invite links with QR code
struct FriendInviteView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var invite: FriendInvite? = nil
    @State private var isLoading = true
    @State private var showingShareSheet = false
    @State private var showingRegenerateConfirmation = false
    @State private var isRegenerating = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    if isLoading {
                        loadingView
                    } else if let invite = invite {
                        inviteContentView(invite)
                    } else {
                        errorView
                    }
                }
                .padding()
            }
            .background(Color(.systemBackground))
            .navigationTitle("Invite Friend")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .task {
                await createInvite()
            }
            .sheet(isPresented: $showingShareSheet) {
                if let invite = invite {
                    ShareSheet(activityItems: ["Be my friend on Homebound! \(invite.invite_url)"])
                }
            }
            .confirmationDialog(
                "Regenerate Invite Link?",
                isPresented: $showingRegenerateConfirmation,
                titleVisibility: .visible
            ) {
                Button("Regenerate", role: .destructive) {
                    Task {
                        await regenerateInvite()
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This will invalidate your current invite link. Anyone with the old link or QR code will no longer be able to add you as a friend.")
            }
        }
    }

    // MARK: - Loading View

    var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text(isRegenerating ? "Regenerating link..." : "Loading your invite link...")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }

    // MARK: - Invite Content

    func inviteContentView(_ invite: FriendInvite) -> some View {
        VStack(spacing: 24) {
            // QR Code
            qrCodeView(for: invite.invite_url)

            // Instructions
            VStack(spacing: 8) {
                Text("Your Invite Link")
                    .font(.title3)
                    .fontWeight(.bold)

                Text("Share this QR code or link with friends. They can use it anytime to add you on Homebound.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            // Invite link
            inviteLinkView(invite.invite_url)

            // Share button
            Button(action: { showingShareSheet = true }) {
                Label("Share Invite Link", systemImage: "square.and.arrow.up")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color.hbBrand)
                    .cornerRadius(12)
            }

            // Regenerate link button
            Button(action: { showingRegenerateConfirmation = true }) {
                Label("Regenerate Link", systemImage: "arrow.triangle.2.circlepath")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Benefits section
            benefitsSection
        }
    }

    // MARK: - QR Code View

    func qrCodeView(for urlString: String) -> some View {
        Group {
            if let qrImage = generateQRCode(from: urlString) {
                Image(uiImage: qrImage)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
                    .frame(width: 200, height: 200)
                    .padding(16)
                    .background(Color.white)
                    .cornerRadius(16)
                    .shadow(color: Color.black.opacity(0.1), radius: 10, y: 5)
            } else {
                Rectangle()
                    .fill(Color(.secondarySystemBackground))
                    .frame(width: 200, height: 200)
                    .cornerRadius(16)
                    .overlay(
                        Image(systemName: "qrcode")
                            .font(.largeTitle)
                            .foregroundStyle(.secondary)
                    )
            }
        }
    }

    // MARK: - Invite Link View

    func inviteLinkView(_ urlString: String) -> some View {
        HStack {
            Text(urlString)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Spacer()

            Button(action: {
                UIPasteboard.general.string = urlString
                session.notice = "Link copied!"
            }) {
                Image(systemName: "doc.on.doc")
                    .font(.subheadline)
                    .foregroundStyle(Color.hbBrand)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    // MARK: - Benefits Section

    var benefitsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Friend Benefits")
                .font(.headline)

            VStack(alignment: .leading, spacing: 12) {
                benefitRow(
                    icon: "bell.badge.fill",
                    color: .green,
                    title: "Push Notifications",
                    description: "Friends get instant alerts instead of email"
                )

                benefitRow(
                    icon: "bolt.fill",
                    color: .orange,
                    title: "Faster Response",
                    description: "No email delays when you need help"
                )

                benefitRow(
                    icon: "person.2.fill",
                    color: .blue,
                    title: "Mutual Safety",
                    description: "Both of you can be safety contacts"
                )
            }
            .padding()
            .background(Color(.secondarySystemBackground))
            .cornerRadius(12)
        }
    }

    func benefitRow(icon: String, color: Color, title: String, description: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline)
                    .fontWeight(.medium)
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
    }

    // MARK: - Error View

    var errorView: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundStyle(.orange)

            Text("Couldn't create invite")
                .font(.headline)

            Text("Please check your connection and try again.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button(action: {
                Task {
                    await createInvite()
                }
            }) {
                Label("Try Again", systemImage: "arrow.clockwise")
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
                    .background(Color.hbBrand)
                    .cornerRadius(12)
            }
        }
        .padding(.vertical, 40)
    }

    // MARK: - Actions

    func createInvite() async {
        isLoading = true
        invite = await session.createFriendInvite()
        isLoading = false
    }

    func regenerateInvite() async {
        isLoading = true
        isRegenerating = true
        invite = await session.createFriendInvite(regenerate: true)
        isRegenerating = false
        isLoading = false
        if invite != nil {
            session.notice = "Link regenerated"
        }
    }

    // MARK: - QR Code Generator

    func generateQRCode(from string: String) -> UIImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()

        guard let data = string.data(using: .utf8) else { return nil }
        filter.setValue(data, forKey: "inputMessage")
        filter.setValue("H", forKey: "inputCorrectionLevel")  // High error correction

        guard let outputImage = filter.outputImage else { return nil }

        // Scale up for better quality
        let scale = 10.0
        let transform = CGAffineTransform(scaleX: scale, y: scale)
        let scaledImage = outputImage.transformed(by: transform)

        guard let cgImage = context.createCGImage(scaledImage, from: scaledImage.extent) else {
            return nil
        }

        return UIImage(cgImage: cgImage)
    }
}

#Preview {
    FriendInviteView()
        .environmentObject(Session())
}
