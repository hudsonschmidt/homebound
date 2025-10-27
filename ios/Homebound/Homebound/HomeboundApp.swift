//
//  HomeboundApp.swift
//  Homebound
//
//  Created by Hudson Schmidt on 10/23/25.
//

import SwiftUI
import UserNotifications

@main
struct HomeboundApp: App {
    @StateObject private var session = Session()
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            if session.accessToken != nil {
                ImprovedHomeView()  // Show improved home if authenticated
                    .environmentObject(session)
                    .task { await requestPush() }
                    .onOpenURL { url in
                        // Handle universal links for check-in/out
                        handleUniversalLink(url)
                    }
            } else {
                AuthenticationView()  // Show login if not authenticated
                    .environmentObject(session)
            }
        }
    }

    private func requestPush() async {
        let center = UNUserNotificationCenter.current()
        _ = try? await center.requestAuthorization(options: [.alert, .badge, .sound])
        await MainActor.run {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    private func handleUniversalLink(_ url: URL) {
        // Handle /t/{token}/checkin or /t/{token}/checkout
        if url.pathComponents.count >= 3 && url.pathComponents[1] == "t" {
            let token = url.pathComponents[2]
            let action = url.pathComponents.count > 3 ? url.pathComponents[3] : ""

            Task {
                await session.performTokenAction(token, action: action)
            }
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        NotificationCenter.default.post(name: .hbGotAPNsToken, object: token)
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        print("APNs registration failed:", error)
    }
}

extension Notification.Name {
    static let hbGotAPNsToken = Notification.Name("hbGotAPNsToken")
}
