import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var session: Session
    @Environment(\.dismiss) var dismiss
    @State private var showSignOutAlert = false

    var body: some View {
        NavigationStack {
            ZStack {
                // Gradient Background
                LinearGradient(
                    colors: [
                        Color(hex: "#6C63FF") ?? .purple,
                        Color(hex: "#4ECDC4") ?? .teal
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Profile Header Card
                        VStack(spacing: 20) {
                            // Avatar
                            ZStack {
                                Circle()
                                    .fill(
                                        LinearGradient(
                                            colors: [.white.opacity(0.9), .white.opacity(0.7)],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                                    .frame(width: 100, height: 100)

                                Text(session.userName?.prefix(1).uppercased() ?? "U")
                                    .font(.system(size: 42, weight: .bold, design: .rounded))
                                    .foregroundStyle(
                                        LinearGradient(
                                            colors: [Color(hex: "#6C63FF") ?? .purple, Color(hex: "#4ECDC4") ?? .teal],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                            }
                            .shadow(color: .black.opacity(0.1), radius: 10, x: 0, y: 5)

                            // User Name
                            Text(session.userName ?? "User")
                                .font(.system(size: 28, weight: .bold, design: .rounded))
                                .foregroundStyle(.white)

                            // Member Since
                            VStack(spacing: 4) {
                                Text("Member Since")
                                    .font(.caption)
                                    .foregroundStyle(.white.opacity(0.8))

                                Text(memberSinceDate())
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(.white)
                            }

                            // User Info
                            HStack(spacing: 30) {
                                ProfileInfoItem(
                                    icon: "envelope.fill",
                                    value: session.userEmail ?? "Not set"
                                )

                                if let age = session.userAge {
                                    ProfileInfoItem(
                                        icon: "birthday.cake.fill",
                                        value: "\(age) years"
                                    )
                                }
                            }
                        }
                        .padding(30)
                        .frame(maxWidth: .infinity)
                        .background(
                            RoundedRectangle(cornerRadius: 24)
                                .fill(.ultraThinMaterial)
                                .background(
                                    RoundedRectangle(cornerRadius: 24)
                                        .fill(Color.white.opacity(0.1))
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 24)
                                        .stroke(
                                            LinearGradient(
                                                colors: [.white.opacity(0.5), .white.opacity(0.1)],
                                                startPoint: .topLeading,
                                                endPoint: .bottomTrailing
                                            ),
                                            lineWidth: 1
                                        )
                                )
                        )
                        .shadow(color: .black.opacity(0.1), radius: 20, x: 0, y: 10)
                        .padding(.horizontal)

                        // Settings Section
                        VStack(spacing: 12) {
                            ProfileSettingRow(
                                icon: "bell.badge.fill",
                                title: "Notifications",
                                action: {}
                            )

                            ProfileSettingRow(
                                icon: "lock.shield.fill",
                                title: "Privacy & Security",
                                action: {}
                            )

                            ProfileSettingRow(
                                icon: "questionmark.circle.fill",
                                title: "Help & Support",
                                action: {}
                            )

                            ProfileSettingRow(
                                icon: "info.circle.fill",
                                title: "About",
                                action: {}
                            )
                        }
                        .padding(.horizontal)

                        // Sign Out Button
                        Button(action: {
                            showSignOutAlert = true
                        }) {
                            HStack {
                                Image(systemName: "rectangle.portrait.and.arrow.right")
                                Text("Sign Out")
                                    .fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(
                                RoundedRectangle(cornerRadius: 16)
                                    .fill(.ultraThinMaterial)
                                    .background(
                                        RoundedRectangle(cornerRadius: 16)
                                            .fill(Color.red.opacity(0.2))
                                    )
                            )
                            .foregroundStyle(.red)
                            .overlay(
                                RoundedRectangle(cornerRadius: 16)
                                    .stroke(Color.red.opacity(0.3), lineWidth: 1)
                            )
                        }
                        .padding(.horizontal)
                        .padding(.top, 20)
                    }
                    .padding(.vertical)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                }
            }
        }
        .alert("Sign Out", isPresented: $showSignOutAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Sign Out", role: .destructive) {
                session.signOut()
                dismiss()
            }
        } message: {
            Text("Are you sure you want to sign out?")
        }
    }

    private func memberSinceDate() -> String {
        // For now, return current year
        // You could store actual registration date in session
        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM yyyy"
        return formatter.string(from: Date())
    }
}

struct ProfileInfoItem: View {
    let icon: String
    let value: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(.white.opacity(0.8))
            Text(value)
                .font(.subheadline)
                .foregroundStyle(.white)
        }
    }
}

struct ProfileSettingRow: View {
    let icon: String
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundStyle(Color(hex: "#6C63FF") ?? .purple)
                    .frame(width: 30)

                Text(title)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.primary)

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(.ultraThinMaterial)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(Color.white.opacity(0.8))
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.gray.opacity(0.1), lineWidth: 1)
            )
        }
    }
}

#Preview {
    ProfileView()
        .environmentObject(Session())
}