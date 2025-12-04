import SwiftUI

struct LoadingScreen: View {
    var body: some View {
        ZStack {
            Color(.systemBackground)
                .ignoresSafeArea()

            VStack(spacing: 24) {
                Image("Logo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 120, height: 120)

                ProgressView()
                    .scaleEffect(1.2)
            }
        }
    }
}

#Preview {
    LoadingScreen()
}
