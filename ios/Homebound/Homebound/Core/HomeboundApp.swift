//
//  HomeboundApp.swift
//  Homebound
//
//  Created by Hudson Schmidt on 10/23/25.
//

import SwiftUI
import UserNotifications
import BackgroundTasks

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
                } else if !session.isInitialDataLoaded {
                    // Authenticated but data not yet loaded - show loading screen
                    LoadingScreen()
                        .task {
                            await session.loadInitialData()
                        }
                        .transition(.opacity)
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
            .animation(.easeInOut(duration: 0.3), value: session.isInitialDataLoaded)
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

    // Background task identifiers
    private let backgroundRefreshTaskIdentifier = "com.homeboundapp.Homebound.refresh"
    private let backgroundProcessingTaskIdentifier = "com.homeboundapp.Homebound.processing"

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Set ourselves as the notification center delegate
        UNUserNotificationCenter.current().delegate = self

        // Register background tasks
        registerBackgroundTasks()

        return true
    }

    // MARK: - Background Tasks

    private func registerBackgroundTasks() {
        // Register for app refresh (short tasks, ~30 seconds)
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: backgroundRefreshTaskIdentifier,
            using: nil
        ) { task in
            self.handleAppRefresh(task: task as! BGAppRefreshTask)
        }

        // Register for processing tasks (longer tasks, when plugged in)
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: backgroundProcessingTaskIdentifier,
            using: nil
        ) { task in
            self.handleProcessingTask(task: task as! BGProcessingTask)
        }

        debugLog("[AppDelegate] ✅ Background tasks registered")
    }

    private func handleAppRefresh(task: BGAppRefreshTask) {
        debugLog("[AppDelegate] 🔄 Handling background app refresh")

        // Schedule the next refresh
        scheduleAppRefresh()

        // Create a task to sync pending actions
        let syncTask = Task {
            // Post notification to trigger sync in Session
            NotificationCenter.default.post(name: .backgroundSyncRequested, object: nil)

            // Wait a bit for the sync to complete (max 25 seconds to stay within limit)
            try? await Task.sleep(nanoseconds: 5_000_000_000) // 5 seconds
        }

        // Handle task expiration
        task.expirationHandler = {
            syncTask.cancel()
            debugLog("[AppDelegate] ⚠️ Background refresh task expired")
        }

        // Complete the task
        Task {
            await syncTask.value
            task.setTaskCompleted(success: true)
            debugLog("[AppDelegate] ✅ Background refresh task completed")
        }
    }

    private func handleProcessingTask(task: BGProcessingTask) {
        debugLog("[AppDelegate] 🔄 Handling background processing task")

        // Schedule the next processing task
        scheduleProcessingTask()

        // Create a task to sync pending actions
        let syncTask = Task {
            // Post notification to trigger sync in Session
            NotificationCenter.default.post(name: .backgroundSyncRequested, object: nil)

            // Processing tasks have more time, wait longer
            try? await Task.sleep(nanoseconds: 10_000_000_000) // 10 seconds
        }

        // Handle task expiration
        task.expirationHandler = {
            syncTask.cancel()
            debugLog("[AppDelegate] ⚠️ Background processing task expired")
        }

        // Complete the task
        Task {
            await syncTask.value
            task.setTaskCompleted(success: true)
            debugLog("[AppDelegate] ✅ Background processing task completed")
        }
    }

    func scheduleAppRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: backgroundRefreshTaskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes

        do {
            try BGTaskScheduler.shared.submit(request)
            debugLog("[AppDelegate] ✅ Scheduled background refresh for ~15 minutes")
        } catch {
            debugLog("[AppDelegate] ❌ Failed to schedule background refresh: \(error)")
        }
    }

    func scheduleProcessingTask() {
        let request = BGProcessingTaskRequest(identifier: backgroundProcessingTaskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60) // 1 hour
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false

        do {
            try BGTaskScheduler.shared.submit(request)
            debugLog("[AppDelegate] ✅ Scheduled background processing for ~1 hour")
        } catch {
            debugLog("[AppDelegate] ❌ Failed to schedule background processing: \(error)")
        }
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
        debugLog("APNs registration failed: \(error)")
    }

    // MARK: - Silent Push Notifications (Background Sync)

    func application(
        _ application: UIApplication,
        didReceiveRemoteNotification userInfo: [AnyHashable: Any],
        fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
    ) {
        debugLog("[AppDelegate] 📬 Received remote notification")

        // Check if this is a sync notification
        if let sync = userInfo["sync"] as? String, sync == "pending_actions" {
            debugLog("[AppDelegate] 🔄 Silent push: syncing pending actions")

            // Post notification to trigger sync in Session
            NotificationCenter.default.post(name: .backgroundSyncRequested, object: nil)

            // Give some time for sync to complete
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                completionHandler(.newData)
            }
        } else {
            completionHandler(.noData)
        }
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
    static let backgroundSyncRequested = Notification.Name("backgroundSyncRequested")
}
