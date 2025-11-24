import SwiftUI
import AuthenticationServices

// MARK: - Main Authentication View
struct AuthenticationView: View {
    @EnvironmentObject var session: Session
    @State private var email = ""
    @State private var code = ""
    @State private var showingVerification = false
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var appleSignInCoordinator: AppleSignInCoordinator?

    var body: some View {
        ZStack {
            // Gradient Background
            LinearGradient(
                colors: [
                    Color.hbBrand,
                    Color.hbTeal
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo and Title
                VStack(spacing: 24) {
                    // App Icon/Logo
                    Image(systemName: "location.north.circle.fill")
                        .font(.system(size: 80))
                        .foregroundStyle(.white)
                        .shadow(radius: 10)

                    Text("Homebound")
                        .font(.system(size: 42, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                }
                .padding(.bottom, 60)

                // Auth Card
                VStack(spacing: 20) {
                    if !showingVerification {
                        // Email Entry
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Create an account")
                                .font(.title2)
                                .fontWeight(.bold)

                            Text("Enter your email to sign up")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.bottom, 20)

                        // Email Field
                        TextField("email@domain.com", text: $email)
                            .textFieldStyle(ModernTextFieldStyle())
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()

                        // Continue Button
                        Button(action: requestMagicLink) {
                            HStack {
                                if isLoading {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                        .scaleEffect(0.8)
                                } else {
                                    Text("Continue")
                                        .fontWeight(.semibold)
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(Color.black)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                        }
                        .disabled(!isValidEmail || isLoading)
                        .opacity(!isValidEmail ? 0.6 : 1)

                        // Divider
                        HStack {
                            Rectangle()
                                .fill(Color.gray.opacity(0.3))
                                .frame(height: 1)
                            Text("or")
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                            Rectangle()
                                .fill(Color.gray.opacity(0.3))
                                .frame(height: 1)
                        }
                        .padding(.vertical, 8)

                        // Apple Sign In
                        Button {
                            print("🍎 Apple Sign In button tapped")
                            let provider = ASAuthorizationAppleIDProvider()
                            let request = provider.createRequest()
                            request.requestedScopes = [.email, .fullName]

                            let controller = ASAuthorizationController(authorizationRequests: [request])
                            appleSignInCoordinator = AppleSignInCoordinator(session: session) {}
                            controller.delegate = appleSignInCoordinator

                            print("🍎 Calling performRequests()")
                            controller.performRequests()
                        } label: {
                            HStack {
                                Image(systemName: "apple.logo")
                                    .font(.title3)
                                Text("Continue with Apple")
                                    .fontWeight(.medium)
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(Color.black)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                        }
                        .buttonStyle(.plain)

                    } else {
                        // Verification Code Entry
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Check your email")
                                .font(.title2)
                                .fontWeight(.bold)

                            Text("We sent a code to \(email)")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.bottom, 20)

                        // Code Field
                        TextField("000000", text: $code)
                            .textFieldStyle(ModernTextFieldStyle())
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .multilineTextAlignment(.center)
                            .font(.system(size: 24, weight: .bold, design: .monospaced))
                            .onChange(of: code) { _, newValue in
                                // Auto-submit when 6 digits entered
                                if newValue.count == 6 {
                                    verifyCode()
                                }
                            }

                        // Verify Button
                        Button(action: verifyCode) {
                            HStack {
                                if isLoading {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                        .scaleEffect(0.8)
                                } else {
                                    Text("Verify")
                                        .fontWeight(.semibold)
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(Color.black)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                        }
                        .disabled(code.count != 6 || isLoading)
                        .opacity(code.count != 6 ? 0.6 : 1)

                        // Resend Link
                        Button(action: {
                            withAnimation {
                                showingVerification = false
                                code = ""
                            }
                        }) {
                            Text("Use a different email")
                                .font(.footnote)
                                .foregroundStyle(.blue)
                        }
                        .padding(.top, 8)
                    }

                    // Error Message
                    if let error = errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .padding(.top, 8)
                    }
                }
                .padding(30)
                .background(Color(.systemBackground))
                .cornerRadius(20)
                .shadow(color: .black.opacity(0.1), radius: 20, x: 0, y: 10)
                .padding(.horizontal, 24)

                Spacer()
                Spacer()

                // Terms and Privacy
                VStack(spacing: 4) {
                    HStack(spacing: 4) {
                        Text("By clicking continue, you agree to our")
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.8))
                    }
                    HStack(spacing: 4) {
                        Button("Terms of Service") {}
                            .font(.caption)
                            .foregroundStyle(.white)
                            .underline()
                        Text("and")
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.8))
                        Button("Privacy Policy") {}
                            .font(.caption)
                            .foregroundStyle(.white)
                            .underline()
                    }
                }
                .padding(.bottom, 50)
            }
        }
        .onChange(of: session.accessToken) { _, newValue in
            // Auto-dismiss when authenticated
            if newValue != nil {
                // Authentication successful - the main app will handle navigation
            }
        }
        .alert("Link Apple Account?", isPresented: $session.showAppleLinkAlert) {
            Button("Link Account") {
                Task {
                    await session.linkAppleAccount()
                }
            }
            Button("Cancel", role: .cancel) {
                // Clear pending Apple credentials
                session.pendingAppleUserID = nil
                session.pendingAppleEmail = nil
                session.pendingAppleIdentityToken = nil
            }
        } message: {
            if let email = session.pendingAppleEmail {
                Text("An account with \(email) already exists. Would you like to link it to Sign in with Apple?")
            }
        }
    }

    private var isValidEmail: Bool {
        let emailPattern = #"^[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"#
        let regex = try? NSRegularExpression(pattern: emailPattern)
        let range = NSRange(location: 0, length: email.utf16.count)
        return regex?.firstMatch(in: email, options: [], range: range) != nil
    }

    private func requestMagicLink() {
        guard isValidEmail else { return }

        isLoading = true
        errorMessage = nil

        Task {
            await session.requestMagicLink(email: email)

            await MainActor.run {
                isLoading = false
                if session.error == nil {
                    withAnimation {
                        showingVerification = true
                    }
                } else {
                    errorMessage = session.error
                }
            }
        }
    }

    private func verifyCode() {
        guard code.count == 6 else { return }

        isLoading = true
        errorMessage = nil

        Task {
            await session.verifyMagic(code: code, email: email)

            await MainActor.run {
                isLoading = false
                if let error = session.error {
                    errorMessage = error
                    code = ""
                }
                // If successful, the view will auto-dismiss via onReceive
            }
        }
    }
}

// MARK: - Custom TextField Style
struct ModernTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(16)
            .background(Color(.systemGray6))
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color(.systemGray4), lineWidth: 0.5)
            )
    }
}