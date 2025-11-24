import SwiftUI

enum HB {
    enum Spacing { static let lg: CGFloat = 24; static let md: CGFloat = 16; static let xl: CGFloat = 36 }
    enum Radius { static let xl: CGFloat = 16 }
}

extension Color {
    static let hbBackground = Color(UIColor.systemBackground)
    static let hbPrimary = Color.primary
    static let hbAccent = Color(hex: "#6366F1") ?? Color.purple  // Indigo accent matching reference
    static let hbCardBackground = Color(UIColor.secondarySystemBackground)
}

struct HBPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 17, weight: .semibold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(Color.hbAccent.opacity(configuration.isPressed ? 0.8 : 1))
            .clipShape(RoundedRectangle(cornerRadius: HB.Radius.xl, style: .continuous))
    }
}

struct HBSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 17, weight: .semibold))
            .foregroundStyle(.primary)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: HB.Radius.xl, style: .continuous))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct HBTextFieldStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding(.horizontal, 16).frame(minHeight: 52)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: HB.Radius.xl, style: .continuous))
    }
}
extension View { func hbTextField() -> some View { modifier(HBTextFieldStyle()) } }

// MARK: - Card Styling (Solid, Clean Design)

struct SolidCard: ViewModifier {
    var cornerRadius: CGFloat = 24
    @Environment(\.colorScheme) var colorScheme

    func body(content: Content) -> some View {
        content
            .background(Color.hbCardBackground)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .shadow(
                color: colorScheme == .dark ? .clear : Color.black.opacity(0.05),
                radius: 8,
                y: 2
            )
    }
}

struct SolidButton: ViewModifier {
    var isPressed: Bool = false
    var cornerRadius: CGFloat = 12
    @Environment(\.colorScheme) var colorScheme

    func body(content: Content) -> some View {
        content
            .background(Color.hbCardBackground)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .shadow(
                color: colorScheme == .dark ? .clear : Color.black.opacity(0.05),
                radius: isPressed ? 4 : 6,
                y: isPressed ? 1 : 2
            )
            .scaleEffect(isPressed ? 0.98 : 1.0)
    }
}

extension View {
    // Keep old name for compatibility, but use new solid styling
    func glassmorphic(cornerRadius: CGFloat = 24, borderOpacity: Double = 0.6) -> some View {
        modifier(SolidCard(cornerRadius: cornerRadius))
    }

    func glassmorphicButton(isPressed: Bool = false, cornerRadius: CGFloat = 12) -> some View {
        modifier(SolidButton(isPressed: isPressed, cornerRadius: cornerRadius))
    }

    // New explicit names
    func solidCard(cornerRadius: CGFloat = 24) -> some View {
        modifier(SolidCard(cornerRadius: cornerRadius))
    }

    func solidButton(isPressed: Bool = false, cornerRadius: CGFloat = 12) -> some View {
        modifier(SolidButton(isPressed: isPressed, cornerRadius: cornerRadius))
    }
}
