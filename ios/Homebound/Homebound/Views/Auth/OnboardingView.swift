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
    @State private var appeared = false

    enum Field {
        case firstName
        case lastName
        case age
    }

    var body: some View {
        ZStack {
            // System background
            Color(.systemBackground)
                .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 30) {
                    Spacer(minLength: 60)

                    // Welcome message
                    VStack(spacing: 16) {
                        Text("Welcome to Homebound!")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.center)

                        Text("Let's get to know you better")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.bottom, 20)

                    // Card with glowing background
                    VStack(spacing: 25) {
                        // First name field
                        VStack(alignment: .leading, spacing: 10) {
                            Label("What's your first name?", systemImage: "person.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(.secondary)

                            TextField("Enter your first name", text: $firstName)
                                .textFieldStyle(OnboardingTextFieldStyle())
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
                                .foregroundStyle(.secondary)

                            TextField("Enter your last name", text: $lastName)
                                .textFieldStyle(OnboardingTextFieldStyle())
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
                                .foregroundStyle(.secondary)

                            TextField("Enter your age", text: $age)
                                .textFieldStyle(OnboardingTextFieldStyle())
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
                                .foregroundStyle(.secondary)

                            Text("Your information is secure and will never be shared")
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
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
                            .background(isButtonDisabled ? Color.gray : Color.hbBrand)
                            .foregroundStyle(.white)
                            .cornerRadius(16)
                        }
                        .disabled(isButtonDisabled || isLoading)
                        .scaleEffect(isButtonDisabled ? 0.98 : 1.0)
                        .animation(.spring(response: 0.3), value: isButtonDisabled)
                    }
                    .padding(30)
                    .background(Color(.secondarySystemBackground))
                    .cornerRadius(32)
                    // Glowing shadow effect like active trips
                    .shadow(
                        color: Color.hbBrand.opacity(0.3),
                        radius: 20,
                        y: 10
                    )
                    .shadow(
                        color: Color.hbBrand.opacity(0.2),
                        radius: 12,
                        y: 6
                    )
                    .padding(.horizontal, 24)
                    .opacity(appeared ? 1.0 : 0.0)
                    .offset(y: appeared ? 0 : 20)

                    Spacer(minLength: 100)
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .scrollIndicators(.hidden)
        }
        .onAppear {
            // Pre-fill name fields from Apple Sign In if available
            if let appleFirst = session.appleFirstName, !appleFirst.isEmpty {
                firstName = appleFirst
            }
            if let appleLast = session.appleLastName, !appleLast.isEmpty {
                lastName = appleLast
            }

            // Animate card appearance
            withAnimation(.easeOut(duration: 0.5)) {
                appeared = true
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

// Clean text field style for onboarding
struct OnboardingTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(16)
            .background(Color(.tertiarySystemFill))
            .cornerRadius(12)
            .font(.system(size: 16, weight: .medium))
    }
}

#Preview {
    OnboardingView()
        .environmentObject(Session())
}
