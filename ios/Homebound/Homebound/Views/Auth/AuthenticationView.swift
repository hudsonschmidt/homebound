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
    @State private var appeared = false

    var body: some View {
        ZStack {
            // System background
            Color(.systemBackground)
                .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 80)

                    // Logo and Title
                    VStack(spacing: 20) {
                        // App Icon/Logo
                        ZStack {
                            Circle()
                                .fill(Color.hbBrand.opacity(0.1))
                                .frame(width: 100, height: 100)

                            Image(systemName: "location.north.circle.fill")
                                .font(.system(size: 60))
                                .foregroundStyle(Color.hbBrand)
                        }

                        Text("Homebound")
                            .font(.system(size: 38, weight: .bold, design: .rounded))
                            .foregroundStyle(.primary)
                    }
                    .padding(.bottom, 40)

                    // Auth Card with glowing effect
                    VStack(spacing: 20) {
                        if !showingVerification {
                            // Email Entry
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Welcome")
                                    .font(.title2)
                                    .fontWeight(.bold)

                                Text("Sign in or create an account")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.bottom, 16)

                            // Email Field
                            TextField("email@example.com", text: $email)
                                .textFieldStyle(AuthTextFieldStyle())
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
                                        Text("Continue with Email")
                                            .fontWeight(.semibold)
                                    }
                                }
                                .frame(maxWidth: .infinity)
                                .frame(height: 56)
                                .background(isValidEmail ? Color.hbBrand : Color.gray)
                                .foregroundStyle(.white)
                                .cornerRadius(14)
                            }
                            .disabled(!isValidEmail || isLoading)

                            // Divider
                            HStack {
                                Rectangle()
                                    .fill(Color(.separator))
                                    .frame(height: 1)
                                Text("or")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                Rectangle()
                                    .fill(Color(.separator))
                                    .frame(height: 1)
                            }
                            .padding(.vertical, 8)

                            // Apple Sign In
                            Button {
                                let provider = ASAuthorizationAppleIDProvider()
                                let request = provider.createRequest()
                                request.requestedScopes = [.email, .fullName]

                                let controller = ASAuthorizationController(authorizationRequests: [request])
                                appleSignInCoordinator = AppleSignInCoordinator(session: session) {}
                                controller.delegate = appleSignInCoordinator
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
                                .background(Color(.label))
                                .foregroundStyle(Color(.systemBackground))
                                .cornerRadius(14)
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
                            .padding(.bottom, 16)

                            // Code Field
                            TextField("000000", text: $code)
                                .textFieldStyle(AuthTextFieldStyle())
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
                                .background(code.count == 6 ? Color.hbBrand : Color.gray)
                                .foregroundStyle(.white)
                                .cornerRadius(14)
                            }
                            .disabled(code.count != 6 || isLoading)

                            // Back Button
                            Button(action: {
                                withAnimation {
                                    showingVerification = false
                                    code = ""
                                }
                            }) {
                                Text("Use a different email")
                                    .font(.subheadline)
                                    .foregroundStyle(Color.hbBrand)
                            }
                            .padding(.top, 8)
                        }

                        // Error Message
                        if let error = errorMessage {
                            HStack {
                                Image(systemName: "exclamationmark.circle.fill")
                                    .foregroundStyle(.red)
                                Text(error)
                                    .font(.caption)
                                    .foregroundStyle(.red)
                            }
                            .padding(.top, 8)
                        }
                    }
                    .padding(28)
                    .background(Color(.secondarySystemBackground))
                    .cornerRadius(28)
                    // Glowing shadow effect
                    .shadow(
                        color: Color.hbBrand.opacity(0.25),
                        radius: 20,
                        y: 10
                    )
                    .shadow(
                        color: Color.hbBrand.opacity(0.15),
                        radius: 12,
                        y: 6
                    )
                    .padding(.horizontal, 24)
                    .opacity(appeared ? 1.0 : 0.0)
                    .offset(y: appeared ? 0 : 20)

                    Spacer(minLength: 40)

                    // Terms and Privacy
                    VStack(spacing: 4) {
                        Text("By continuing, you agree to our")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        HStack(spacing: 4) {
                            Button("Terms of Service") {}
                                .font(.caption)
                                .foregroundStyle(Color.hbBrand)
                            Text("and")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Button("Privacy Policy") {}
                                .font(.caption)
                                .foregroundStyle(Color.hbBrand)
                        }
                    }
                    .padding(.bottom, 30)
                }
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.5)) {
                appeared = true
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
struct AuthTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(16)
            .background(Color(.tertiarySystemFill))
            .cornerRadius(12)
    }
}
