import SwiftUI

// MARK: - Activity Type Definition
enum ActivityType: String, CaseIterable, Codable {
    case hiking = "hiking"
    case biking = "biking"
    case running = "running"
    case climbing = "climbing"
    case camping = "camping"
    case backpacking = "backpacking"
    case skiing = "skiing"
    case snowboarding = "snowboarding"
    case kayaking = "kayaking"
    case sailing = "sailing"
    case fishing = "fishing"
    case surfing = "surfing"
    case scubaDiving = "scuba_diving"
    case freeDiving = "free_diving"
    case snorkeling = "snorkeling"
    case horsebackRiding = "horseback_riding"
    case driving = "driving"
    case flying = "flying"
    case other = "other"

    var displayName: String {
        switch self {
        case .hiking: return "Hiking"
        case .biking: return "Biking"
        case .running: return "Running"
        case .climbing: return "Climbing"
        case .camping: return "Camping"
        case .backpacking: return "Backpacking"
        case .skiing: return "Skiing"
        case .snowboarding: return "Snowboarding"
        case .kayaking: return "Kayaking"
        case .sailing: return "Sailing"
        case .fishing: return "Fishing"
        case .surfing: return "Surfing"
        case .scubaDiving: return "Scuba Diving"
        case .freeDiving: return "Free Diving"
        case .snorkeling: return "Snorkeling"
        case .horsebackRiding: return "Horseback Riding"
        case .driving: return "Driving"
        case .flying: return "Flying"
        case .other: return "Other"
        }
    }

    var icon: String {
        switch self {
        case .hiking: return "🥾"
        case .biking: return "🚴"
        case .running: return "🏃"
        case .climbing: return "🧗"
        case .camping: return "🏕️"
        case .backpacking: return "🎒"
        case .skiing: return "⛷️"
        case .snowboarding: return "🏂"
        case .kayaking: return "🛶"
        case .sailing: return "⛵"
        case .fishing: return "🎣"
        case .surfing: return "🏄"
        case .scubaDiving: return "🤿"
        case .freeDiving: return "🏊"
        case .snorkeling: return "🥽"
        case .horsebackRiding: return "🐎"
        case .driving: return "🚗"
        case .flying: return "✈️"
        case .other: return "📍"
        }
    }

    var defaultGraceMinutes: Int {
        switch self {
        case .hiking: return 45
        case .biking: return 30
        case .running: return 20
        case .climbing: return 60
        case .camping: return 90
        case .backpacking: return 60
        case .skiing: return 45
        case .snowboarding: return 45
        case .kayaking: return 45
        case .sailing: return 60
        case .fishing: return 60
        case .surfing: return 30
        case .scubaDiving: return 45
        case .freeDiving: return 30
        case .snorkeling: return 30
        case .horsebackRiding: return 45
        case .driving: return 30
        case .flying: return 120
        case .other: return 30
        }
    }

    var primaryColor: Color {
        switch self {
        case .hiking: return Color(hex: "#2D5016") ?? .green
        case .biking: return Color(hex: "#FF6B35") ?? .orange
        case .running: return Color(hex: "#E74C3C") ?? .red
        case .climbing: return Color(hex: "#7F8C8D") ?? .gray
        case .camping: return Color(hex: "#1A237E") ?? .indigo
        case .backpacking: return Color(hex: "#795548") ?? .brown
        case .skiing: return Color(hex: "#00BCD4") ?? .cyan
        case .snowboarding: return Color(hex: "#039BE5") ?? .blue
        case .kayaking: return Color(hex: "#006064") ?? .teal
        case .sailing: return Color(hex: "#1976D2") ?? .blue
        case .fishing: return Color(hex: "#004D40") ?? .green
        case .surfing: return Color(hex: "#00ACC1") ?? .cyan
        case .scubaDiving: return Color(hex: "#01579B") ?? .blue
        case .freeDiving: return Color(hex: "#0277BD") ?? .blue
        case .snorkeling: return Color(hex: "#0097A7") ?? .cyan
        case .horsebackRiding: return Color(hex: "#5D4037") ?? .brown
        case .driving: return Color(hex: "#2C3E50") ?? .blue
        case .flying: return Color(hex: "#3498DB") ?? .blue
        case .other: return Color(hex: "#6C63FF") ?? .purple
        }
    }

    var secondaryColor: Color {
        switch self {
        case .hiking: return Color(hex: "#8B4513") ?? .brown
        case .biking: return Color(hex: "#4A90E2") ?? .blue
        case .running: return Color(hex: "#34495E") ?? .gray
        case .climbing: return Color(hex: "#E67E22") ?? .orange
        case .camping: return Color(hex: "#FF6F00") ?? .orange
        case .backpacking: return Color(hex: "#8D6E63") ?? .brown
        case .skiing: return Color(hex: "#E1F5FE") ?? .cyan
        case .snowboarding: return Color(hex: "#4FC3F7") ?? .blue
        case .kayaking: return Color(hex: "#4DB6AC") ?? .teal
        case .sailing: return Color(hex: "#64B5F6") ?? .blue
        case .fishing: return Color(hex: "#80CBC4") ?? .teal
        case .surfing: return Color(hex: "#4DD0E1") ?? .cyan
        case .scubaDiving: return Color(hex: "#0288D1") ?? .blue
        case .freeDiving: return Color(hex: "#29B6F6") ?? .blue
        case .snorkeling: return Color(hex: "#26C6DA") ?? .cyan
        case .horsebackRiding: return Color(hex: "#8D6E63") ?? .brown
        case .driving: return Color(hex: "#16A085") ?? .teal
        case .flying: return Color(hex: "#ECF0F1") ?? .gray
        case .other: return Color(hex: "#A8A8A8") ?? .gray
        }
    }

    var accentColor: Color {
        switch self {
        case .hiking: return Color(hex: "#87CEEB") ?? .blue
        case .biking: return Color(hex: "#2ECC71") ?? .green
        case .running: return Color(hex: "#F39C12") ?? .yellow
        case .climbing: return Color(hex: "#3498DB") ?? .blue
        case .camping: return Color(hex: "#4CAF50") ?? .green
        case .backpacking: return Color(hex: "#A1887F") ?? .brown
        case .skiing: return Color(hex: "#B3E5FC") ?? .cyan
        case .snowboarding: return Color(hex: "#81D4FA") ?? .blue
        case .kayaking: return Color(hex: "#80DEEA") ?? .cyan
        case .sailing: return Color(hex: "#90CAF9") ?? .blue
        case .fishing: return Color(hex: "#B2DFDB") ?? .teal
        case .surfing: return Color(hex: "#80DEEA") ?? .cyan
        case .scubaDiving: return Color(hex: "#4FC3F7") ?? .blue
        case .freeDiving: return Color(hex: "#81D4FA") ?? .blue
        case .snorkeling: return Color(hex: "#80DEEA") ?? .cyan
        case .horsebackRiding: return Color(hex: "#BCAAA4") ?? .brown
        case .driving: return Color(hex: "#ECF0F1") ?? .gray
        case .flying: return Color(hex: "#9B59B6") ?? .purple
        case .other: return Color(hex: "#4ECDC4") ?? .teal
        }
    }

    var startMessage: String {
        switch self {
        case .hiking: return "Happy trails! Adventure awaits!"
        case .biking: return "Pedal power activated! Ride safe!"
        case .running: return "Let's go! Feel the rhythm!"
        case .climbing: return "Time to send it! Climb safe!"
        case .camping: return "Into the wild! Enjoy nature!"
        case .backpacking: return "Pack light, adventure heavy!"
        case .skiing: return "Fresh powder awaits! Ski safe!"
        case .snowboarding: return "Shred the gnar! Board safe!"
        case .kayaking: return "Paddle on! Enjoy the water!"
        case .sailing: return "Wind in your sails! Bon voyage!"
        case .fishing: return "Tight lines! Hope they're biting!"
        case .surfing: return "Catch those waves! Surf's up!"
        case .scubaDiving: return "Dive deep! Explore the blue!"
        case .freeDiving: return "One breath, one dive! Be safe!"
        case .snorkeling: return "Explore the shallows! Have fun!"
        case .horsebackRiding: return "Saddle up! Happy trails!"
        case .driving: return "Safe travels! Drive carefully!"
        case .flying: return "Bon voyage! Have a great flight!"
        case .other: return "Have a great adventure!"
        }
    }

    var checkinMessage: String {
        switch self {
        case .hiking: return "Great progress on the trail!"
        case .biking: return "Crushing those miles!"
        case .running: return "Runner's high incoming!"
        case .climbing: return "Making great progress up there!"
        case .camping: return "Camp life is good!"
        case .backpacking: return "Trail progress looking good!"
        case .skiing: return "Carving those slopes!"
        case .snowboarding: return "Shredding nicely!"
        case .kayaking: return "Paddling strong!"
        case .sailing: return "Smooth sailing so far!"
        case .fishing: return "Any luck out there?"
        case .surfing: return "Catching some good ones!"
        case .scubaDiving: return "How's the underwater world?"
        case .freeDiving: return "Great depth control!"
        case .snorkeling: return "Enjoying the marine life!"
        case .horsebackRiding: return "Riding steady!"
        case .driving: return "Making good progress on the road!"
        case .flying: return "Hope you're enjoying the journey!"
        case .other: return "Thanks for checking in!"
        }
    }

    var checkoutMessage: String {
        switch self {
        case .hiking: return "Trail conquered! Well done!"
        case .biking: return "Ride complete! Great job!"
        case .running: return "Run complete! You crushed it!"
        case .climbing: return "Summit reached! Amazing work!"
        case .camping: return "Back to civilization!"
        case .backpacking: return "Epic journey complete!"
        case .skiing: return "Slopes conquered! Well done!"
        case .snowboarding: return "Session complete! Awesome runs!"
        case .kayaking: return "Back to shore! Great paddle!"
        case .sailing: return "Docked safely! Smooth sailing!"
        case .fishing: return "Lines are in! Hope you caught some!"
        case .surfing: return "Session done! Epic waves!"
        case .scubaDiving: return "Surface reached! Amazing dive!"
        case .freeDiving: return "Dive complete! Impressive!"
        case .snorkeling: return "Back on dry land!"
        case .horsebackRiding: return "Ride complete! Well done!"
        case .driving: return "Arrived safely! Journey complete!"
        case .flying: return "Welcome to your destination!"
        case .other: return "Welcome back! Hope it was great!"
        }
    }

    var encouragementMessages: [String] {
        switch self {
        case .hiking: return ["One step at a time!", "Nature is calling!", "Enjoy the journey!"]
        case .biking: return ["Wind in your hair!", "Keep those wheels turning!", "Enjoy the ride!"]
        case .running: return ["You've got this!", "Keep that pace!", "Feel the burn!"]
        case .climbing: return ["Trust your grip!", "You're crushing it!", "The summit awaits!"]
        case .camping: return ["Under the stars!", "Wilderness mode: ON!", "Enjoy the peace!"]
        case .backpacking: return ["Miles to go!", "Adventure continues!", "Pack's feeling lighter!"]
        case .skiing: return ["Fresh tracks!", "Perfect turns!", "Mountain vibes!"]
        case .snowboarding: return ["Send it!", "Powder day!", "Mountain magic!"]
        case .kayaking: return ["Paddle strong!", "Go with the flow!", "Water therapy!"]
        case .sailing: return ["Catch the wind!", "Smooth sailing!", "Ocean freedom!"]
        case .fishing: return ["Patience pays!", "Fish are waiting!", "Perfect day!"]
        case .surfing: return ["Next wave's yours!", "Ocean energy!", "Surf's always up!"]
        case .scubaDiving: return ["Breathe easy!", "Ocean wonders await!", "Dive deeper!"]
        case .freeDiving: return ["Mind over matter!", "One with the water!", "Pure focus!"]
        case .snorkeling: return ["Crystal clear!", "Marine paradise!", "Float on!"]
        case .horsebackRiding: return ["Ride on!", "Trust your horse!", "Trail magic!"]
        case .driving: return ["Enjoy the drive!", "Safe and steady!", "Almost there!"]
        case .flying: return ["Adventure awaits!", "Enjoy the views!", "Safe travels!"]
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
        case .camping:
            return [
                "Share your campsite location",
                "Check fire regulations",
                "Store food properly",
                "Bring weather-appropriate gear"
            ]
        case .backpacking:
            return [
                "Pack light but essential gear",
                "Know water sources on your route",
                "Leave a detailed itinerary",
                "Check trail conditions ahead"
            ]
        case .skiing:
            return [
                "Check binding adjustments",
                "Stay on marked trails",
                "Monitor avalanche conditions",
                "Wear appropriate layers"
            ]
        case .snowboarding:
            return [
                "Wear wrist guards and helmet",
                "Check snow conditions",
                "Stay within your skill level",
                "Keep bindings properly adjusted"
            ]
        case .kayaking:
            return [
                "Always wear a life jacket",
                "Check weather and water conditions",
                "Know your exit points",
                "Bring a whistle and light"
            ]
        case .sailing:
            return [
                "Check marine weather forecast",
                "Wear life jacket on deck",
                "Know emergency procedures",
                "Have backup navigation"
            ]
        case .fishing:
            return [
                "Check local regulations",
                "Wear sun protection",
                "Be aware of weather changes",
                "Handle hooks carefully"
            ]
        case .surfing:
            return [
                "Check surf conditions and tides",
                "Use a leash always",
                "Know local hazards and currents",
                "Respect local surf etiquette"
            ]
        case .scubaDiving:
            return [
                "Never dive alone",
                "Check equipment thoroughly",
                "Monitor air supply constantly",
                "Know decompression limits"
            ]
        case .freeDiving:
            return [
                "Never freedive alone",
                "Know your limits",
                "Practice proper breathing technique",
                "Watch for signs of blackout"
            ]
        case .snorkeling:
            return [
                "Check mask seal before entering",
                "Stay aware of currents",
                "Use fins for efficiency",
                "Apply reef-safe sunscreen"
            ]
        case .horsebackRiding:
            return [
                "Wear a proper helmet",
                "Check tack before mounting",
                "Match horse to skill level",
                "Stay calm around horses"
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