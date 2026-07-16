import Foundation

/// Mirrors one entry of GET /candidates.json — a weekly buy-candidate from the screener.
/// Decoded with .convertFromSnakeCase (so exit_if -> exitIf); dictionary keys (metrics/subscores)
/// keep their server spelling since that strategy only rewrites struct property names.
struct CandidateData: Codable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let rank: Int?
    let composite: Double?
    let buckets: [String]
    let verdict: String?        // strong | watch | avoid
    let conviction: String?     // high | medium | low
    let thesis: String?
    let tailwind: String?
    let exitIf: [String]
    let risks: [String]
    let subscores: [String: Double]
    let metrics: [String: Double]

    /// Illustrative sample for demo mode (generic names — not real recommendations).
    static let sample: [CandidateData] = [
        CandidateData(symbol: "ACME INDS", rank: 1, composite: 88, buckets: ["Compounder", "GARP"],
            verdict: "strong", conviction: "high",
            thesis: "Illustrative sample: a capital-efficient franchise with consistent double-digit returns and durable, self-funded growth.",
            tailwind: "formalization of a fragmented category",
            exitIf: ["ROE falls below 18% for two years", "promoter pledge rises above 15%"],
            risks: ["demand cyclicality", "input-cost inflation"],
            subscores: ["quality": 90, "growth": 82, "durability": 86, "valuation": 62, "safety": 95, "liquidity": 78],
            metrics: ["roe": 28, "roe_5y": 26, "roce": 34, "pe": 32, "peg": 1.1]),
        CandidateData(symbol: "NOVA TECH", rank: 2, composite: 81, buckets: ["GARP", "Tailwind"],
            verdict: "watch", conviction: "medium",
            thesis: "Illustrative sample: fast grower at a reasonable price, but the growth is early-cycle and unproven across a downturn.",
            tailwind: "digital adoption in mid-market enterprises",
            exitIf: ["revenue growth stalls below 12%", "margins compress on competition"],
            risks: ["competitive intensity", "key-client concentration"],
            subscores: ["quality": 78, "growth": 90, "durability": 74, "valuation": 80, "safety": 70, "liquidity": 66],
            metrics: ["roe": 22, "roe_5y": 19, "roce": 24, "pe": 28, "peg": 0.9]),
        CandidateData(symbol: "TERRA POWER", rank: 3, composite: 72, buckets: ["Tailwind"],
            verdict: "watch", conviction: "low",
            thesis: "Illustrative sample: rides a strong sector capex tailwind, but returns are cyclical and the valuation already prices in continued momentum.",
            tailwind: "grid / infrastructure capex cycle",
            exitIf: ["order inflow slows for two quarters", "leverage rises above 1.5x"],
            risks: ["commodity/cyclical earnings", "execution and working-capital risk"],
            subscores: ["quality": 66, "growth": 84, "durability": 58, "valuation": 52, "safety": 60, "liquidity": 88],
            metrics: ["roe": 14, "roe_5y": 11, "roce": 13, "pe": 40, "peg": 1.6]),
    ]
}

/// GET /candidates.json envelope.
struct CandidatesData: Codable {
    let runDate: String?
    let universe: Int?
    let candidates: [CandidateData]
}
