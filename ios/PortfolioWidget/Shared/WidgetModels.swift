import Foundation

/// Mirrors the backend widget.json. Decoded with .convertFromSnakeCase, so property names are camelCase.
struct WidgetData: Codable {
    let asOf: String?
    let pricesAsOf: String?   // set by the intraday refresh; nil on a fresh daily-only run
    let headline: String?
    let portfolio: Portfolio
    let holdings: [Holding]

    static let sample = WidgetData(
        asOf: "2026-07-13T08:00:00+05:30",
        pricesAsOf: "2026-07-13T12:34:00+05:30",
        headline: "Portfolio concentrated; two names on watch.",
        portfolio: Portfolio(value: 291881, dayChangePct: 1.28, totalPnl: 126934, totalReturnPct: 76.9, attentionCount: 3),
        holdings: [
            Holding(symbol: "YESBANK", name: "Yes Bank", ltp: 23.9, changePct: 1.23, ret20d: 4.1, ret252d: 32.0, returnPct: 88.4, pnl: 42300, classification: "Hold", confidence: "High", thesisStatus: "watch", flag: "risk", flagReason: nil),
            Holding(symbol: "TATACHEM", name: "Tata Chemicals", ltp: 721.0, changePct: 1.03, ret20d: -3.2, ret252d: -14.5, returnPct: 148.2, pnl: 46600, classification: "Exit Candidate", confidence: "High", thesisStatus: "impaired", flag: "risk", flagReason: nil),
            Holding(symbol: "SBIN", name: "State Bank", ltp: 1035.8, changePct: 1.34, ret20d: 2.6, ret252d: 21.3, returnPct: 456.8, pnl: 38900, classification: "Hold", confidence: "High", thesisStatus: "intact", flag: "ok", flagReason: nil),
            Holding(symbol: "TCS", name: "TCS", ltp: 2074.4, changePct: 1.21, ret20d: -1.4, ret252d: 8.7, returnPct: -4.98, pnl: -1800, classification: "Hold", confidence: "High", thesisStatus: "intact", flag: "risk", flagReason: nil),
            Holding(symbol: "SEPC", name: "SEPC", ltp: 6.55, changePct: 1.39, ret20d: -8.0, ret252d: -22.0, returnPct: -43.34, pnl: -9200, classification: "Trim Candidate", confidence: "High", thesisStatus: "impaired", flag: "risk", flagReason: nil),
        ]
    )
}

struct Portfolio: Codable {
    let value: Double
    let dayChangePct: Double?
    let totalPnl: Double?
    let totalReturnPct: Double?   // return since purchase, whole portfolio
    let attentionCount: Int?
}

struct Holding: Codable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let name: String?
    let ltp: Double?
    let changePct: Double?   // today
    let ret20d: Double?      // ~1 month
    let ret252d: Double?     // ~1 year
    let returnPct: Double?   // since purchase %
    let pnl: Double?         // since purchase ₹ gain
    let classification: String?
    let confidence: String?
    let thesisStatus: String?
    let flag: String?
    let flagReason: String?
}
