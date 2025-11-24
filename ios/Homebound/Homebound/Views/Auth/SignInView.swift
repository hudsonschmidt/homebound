import SwiftUI
import AuthenticationServices

// MARK: - Apple Sign In Coordinator
class AppleSignInCoordinator: NSObject, ASAuthorizationControllerDelegate {
    let session: Session
    let onSuccess: () -> Void

    init(session: Session, onSuccess: @escaping () -> Void) {
        self.session = session
        self.onSuccess = onSuccess
    }

    func authorizationController(controller: ASAuthorizationController,
                                didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            return
        }

        Task {
            await session.signInWithApple(
                userID: credential.user,
                email: credential.email,
                firstName: credential.fullName?.givenName,
                lastName: credential.fullName?.familyName,
                identityToken: credential.identityToken
            )

            // Call success callback on main actor
            await MainActor.run {
                onSuccess()
            }
        }
    }

    func authorizationController(controller: ASAuthorizationController,
                                didCompleteWithError error: Error) {
        Task {
            await MainActor.run {
                // Check if user cancelled
                if let authError = error as? ASAuthorizationError,
                   authError.code == .canceled {
                    print("[AppleAuth] User cancelled")
                    return
                }

                session.error = "Apple Sign In failed: \(error.localizedDescription)"
            }
        }
    }
}

struct SignInView: View {
    @EnvironmentObject var session: Session
    @State private var localEmail: String = ""
    @State private var appleSignInCoordinator: AppleSignInCoordinator?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 24) {
                Spacer().frame(height: 12)

                Text("Homebound")
                    .font(.largeTitle.weight(.semibold))

                VStack(alignment: .leading, spacing: 8) {
                    Text("Create an account")
                        .font(.headline)
                    Text("Enter your email to sign up")
                        .foregroundStyle(.secondary)
                        .font(.subheadline)
                }

                VStack(spacing: 12) {
                    TextField("email@domain.com", text: $localEmail)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(.horizontal, 14)
                        .frame(height: 48)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Color(.secondarySystemBackground)))

                    Button(action: {
                        Task {
                            await MainActor.run { session.email = localEmail }
                            await session.requestMagicLink(email: localEmail)
                        }
                    }) {
                        Text(session.isRequesting ? "Sending..." : "Continue")
                            .frame(maxWidth: .infinity, minHeight: 48)
                            .font(.headline)
                    }
                    .disabled(session.isRequesting || localEmail.isEmpty)
                    .background(Color.black)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 10))

                    HStack {
                        Rectangle().frame(height: 1).foregroundStyle(.tertiary)
                        Text("or").font(.footnote).foregroundStyle(.secondary)
                        Rectangle().frame(height: 1).foregroundStyle(.tertiary)
                    }

                    // Simple button to test tap detection
                    Button {
                        print("🔴 APPLE BUTTON TAPPED!")
                        let provider = ASAuthorizationAppleIDProvider()
                        let request = provider.createRequest()
                        request.requestedScopes = [.email, .fullName]

                        let controller = ASAuthorizationController(authorizationRequests: [request])
                        appleSignInCoordinator = AppleSignInCoordinator(session: session) {}
                        controller.delegate = appleSignInCoordinator

                        print("🔴 About to call performRequests()")
                        controller.performRequests()
                    } label: {
                        HStack {
                            Image(systemName: "apple.logo")
                                .font(.title3)
                            Text("Continue with Apple")
                                .font(.headline)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 48)
                        .foregroundColor(.white)
                        .background(Color.black)
                        .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                }

                Text("By clicking continue, you agree to our **Terms of Service** and **Privacy Policy**.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Spacer()
            }
            .padding(24)
            .sheet(isPresented: Binding(get: { session.showCodeSheet }, set: { session.showCodeSheet = $0 })) {
                VerifyCodeSheet()
                    .presentationDetents([.height(280)])
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
            .navigationTitle("Sign In")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct VerifyCodeSheet: View {
    @EnvironmentObject var session: Session
    @State private var code: String = ""

    var body: some View {
        VStack(spacing: 16) {
            Text("Enter 6-digit code").font(.headline)
            Text("We sent a code to \(session.email)")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            TextField("123456", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .multilineTextAlignment(.center)
                .font(.title2.monospacedDigit())
                .padding(.horizontal, 14)
                .frame(height: 48)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color(.secondarySystemBackground)))

            HStack {
                Button("Cancel") {
                    session.showCodeSheet = false
                }
                .frame(maxWidth: .infinity, minHeight: 44)

                Button("Verify") {
                    Task {
                        await session.verifyMagic(code: code, email: session.email)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(.borderedProminent)

            if let err = session.error, !err.isEmpty {
                Text(err).font(.footnote).foregroundStyle(.red)
            }
        }
        .padding(20)
    }
}
