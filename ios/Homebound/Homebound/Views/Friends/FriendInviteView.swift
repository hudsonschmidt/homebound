import SwiftUI
import CoreImage.CIFilterBuiltins

/// View for creating and sharing friend invite links with QR code
struct FriendInviteView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss

    @State private var invite: FriendInvite? = nil
    @State private var isLoading = true
    @State private var showingShareSheet = false

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
        }
    }

    // MARK: - Loading View

    var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Creating invite link...")
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
                Text("Scan to Add Friend")
                    .font(.title3)
                    .fontWeight(.bold)

                Text("Have your friend scan this QR code with their Homebound app, or share the link below.")
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

            // Expiration info
            if let expiresAt = invite.expiresAtDate {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.caption)
                    Text("Expires \(expiresAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption)
                }
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
