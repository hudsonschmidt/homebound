import SwiftUI

enum HB {
    enum Spacing { static let lg: CGFloat = 24; static let md: CGFloat = 16; static let xl: CGFloat = 36 }
    enum Radius { static let xl: CGFloat = 16 }
}

extension Color {
    static let hbBackground = Color(UIColor.systemBackground)
    static let hbPrimary = Color.primary
    static let hbAccent = Color.black // button background (matches your mock)
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
