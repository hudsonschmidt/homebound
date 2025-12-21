//
//  HomeboundApp.swift
//  Homebound
//
//  Created by Hudson Schmidt on 10/23/25.
//

import SwiftUI
import UserNotifications
import BackgroundTasks
import CoreLocation

@main
struct HomeboundApp: App {
    @ObservedObject private var session = Session.shared
    @ObservedObject private var preferences = AppPreferences.shared
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var showWhatsNew = false
    @State private var pendingFriendInviteToken: String?
    @State private var showFriendInvite = false

    var body: some Scene {
        WindowGroup {
            Group {
                if session.accessToken == nil {
                    // Not authenticated - show login
                    AuthenticationView()
                        .environmentObject(session)
                        .environmentObject(preferences)
                        .onOpenURL { url in
                            // Save friend invite token to show after login
                            if let token = extractFriendToken(from: url) {
                                pendingFriendInviteToken = token
                            }
                        }
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
                        .onOpenURL { url in
                            // Save friend invite token to show after onboarding
                            if let token = extractFriendToken(from: url) {
                                pendingFriendInviteToken = token
                            }
                        }
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
                            // Handle universal links for check-in/out and friend invites
                            handleUniversalLink(url)
                        }
                        .onAppear {
                            // Show What's New if user has updated from a previous version
                            if preferences.shouldShowWhatsNew {
                                showWhatsNew = true
                            }
                            // Check for pending friend invite from before login
                            if pendingFriendInviteToken != nil {
                                showFriendInvite = true
                            }
                        }
                        .fullScreenCover(isPresented: $showWhatsNew) {
                            WhatsNewView()
                        }
                        .sheet(isPresented: $showFriendInvite) {
                            if let token = pendingFriendInviteToken {
                                InviteAcceptView(token: token) {
                                    pendingFriendInviteToken = nil
                                }
                                .environmentObject(session)
                            }
                        }
                        .transition(.opacity)
                }
            }
            .animation(.easeInOut(duration: 0.3), value: session.accessToken)
            .animation(.easeInOut(duration: 0.3), value: session.isInitialDataLoaded)
            .animation(.easeInOut(duration: 0.3), value: session.profileCompleted)
            .preferredColorScheme(preferences.colorScheme.colorScheme)
            .id(preferences.colorScheme)
        }
    }

    private func requestPush() async {
        let center = UNUserNotificationCenter.current()
        _ = try? await center.requestAuthorization(options: [.alert, .badge, .sound])
        await MainActor.run {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    /// Extract friend invite token from URL, handling both custom scheme and universal link formats
    private func extractFriendToken(from url: URL) -> String? {
        // Custom URL scheme: homebound://f/{token}
        if url.scheme == "homebound" && url.host == "f" {
            if let token = url.pathComponents.last, token != "/" {
                return token
            }
        }
        // Universal link: https://api.homeboundapp.com/f/{token}
        if url.pathComponents.count >= 3 && url.pathComponents[1] == "f" {
            return url.pathComponents[2]
        }
        return nil
    }

    private func handleUniversalLink(_ url: URL) {
        // Handle custom URL scheme: homebound://f/{token}
        // In this format, host = "f" and path = "/{token}"
        if url.scheme == "homebound" {
            if url.host == "f", let token = url.pathComponents.last, token != "/" {
                pendingFriendInviteToken = token
                showFriendInvite = true
                return
            }
            if url.host == "t", url.pathComponents.count >= 2 {
                let token = url.pathComponents[1]
                let action = url.pathComponents.count > 2 ? url.pathComponents[2] : ""
                Task {
                    await session.performTokenAction(token, action: action)
                }
            }
            return
        }

        // Handle universal links: https://api.homeboundapp.com/f/{token}
        // In this format, pathComponents = ["/", "f", "{token}"]
        if url.pathComponents.count >= 3 && url.pathComponents[1] == "f" {
            let token = url.pathComponents[2]
            pendingFriendInviteToken = token
            showFriendInvite = true
            return
        }

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
        // Check-in action - runs in background without opening app
        let checkinAction = UNNotificationAction(
            identifier: "CHECKIN_ACTION",
            title: "Check In",
            options: []
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
        if let sync = userInfo["sync"] as? String {
            switch sync {
            case "pending_actions":
                debugLog("[AppDelegate] 🔄 Silent push: syncing pending actions")
                NotificationCenter.default.post(name: .backgroundSyncRequested, object: nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                    completionHandler(.newData)
                }

            case "live_activity_eta_warning", "live_activity_overdue", "trip_state_update":
                debugLog("[AppDelegate] 🔄 Silent push: updating Live Activity (\(sync))")
                // Refresh trip data and update Live Activity
                Task {
                    await Session.shared.loadActivePlan()
                    let trip = Session.shared.activeTrip
                    await LiveActivityManager.shared.restoreActivityIfNeeded(for: trip)
                    completionHandler(.newData)
                }

            default:
                debugLog("[AppDelegate] ⚠️ Unknown sync type: \(sync)")
                completionHandler(.noData)
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

        // Wrap in Task to await async operations before calling completionHandler
        // This ensures background execution completes before iOS terminates the process
        Task {
            switch response.actionIdentifier {
            case "CHECKIN_ACTION":
                await handleCheckinAction(userInfo: userInfo)

            case "CHECKOUT_ACTION":
                await handleCheckoutAction(userInfo: userInfo)

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
    }

    // MARK: - Notification Action Handlers

    private func handleCheckinAction(userInfo: [AnyHashable: Any]) async {
        guard let data = userInfo["data"] as? [String: Any],
              let checkinToken = data["checkin_token"] as? String else {
            debugLog("[Notification Action] Check-in action missing token")
            return
        }

        debugLog("[Notification Action] Check-in action tapped")

        // Use cached location (background mode can't reliably request fresh location)
        let location = LocationManager.shared.currentLocation

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

    private func handleCheckoutAction(userInfo: [AnyHashable: Any]) async {
        guard let data = userInfo["data"] as? [String: Any],
              let checkoutToken = data["checkout_token"] as? String else {
            debugLog("[Notification Action] Check-out action missing token")
            return
        }

        debugLog("[Notification Action] Check-out action tapped")

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
