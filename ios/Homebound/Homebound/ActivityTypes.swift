import SwiftUI

// MARK: - Activity Type Definition
enum ActivityType: String, CaseIterable, Codable {
    case hiking = "hiking"
    case biking = "biking"
    case running = "running"
    case climbing = "climbing"
    case driving = "driving"
    case flying = "flying"
    case camping = "camping"
    case other = "other"

    var displayName: String {
        switch self {
        case .hiking: return "Hiking"
        case .biking: return "Biking"
        case .running: return "Running"
        case .climbing: return "Climbing"
        case .driving: return "Driving"
        case .flying: return "Flying"
        case .camping: return "Camping"
        case .other: return "Other"
        }
    }

    var icon: String {
        switch self {
        case .hiking: return "🥾"
        case .biking: return "🚴"
        case .running: return "🏃"
        case .climbing: return "🧗"
        case .driving: return "🚗"
        case .flying: return "✈️"
        case .camping: return "🏕️"
        case .other: return "📍"
        }
    }

    var defaultGraceMinutes: Int {
        switch self {
        case .hiking: return 45
        case .biking: return 30
        case .running: return 20
        case .climbing: return 60
        case .driving: return 30
        case .flying: return 120
        case .camping: return 90
        case .other: return 30
        }
    }

    var primaryColor: Color {
        switch self {
        case .hiking: return Color(hex: "#2D5016") ?? .green
        case .biking: return Color(hex: "#FF6B35") ?? .orange
        case .running: return Color(hex: "#E74C3C") ?? .red
        case .climbing: return Color(hex: "#7F8C8D") ?? .gray
        case .driving: return Color(hex: "#2C3E50") ?? .blue
        case .flying: return Color(hex: "#3498DB") ?? .blue
        case .camping: return Color(hex: "#1A237E") ?? .indigo
        case .other: return Color(hex: "#6C63FF") ?? .purple
        }
    }

    var secondaryColor: Color {
        switch self {
        case .hiking: return Color(hex: "#8B4513") ?? .brown
        case .biking: return Color(hex: "#4A90E2") ?? .blue
        case .running: return Color(hex: "#34495E") ?? .gray
        case .climbing: return Color(hex: "#E67E22") ?? .orange
        case .driving: return Color(hex: "#16A085") ?? .teal
        case .flying: return Color(hex: "#ECF0F1") ?? .gray
        case .camping: return Color(hex: "#FF6F00") ?? .orange
        case .other: return Color(hex: "#A8A8A8") ?? .gray
        }
    }

    var accentColor: Color {
        switch self {
        case .hiking: return Color(hex: "#87CEEB") ?? .blue
        case .biking: return Color(hex: "#2ECC71") ?? .green
        case .running: return Color(hex: "#F39C12") ?? .yellow
        case .climbing: return Color(hex: "#3498DB") ?? .blue
        case .driving: return Color(hex: "#ECF0F1") ?? .gray
        case .flying: return Color(hex: "#9B59B6") ?? .purple
        case .camping: return Color(hex: "#4CAF50") ?? .green
        case .other: return Color(hex: "#4ECDC4") ?? .teal
        }
    }

    var startMessage: String {
        switch self {
        case .hiking: return "Happy trails! Adventure awaits!"
        case .biking: return "Pedal power activated! Ride safe!"
        case .running: return "Let's go! Feel the rhythm!"
        case .climbing: return "Time to send it! Climb safe!"
        case .driving: return "Safe travels! Drive carefully!"
        case .flying: return "Bon voyage! Have a great flight!"
        case .camping: return "Into the wild! Enjoy nature!"
        case .other: return "Have a great adventure!"
        }
    }

    var checkinMessage: String {
        switch self {
        case .hiking: return "Great progress on the trail!"
        case .biking: return "Crushing those miles!"
        case .running: return "Runner's high incoming!"
        case .climbing: return "Making great progress up there!"
        case .driving: return "Making good progress on the road!"
        case .flying: return "Hope you're enjoying the journey!"
        case .camping: return "Camp life is good!"
        case .other: return "Thanks for checking in!"
        }
    }

    var checkoutMessage: String {
        switch self {
        case .hiking: return "Trail conquered! Well done!"
        case .biking: return "Ride complete! Great job!"
        case .running: return "Run complete! You crushed it!"
        case .climbing: return "Summit reached! Amazing work!"
        case .driving: return "Arrived safely! Journey complete!"
        case .flying: return "Welcome to your destination!"
        case .camping: return "Back to civilization!"
        case .other: return "Welcome back! Hope it was great!"
        }
    }

    var encouragementMessages: [String] {
        switch self {
        case .hiking: return ["One step at a time!", "Nature is calling!", "Enjoy the journey!"]
        case .biking: return ["Wind in your hair!", "Keep those wheels turning!", "Enjoy the ride!"]
        case .running: return ["You've got this!", "Keep that pace!", "Feel the burn!"]
        case .climbing: return ["Trust your grip!", "You're crushing it!", "The summit awaits!"]
        case .driving: return ["Enjoy the drive!", "Safe and steady!", "Almost there!"]
        case .flying: return ["Adventure awaits!", "Enjoy the views!", "Safe travels!"]
        case .camping: return ["Under the stars!", "Wilderness mode: ON!", "Enjoy the peace!"]
        case .other: return ["You're doing great!", "Stay safe!", "Enjoy!"]
        }
    }

    var safetyTips: [String] {
        switch self {
        case .hiking:
            return [
                "Pack plenty of water and snacks",
                "Check weather conditions",
                "Tell someone your route",
                "Bring a first aid kit"
            ]
        case .biking:
            return [
                "Always wear your helmet",
                "Check your brakes and tires",
                "Use lights in low visibility",
                "Stay hydrated"
            ]
        case .running:
            return [
                "Warm up before you start",
                "Stay visible with bright colors",
                "Run against traffic",
                "Stay hydrated"
            ]
        case .climbing:
            return [
                "Double-check all gear",
                "Never climb alone",
                "Know your limits",
                "Check anchor points"
            ]
        case .driving:
            return [
                "Take breaks on long drives",
                "Check your route before starting",
                "Keep your phone charged",
                "Watch for weather conditions"
            ]
        case .flying:
            return [
                "Arrive at airport early",
                "Keep documents handy",
                "Stay hydrated during flight",
                "Account for delays"
            ]
        case .camping:
            return [
                "Share your campsite location",
                "Check fire regulations",
                "Store food properly",
                "Bring weather-appropriate gear"
            ]
        case .other:
            return [
                "Stay aware of your surroundings",
                "Keep your phone charged",
                "Share your location with someone",
                "Trust your instincts"
            ]
        }
    }
}

// MARK: - Color Extension for Hex Support
extension Color {
    init?(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            return nil
        }

        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue:  Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Activity Response Models
struct ActivityInfo: Codable {
    var id: String
    var name: String
    var icon: String
    var default_grace_minutes: Int
    var colors: ActivityColors
}

struct ActivityColors: Codable {
    var primary: String
    var secondary: String
    var accent: String
}

struct ActivitiesResponse: Codable {
    var activities: [ActivityInfo]
}