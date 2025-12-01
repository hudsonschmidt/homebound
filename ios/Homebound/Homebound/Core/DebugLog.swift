import Foundation

/// Debug-only print function. Only prints in DEBUG builds.
@inline(__always)
func debugLog(_ message: String) {
    #if DEBUG
    print(message)
    #endif
}

/// Debug-only print function for any type. Only prints in DEBUG builds.
@inline(__always)
func debugLog(_ item: Any) {
    #if DEBUG
    print(item)
    #endif
}
