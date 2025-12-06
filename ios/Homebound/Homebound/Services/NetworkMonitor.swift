import Foundation
import Network
import Combine

/// Notification posted when network connection is restored after being offline
extension Notification.Name {
    static let networkDidReconnect = Notification.Name("networkDidReconnect")
}

/// Monitors network connectivity and posts notifications on reconnection
final class NetworkMonitor: ObservableObject {
    static let shared = NetworkMonitor()

    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "NetworkMonitor")

    @Published private(set) var isConnected: Bool = false  // Default to false - safer to assume offline until proven online
    @Published private(set) var connectionType: ConnectionType = .unknown

    private var wasDisconnected: Bool = true  // Start as disconnected

    enum ConnectionType {
        case wifi
        case cellular
        case ethernet
        case unknown
    }

    private init() {
        startMonitoring()
    }

    private func startMonitoring() {
        monitor.pathUpdateHandler = { [weak self] path in
            guard let self = self else { return }

            let newIsConnected = path.status == .satisfied
            let newConnectionType = self.getConnectionType(path)

            DispatchQueue.main.async {
                // Check if we just reconnected after being offline
                if newIsConnected && self.wasDisconnected {
                    debugLog("[NetworkMonitor] 🌐 Network reconnected - posting notification")
                    NotificationCenter.default.post(name: .networkDidReconnect, object: nil)
                }

                // Update state
                self.wasDisconnected = !newIsConnected
                self.isConnected = newIsConnected
                self.connectionType = newConnectionType

                if newIsConnected {
                    debugLog("[NetworkMonitor] ✅ Connected via \(newConnectionType)")
                } else {
                    debugLog("[NetworkMonitor] ❌ Disconnected")
                }
            }
        }

        monitor.start(queue: queue)
        debugLog("[NetworkMonitor] Started monitoring")
    }

    private func getConnectionType(_ path: NWPath) -> ConnectionType {
        if path.usesInterfaceType(.wifi) {
            return .wifi
        } else if path.usesInterfaceType(.cellular) {
            return .cellular
        } else if path.usesInterfaceType(.wiredEthernet) {
            return .ethernet
        } else {
            return .unknown
        }
    }

    deinit {
        monitor.cancel()
    }
}
