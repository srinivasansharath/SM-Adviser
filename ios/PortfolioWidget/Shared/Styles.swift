import SwiftUI

/// Colour + short-label helpers shared by the widget and app views.
enum Style {
    static func color(classification: String?, flag: String?) -> Color {
        switch classification {
        case "Accumulate Candidate", "Hold": return .green
        case "Watch": return .yellow
        case "Trim Candidate": return .orange
        case "Exit Candidate": return .red
        default:
            switch flag {
            case "risk": return .red
            case "watch": return .yellow
            case "ok": return .green
            default: return .gray
            }
        }
    }

    static func shortLabel(_ classification: String?) -> String {
        switch classification {
        case "Accumulate Candidate": return "ACC"
        case "Hold": return "HOLD"
        case "Watch": return "WATCH"
        case "Trim Candidate": return "TRIM"
        case "Exit Candidate": return "EXIT"
        default: return ""
        }
    }

    static func price(_ v: Double?) -> String {
        guard let v else { return "—" }
        return v >= 1000
            ? String(format: "%.0f", v)
            : String(format: "%.2f", v)
    }

    static func pct(_ v: Double?) -> String {
        guard let v else { return "—" }
        return String(format: "%+.2f%%", v)
    }

    /// Signed, compact rupee amount using Indian units (k / L / Cr). e.g. +₹1.26L, -₹9.2k.
    static func rupeeShort(_ v: Double?) -> String {
        guard let v else { return "—" }
        let a = abs(v), sign = v < 0 ? "-" : "+"
        if a >= 1e7 { return "\(sign)₹\(String(format: "%.2f", a / 1e7))Cr" }
        if a >= 1e5 { return "\(sign)₹\(String(format: "%.2f", a / 1e5))L" }
        if a >= 1e3 { return "\(sign)₹\(String(format: "%.1f", a / 1e3))k" }
        return "\(sign)₹\(Int(a))"
    }
}
