import SwiftUI

/// Operational health (GET /status): is the daily portfolio review healthy, is the weekly
/// new-stock screen healthy, and are the system + LLM budget OK — with any problems listed.
struct HealthView: View {
    @State private var status: StatusData?
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        List {
            if let status {
                Section {
                    HStack(spacing: 10) {
                        Circle().fill(color(status.status)).frame(width: 12, height: 12)
                        Text(status.status == "ok"
                             ? "All systems healthy"
                             : "\(status.issues.count) issue\(status.issues.count == 1 ? "" : "s") to look into")
                            .bold()
                    }
                }
                if !status.issues.isEmpty {
                    Section("Needs attention") {
                        ForEach(status.issues, id: \.self) { issue in
                            Label(issue, systemImage: "exclamationmark.triangle.fill")
                                .foregroundStyle(.orange).font(.subheadline)
                        }
                    }
                }
                serviceSection("Portfolio review", status.services.portfolioReview)
                serviceSection("New-stock recommendations", status.services.newStockScreen)
                systemSection(status.services.system)
            } else if loading {
                HStack { ProgressView(); Text("Checking…").foregroundStyle(.secondary) }
            } else if let error {
                Label(error, systemImage: "wifi.slash").foregroundStyle(.red)
            }
        }
        .navigationTitle("System health")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    @ViewBuilder
    private func serviceSection(_ title: String, _ svc: StatusData.ServiceHealth) -> some View {
        Section(title) {
            HStack {
                Circle().fill(color(svc.status)).frame(width: 8, height: 8)
                Text(statusLabel(svc.status)).font(.subheadline)
                Spacer()
                if let lr = svc.lastRun { Text("last run \(lr)").font(.caption).foregroundStyle(.secondary) }
            }
            ForEach(svc.connectors.sorted(by: { $0.key < $1.key }), id: \.key) { name, conn in
                HStack(alignment: .top, spacing: 8) {
                    Circle().fill(color(conn.status)).frame(width: 6, height: 6).padding(.top, 6)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(prettyName(name)).font(.subheadline)
                        if let d = conn.detail, !d.isEmpty {
                            Text(d).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func systemSection(_ sys: StatusData.SystemHealth) -> some View {
        Section("System") {
            HStack {
                Circle().fill(color(sys.database == "ok" ? "ok" : "degraded")).frame(width: 8, height: 8)
                Text("Database"); Spacer()
                Text(sys.database).font(.caption).foregroundStyle(.secondary)
            }
            let spend = sys.llm.usage.thisMonth.costUsd
            HStack {
                Text("AI spend (this month)"); Spacer()
                if let b = sys.llm.budget {
                    Text(String(format: "$%.2f / $%.0f", spend, b.monthlyUsd))
                        .foregroundStyle(b.overBudget ? .red : .secondary)
                } else {
                    Text(String(format: "$%.2f", spend)).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func color(_ status: String) -> Color {
        switch status {
        case "ok": return .green
        case "degraded": return .orange
        case "failed", "stale": return .red
        default: return .gray            // unknown, info
        }
    }

    private func statusLabel(_ s: String) -> String {
        switch s {
        case "ok": return "Healthy"
        case "degraded": return "Degraded"
        case "failed": return "Last run failed"
        case "stale": return "Not running on schedule"
        case "unknown": return "Not run yet"
        default: return s.capitalized
        }
    }

    private func prettyName(_ key: String) -> String {
        [
            "portfolio": "Holdings (Zerodha)", "market_data": "Market data",
            "fundamentals": "Fundamentals", "news": "News / filings", "order_flow": "Order flow",
            "universe": "Universe screen", "llm": "AI analysis",
        ][key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func load() async {
        if status == nil { loading = true }
        error = nil
        let s = await PortfolioService.fetchStatus()
        loading = false
        if let s { status = s } else if status == nil { error = "Couldn't load health status." }
    }
}
