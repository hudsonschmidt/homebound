import SwiftUI

struct SignInView: View {
    @EnvironmentObject var session: Session
    @State private var localEmail: String = ""

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

                    Button(action: {
                        // TODO: Sign in with Apple flow (ASAuthorizationController)
                    }) {
                        HStack {
                            Image(systemName: "apple.logo")
                            Text("Continue with Apple")
                        }
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .font(.headline)
                    }
                    .background(Color(.secondarySystemBackground))
                    .foregroundStyle(.primary)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
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
