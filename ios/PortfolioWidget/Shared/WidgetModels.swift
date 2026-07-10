import Foundation

/// Mirrors the backend widget.json. Decoded with .convertFromSnakeCase, so property names are camelCase.
struct WidgetData: Codable {
    let asOf: String?
    let headline: String?
    let portfolio: Portfolio
    let holdings: [Holding]

    static let sample = WidgetData(
        asOf: "2026-07-10T08:00:00+05:30",
        headline: "Portfolio concentrated; two names on watch.",
        portfolio: Portfolio(value: 292119, dayChangePct: 1.30, totalPnl: 127172, attentionCount: 3),
        holdings: [
            Holding(symbol: "YESBANK", name: "Yes Bank", ltp: 23.9, changePct: 1.18, classification: "Hold", confidence: "High", thesisStatus: "watch", flag: "risk", flagReason: nil),
            Holding(symbol: "TATACHEM", name: "Tata Chemicals", ltp: 722.9, changePct: 1.14, classification: "Trim Candidate", confidence: "High", thesisStatus: "watch", flag: "risk", flagReason: nil),
            Holding(symbol: "SBIN", name: "State Bank", ltp: 1035.8, changePct: 1.34, classification: "Hold", confidence: "High", thesisStatus: "intact", flag: "ok", flagReason: nil),
            Holding(symbol: "TCS", name: "TCS", ltp: 2074.4, changePct: 1.21, classification: "Hold", confidence: "High", thesisStatus: "intact", flag: "risk", flagReason: nil),
            Holding(symbol: "SEPC", name: "SEPC", ltp: 6.55, changePct: 1.39, classification: "Trim Candidate", confidence: "High", thesisStatus: "impaired", flag: "risk", flagReason: nil),
        ]
    )
}

struct Portfolio: Codable {
    let value: Double
    let dayChangePct: Double?
    let totalPnl: Double?
    let attentionCount: Int?
}

struct Holding: Codable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let name: String?
    let ltp: Double?
    let changePct: Double?
    let classification: String?
    let confidence: String?
    let thesisStatus: String?
    let flag: String?
    let flagReason: String?
}
