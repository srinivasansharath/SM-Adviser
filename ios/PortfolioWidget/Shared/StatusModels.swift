import Foundation

/// Mirrors GET /status — operational health for the two jobs + system. Decoded with
/// .convertFromSnakeCase, so portfolio_review -> portfolioReview, cost_usd -> costUsd, etc.
struct StatusData: Codable {
    let status: String            // ok | degraded
    let issues: [String]
    let services: Services

    struct Services: Codable {
        let portfolioReview: ServiceHealth
        let newStockScreen: ServiceHealth
        let system: SystemHealth
    }

    struct ServiceHealth: Codable {
        let status: String        // ok | degraded | failed | stale | unknown
        let lastRun: String?
        let ageDays: Int?
        let connectors: [String: ConnectorHealth]
    }

    struct ConnectorHealth: Codable {
        let source: String?
        let status: String        // ok | degraded | info
        let detail: String?
    }

    struct SystemHealth: Codable {
        let database: String
        let llm: LLMHealth
    }

    struct LLMHealth: Codable {
        let usage: LLMUsage
        let budget: LLMBudget?
    }

    struct LLMUsage: Codable { let thisMonth: LLMAgg }
    struct LLMAgg: Codable { let costUsd: Double }
    struct LLMBudget: Codable {
        let monthlyUsd: Double
        let spentUsd: Double
        let remainingUsd: Double
        let overBudget: Bool
    }

    static let sample = StatusData(
        status: "ok", issues: [],
        services: Services(
            portfolioReview: ServiceHealth(status: "ok", lastRun: "2026-07-17", ageDays: 0, connectors: [
                "portfolio": ConnectorHealth(source: "zerodha", status: "ok", detail: "6 holdings"),
                "market_data": ConnectorHealth(source: "yfinance", status: "ok", detail: "6/6 with metrics"),
                "news": ConnectorHealth(source: "bse", status: "ok", detail: "6/6 with filings"),
            ]),
            newStockScreen: ServiceHealth(status: "ok", lastRun: "2026-07-14", ageDays: 3, connectors: [
                "universe": ConnectorHealth(source: "screener", status: "ok", detail: "2451 names"),
                "llm": ConnectorHealth(source: "anthropic", status: "ok", detail: "11 assessed"),
            ]),
            system: SystemHealth(database: "ok",
                                 llm: LLMHealth(usage: LLMUsage(thisMonth: LLMAgg(costUsd: 0.42)),
                                                budget: LLMBudget(monthlyUsd: 10, spentUsd: 0.42,
                                                                  remainingUsd: 9.58, overBudget: false)))
        ))
}
