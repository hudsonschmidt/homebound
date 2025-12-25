//
//  Color+Hex.swift
//  Homebound
//
//  Shared Color extension for hex color parsing.
//  Add this file to BOTH the main app target AND the widget extension target.
//

import SwiftUI

extension Color {
    /// Initialize a Color from a hex string.
    /// Supports 3-character (RGB), 6-character (RRGGBB), and 8-character (AARRGGBB) formats.
    /// - Parameter hex: The hex color string, with or without # prefix
    /// - Returns: The Color, or nil if parsing fails
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
            #if DEBUG
            print("[Color] Invalid hex color string: '\(hex)' (length: \(hex.count), expected 3, 6, or 8)")
            #endif
            return nil
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}
