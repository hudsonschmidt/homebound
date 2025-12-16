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
                        .onReceive(NotificationCenter.default.publisher(for: .hbAPNsRegistrationFailed)) { notification in
                            if let errorMessage = notification.object as? String {
                                session.handleAPNsRegistrationFailed(errorMessage)
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

        // Register notification categories for actionable notifications
        registerNotificationCategories()

        // Register background tasks
        registerBackgroundTasks()

        return true
    }

    private func registerNotificationCategories() {
        // Check-in action - opens app briefly to get location
        let checkinAction = UNNotificationAction(
            identifier: "CHECKIN_ACTION",
            title: "Check In",
            options: [.foreground]
        )

        // Check-out action - completes trip (red button for emphasis)
        let checkoutAction = UNNotificationAction(
            identifier: "CHECKOUT_ACTION",
            title: "Check Out",
            options: [.destructive]
        )

        // Category for check-in reminder notifications (both actions)
        let checkinCategory = UNNotificationCategory(
            identifier: "CHECKIN_REMINDER",
            actions: [checkinAction, checkoutAction],
            intentIdentifiers: [],
            options: []
        )

        // Category for checkout-only notifications (ETA reached, grace period, etc.)
        let checkoutCategory = UNNotificationCategory(
            identifier: "CHECKOUT_ONLY",
            actions: [checkoutAction],
            intentIdentifiers: [],
            options: []
        )

        UNUserNotificationCenter.current().setNotificationCategories([checkinCategory, checkoutCategory])
        debugLog("[AppDelegate] Registered notification categories")
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
        debugLog("[APNs] ❌ Registration failed: \(error.localizedDescription)")
        // Post notification so Session can handle the error and notify user
        NotificationCenter.default.post(
            name: .hbAPNsRegistrationFailed,
            object: error.localizedDescription
        )
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

    /// Handle notification tap and action buttons
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo

        switch response.actionIdentifier {
        case "CHECKIN_ACTION":
            handleCheckinAction(userInfo: userInfo)

        case "CHECKOUT_ACTION":
            handleCheckoutAction(userInfo: userInfo)

        case UNNotificationDefaultActionIdentifier:
            // User tapped notification banner - navigate to trip
            if let data = userInfo["data"] as? [String: Any],
               let tripId = data["trip_id"] as? Int {
                NotificationCenter.default.post(name: .hbNavigateToTrip, object: tripId)
            } else if let tripId = userInfo["trip_id"] as? Int {
                NotificationCenter.default.post(name: .hbNavigateToTrip, object: tripId)
            }

        default:
            break
        }

        completionHandler()
    }

    // MARK: - Notification Action Handlers

    private func handleCheckinAction(userInfo: [AnyHashable: Any]) {
        guard let data = userInfo["data"] as? [String: Any],
              let checkinToken = data["checkin_token"] as? String else {
            debugLog("[Notification Action] Check-in action missing token")
            return
        }

        debugLog("[Notification Action] Check-in action tapped")

        Task {
            // Get location for check-in (foreground mode ensures this works)
            let location = await LocationManager.shared.getCurrentLocation()

            // Build URL with coordinates if available
            var urlString = "\(getBaseURL())/t/\(checkinToken)/checkin"
            if let loc = location {
                urlString += "?lat=\(loc.latitude)&lon=\(loc.longitude)"
            }

            guard let url = URL(string: urlString) else {
                debugLog("[Notification Action] Invalid check-in URL")
                return
            }

            do {
                let (_, response) = try await URLSession.shared.data(from: url)
                if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                    debugLog("[Notification Action] Check-in successful")
                } else {
                    debugLog("[Notification Action] Check-in failed with response: \(response)")
                }
            } catch {
                debugLog("[Notification Action] Check-in error: \(error)")
            }
        }
    }

    private func handleCheckoutAction(userInfo: [AnyHashable: Any]) {
        guard let data = userInfo["data"] as? [String: Any],
              let checkoutToken = data["checkout_token"] as? String else {
            debugLog("[Notification Action] Check-out action missing token")
            return
        }

        debugLog("[Notification Action] Check-out action tapped")

        Task {
            let urlString = "\(getBaseURL())/t/\(checkoutToken)/checkout"

            guard let url = URL(string: urlString) else {
                debugLog("[Notification Action] Invalid check-out URL")
                return
            }

            do {
                let (_, response) = try await URLSession.shared.data(from: url)
                if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                    debugLog("[Notification Action] Check-out successful")
                } else {
                    debugLog("[Notification Action] Check-out failed with response: \(response)")
                }
            } catch {
                debugLog("[Notification Action] Check-out error: \(error)")
            }
        }
    }

    /// Get the base URL based on server environment (mirrors Session.baseURL)
    private func getBaseURL() -> URL {
        let savedValue = UserDefaults.standard.string(forKey: "serverEnvironment") ?? "production"
        switch savedValue {
        case "production": return Session.productionURL
        case "devRender": return Session.devRenderURL
        case "local": return Session.localURL
        default: return Session.productionURL
        }
    }
}

extension Notification.Name {
    static let hbGotAPNsToken = Notification.Name("hbGotAPNsToken")
    static let hbAPNsRegistrationFailed = Notification.Name("hbAPNsRegistrationFailed")
    static let hbNavigateToTrip = Notification.Name("hbNavigateToTrip")
    static let backgroundSyncRequested = Notification.Name("backgroundSyncRequested")
}
