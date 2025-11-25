import Foundation
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
