import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var session: Session
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var age = ""
    @State private var isLoading = false
    @State private var showError = false
    @State private var errorMessage = ""
    @FocusState private var focusedField: Field?
    @State private var animationAmount = 1.0

    enum Field {
        case firstName
        case lastName
        case age
    }

    var body: some View {
        ZStack {
            // Dynamic gradient background
            LinearGradient(
                colors: [
                    Color.hbBrand,
                    Color.hbTeal,
                    Color(hex: "#FF6B6B") ?? .pink
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
            .hueRotation(.degrees(animationAmount * 20))
            .animation(.easeInOut(duration: 3).repeatForever(autoreverses: true), value: animationAmount)

            ScrollView {
                VStack(spacing: 30) {
                    Spacer(minLength: 60)

                    // Welcome message with glassmorphism
                    VStack(spacing: 20) {
                        Image(systemName: "hand.wave.fill")
                            .font(.system(size: 60))
                            .foregroundStyle(.white)
                            .shadow(radius: 10)
                            .scaleEffect(animationAmount)
                            .animation(
                                .spring(response: 0.5, dampingFraction: 0.6)
                                    .repeatForever(autoreverses: true),
                                value: animationAmount
                            )

                        Text("Welcome to Homebound!")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                            .multilineTextAlignment(.center)

                        Text("Let's get to know you better")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(.white.opacity(0.9))
                    }
                    .padding(.bottom, 40)

                    // Glass card for form
                    VStack(spacing: 25) {
                        // First name field
                        VStack(alignment: .leading, spacing: 10) {
                            Label("What's your first name?", systemImage: "person.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.9))

                            TextField("Enter your first name", text: $firstName)
                                .textFieldStyle(GlassTextFieldStyle())
                                .focused($focusedField, equals: .firstName)
                                .submitLabel(.next)
                                .onSubmit {
                                    focusedField = .lastName
                                }
                        }

                        // Last name field
                        VStack(alignment: .leading, spacing: 10) {
                            Label("What's your last name?", systemImage: "person.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.9))

                            TextField("Enter your last name", text: $lastName)
                                .textFieldStyle(GlassTextFieldStyle())
                                .focused($focusedField, equals: .lastName)
                                .submitLabel(.next)
                                .onSubmit {
                                    focusedField = .age
                                }
                        }

                        // Age field
                        VStack(alignment: .leading, spacing: 10) {
                            Label("How old are you?", systemImage: "birthday.cake.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.9))

                            TextField("Enter your age", text: $age)
                                .textFieldStyle(GlassTextFieldStyle())
                                .keyboardType(.numberPad)
                                .focused($focusedField, equals: .age)
                                .submitLabel(.done)
                                .onSubmit {
                                    saveProfile()
                                }
                        }

                        // Privacy note
                        HStack {
                            Image(systemName: "lock.shield.fill")
                                .font(.system(size: 14))
                                .foregroundStyle(.white.opacity(0.7))

                            Text("Your information is secure and will never be shared")
                                .font(.system(size: 12))
                                .foregroundStyle(.white.opacity(0.7))
                                .multilineTextAlignment(.center)
                        }
                        .padding(.top, 10)

                        // Continue button
                        Button(action: saveProfile) {
                            HStack {
                                if isLoading {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                        .scaleEffect(0.9)
                                } else {
                                    Text("Continue")
                                        .font(.system(size: 18, weight: .semibold))
                                    Image(systemName: "arrow.right")
                                        .font(.system(size: 16, weight: .bold))
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(
                                LinearGradient(
                                    colors: isButtonDisabled ?
                                        [Color.white.opacity(0.2), Color.white.opacity(0.1)] :
                                        [Color.white.opacity(0.9), Color.white.opacity(0.7)],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .foregroundStyle(isButtonDisabled ? .white.opacity(0.5) : Color.hbBrand)
                            .cornerRadius(28)
                            .shadow(color: .black.opacity(0.2), radius: 10, x: 0, y: 5)
                        }
                        .disabled(isButtonDisabled || isLoading)
                        .scaleEffect(isButtonDisabled ? 0.95 : 1.0)
                        .animation(.spring(response: 0.3), value: isButtonDisabled)
                    }
                    .padding(30)
                    .background(
                        RoundedRectangle(cornerRadius: 30)
                            .fill(.ultraThinMaterial)
                            .background(
                                RoundedRectangle(cornerRadius: 30)
                                    .fill(
                                        LinearGradient(
                                            colors: [
                                                Color.white.opacity(0.2),
                                                Color.white.opacity(0.05)
                                            ],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 30)
                                    .stroke(
                                        LinearGradient(
                                            colors: [
                                                Color.white.opacity(0.5),
                                                Color.white.opacity(0.1)
                                            ],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        ),
                                        lineWidth: 1
                                    )
                            )
                    )
                    .shadow(color: .black.opacity(0.1), radius: 20, x: 0, y: 10)
                    .padding(.horizontal, 24)

                    Spacer(minLength: 100)
                }
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .onAppear {
            animationAmount = 1.1

            // Pre-fill name fields from Apple Sign In if available
            if let appleFirst = session.appleFirstName, !appleFirst.isEmpty {
                firstName = appleFirst
            }
            if let appleLast = session.appleLastName, !appleLast.isEmpty {
                lastName = appleLast
            }

            // Auto-focus appropriate field after a brief delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                // If name is pre-filled from Apple, focus on age field
                if session.appleFirstName != nil && session.appleLastName != nil {
                    focusedField = .age
                } else {
                    focusedField = .firstName
                }
            }
        }
        .alert("Oops!", isPresented: $showError) {
            Button("OK") {}
        } message: {
            Text(errorMessage)
        }
    }

    private var isButtonDisabled: Bool {
        firstName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        lastName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        age.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
        Int(age) == nil
    }

    private func saveProfile() {
        guard !isButtonDisabled else { return }

        let trimmedFirstName = firstName.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedLastName = lastName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let ageInt = Int(age) else {
            errorMessage = "Please enter a valid age"
            showError = true
            return
        }

        guard ageInt >= 13 && ageInt <= 120 else {
            errorMessage = "Please enter an age between 13 and 120"
            showError = true
            return
        }

        isLoading = true

        Task {
            do {
                // Update profile via Session
                let success = await session.updateProfile(firstName: trimmedFirstName, lastName: trimmedLastName, age: ageInt)

                await MainActor.run {
                    isLoading = false
                    if success {
                        // Profile updated successfully
                        // The app will automatically navigate to home
                        withAnimation {
                            session.profileCompleted = true
                        }
                    } else {
                        errorMessage = "Failed to update profile. Please try again."
                        showError = true
                    }
                }
            }
        }
    }
}

// Glass-morphism text field style
struct GlassTextFieldStyle: TextFieldStyle {
    @FocusState private var isFocused: Bool

    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(.ultraThinMaterial)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(Color.white.opacity(0.1))
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.4),
                                Color.white.opacity(0.1)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
            )
            .foregroundStyle(.white)
            .tint(.white)
            .font(.system(size: 16, weight: .medium))
    }
}

#Preview {
    OnboardingView()
        .environmentObject(Session())
}