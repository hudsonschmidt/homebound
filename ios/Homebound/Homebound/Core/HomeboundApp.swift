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
    @StateObject private var preferences = AppPreferences.shared
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            Group {
                if session.accessToken == nil {
                    // Not authenticated - show login
                    AuthenticationView()
                        .environmentObject(session)
                        .environmentObject(preferences)
                } else if !session.profileCompleted {
                    // Authenticated but profile not complete - show onboarding
                    OnboardingView()
                        .environmentObject(session)
                        .environmentObject(preferences)
                        .transition(.move(edge: .trailing))
                } else {
                    // Authenticated with complete profile - show main tab view
                    MainTabView()
                        .environmentObject(session)
                        .environmentObject(preferences)
                        .task { await requestPush() }
                        .onReceive(NotificationCenter.default.publisher(for: .hbGotAPNsToken)) { notification in
                            if let token = notification.object as? String {
                                session.handleAPNsToken(token)
                            }
                        }
                        .onOpenURL { url in
                            // Handle universal links for check-in/out
                            handleUniversalLink(url)
                        }
                        .transition(.opacity)
                }
            }
            .animation(.easeInOut(duration: 0.3), value: session.accessToken)
            .animation(.easeInOut(duration: 0.3), value: session.profileCompleted)
            .preferredColorScheme(preferences.colorScheme.colorScheme)
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

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Set ourselves as the notification center delegate
        UNUserNotificationCenter.current().delegate = self
        return true
    }

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

    // MARK: - UNUserNotificationCenterDelegate

    /// Handle notifications when app is in foreground
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // Show notification even when app is in foreground
        completionHandler([.banner, .sound, .badge])
    }

    /// Handle notification tap
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo

        // Handle any custom data from the notification
        if let tripId = userInfo["trip_id"] as? Int {
            // Post notification to navigate to trip
            NotificationCenter.default.post(
                name: .hbNavigateToTrip,
                object: tripId
            )
        }

        completionHandler()
    }
}

extension Notification.Name {
    static let hbGotAPNsToken = Notification.Name("hbGotAPNsToken")
    static let hbNavigateToTrip = Notification.Name("hbNavigateToTrip")
}
