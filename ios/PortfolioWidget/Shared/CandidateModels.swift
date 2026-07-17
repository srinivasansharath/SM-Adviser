import Foundation

/// Mirrors one entry of GET /candidates.json — a weekly buy-candidate from the screener.
/// Decoded with .convertFromSnakeCase (so exit_if -> exitIf); dictionary keys (metrics/subscores)
/// keep their server spelling since that strategy only rewrites struct property names.
struct CandidateData: Codable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let rank: Int?
    let composite: Double?
    let sector: String?
    let industry: String?
    let buckets: [String]
    let verdict: String?        // strong | watch | avoid
    let conviction: String?     // high | medium | low
    let thesis: String?
    let tailwind: String?
    let exitIf: [String]
    let risks: [String]
    let subscores: [String: Double]
    let metrics: [String: Double]

    /// Illustrative sample for demo mode (generic names + a sector mix — not real recommendations).
    static let sample: [CandidateData] = [
        _s("ACME INDS", 88, "Industrials", "Electrical Equipment", ["Compounder", "GARP"], "strong", "high",
           "Capital-efficient franchise with consistent double-digit returns and durable, self-funded growth.",
           "formalization of a fragmented category"),
        _s("VOLTEDGE", 84, "Industrials", "Capital Goods", ["Compounder"], "watch", "medium",
           "Grid-equipment maker riding the T&D capex cycle; strong returns but order lumpiness.",
           "power grid capex"),
        _s("NOVA TECH", 81, "Information Technology", "IT - Software", ["GARP", "Tailwind"], "strong", "medium",
           "Fast grower at a reasonable price; execution good, but unproven across a downturn.",
           "digital adoption in mid-market enterprises"),
        _s("BYTEWORKS", 76, "Information Technology", "IT - Services", ["GARP"], "watch", "low",
           "Niche services player with improving margins; client concentration is the key risk.",
           "none"),
        _s("MERIDIAN FIN", 83, "Financial Services", "NBFC", ["Compounder", "GARP"], "watch", "medium",
           "Well-underwritten lender compounding book value; sensitive to the rate cycle.",
           "financialization of household savings"),
        _s("TRUST BANK", 79, "Financial Services", "Private Sector Bank", ["Compounder"], "watch", "low",
           "Steady deposit franchise; valuation fair but growth is mid-single-digit.",
           "none"),
    ]

    private static func _s(_ sym: String, _ comp: Double, _ sector: String, _ industry: String,
                           _ buckets: [String], _ verdict: String, _ conviction: String,
                           _ thesis: String, _ tailwind: String) -> CandidateData {
        CandidateData(symbol: sym, rank: nil, composite: comp, sector: sector, industry: industry,
                      buckets: buckets, verdict: verdict, conviction: conviction,
                      thesis: "Illustrative sample: " + thesis, tailwind: tailwind,
                      exitIf: ["quality/returns deteriorate for two years", "leverage or pledge rises materially"],
                      risks: ["execution risk", "sector/cyclical risk"],
                      subscores: ["quality": comp - 4, "growth": comp, "durability": comp - 6,
                                  "valuation": comp - 20, "safety": comp - 2, "liquidity": comp - 10],
                      metrics: ["roe": 24, "roe_5y": 21, "roce": 28, "pe": 30, "peg": 1.1])
    }
}

/// GET /candidates.json envelope.
struct CandidatesData: Codable {
    let runDate: String?
    let universe: Int?
    let candidates: [CandidateData]
}
