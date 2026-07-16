import SwiftUI
import WidgetKit

/// Branches on whether the user has connected a server yet (Home-Assistant style).
struct ContentView: View {
    @State private var configured = SettingsStore.isConfigured || SettingsStore.isDemo

    var body: some View {
        NavigationStack {
            if configured {
                DashboardView(onDisconnect: {
                    SettingsStore.clear()
                    WidgetCenter.shared.reloadAllTimelines()
                    configured = false
                })
            } else {
                SetupView(onConnected: { configured = true })
            }
        }
    }
}

/// Shows the portfolio pulled from the connected server + lets you refresh / disconnect.
struct DashboardView: View {
    var onDisconnect: () -> Void

    // Seed from the last cached payload (or the demo sample) so the dashboard shows instantly on
    // launch instead of a blank spinner, then refreshes in the background.
    @State private var data: WidgetData? = SettingsStore.isDemo ? .sample : PortfolioService.cached()
    @State private var candidates: [CandidateData] = SettingsStore.isDemo ? CandidateData.sample : PortfolioService.cachedCandidates()
    @State private var error: String?
    @State private var loading = false
    @State private var refreshFailed = false
    // Shared with the widget via the App Group, so the picker and the widget stay in sync.
    @AppStorage(PeriodStore.key, store: UserDefaults(suiteName: AppConfig.appGroup))
    private var periodRaw = 0
    private var period: Period { Period(rawValue: periodRaw) ?? .today }

    var body: some View {
        List {
            Section {
                if loading && data == nil {
                    HStack { ProgressView(); Text("Fetching…").foregroundStyle(.secondary) }
                } else if let error, data == nil {
                    Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                } else if let data {
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Portfolio").bold()
                            Text("₹\(Int(data.portfolio.value).formatted())").font(.title3).monospacedDigit()
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            if let tr = data.portfolio.totalReturnPct {
                                Text("\(Style.pct(tr)) total").bold()
                                    .foregroundStyle(tr >= 0 ? .green : .red)
                            }
                            Text("\(Style.pct(data.portfolio.dayChangePct)) today").font(.caption)
                                .foregroundStyle((data.portfolio.dayChangePct ?? 0) >= 0 ? .green : .red)
                        }
                    }
                    if let h = data.headline { Text(h).font(.footnote).foregroundStyle(.secondary) }
                    let t = MarketClock.shortTime(data.pricesAsOf)
                    if !t.isEmpty {
                        Text("Prices as of \(t) IST").font(.caption2).foregroundStyle(.secondary)
                    }
                    if refreshFailed {
                        Label("Couldn't refresh — showing last update", systemImage: "wifi.exclamationmark")
                            .font(.caption2).foregroundStyle(.orange)
                    }
                }
            }

            if let data {
                Section {
                    Picker("Period", selection: $periodRaw) {
                        Text("Today").tag(0)
                        Text("1 Month").tag(1)
                        Text("1 Year").tag(2)
                    }
                    .pickerStyle(.segmented)

                    ForEach(data.holdings) { h in
                        NavigationLink {
                            StockDetailView(symbol: h.symbol)
                        } label: {
                        HStack(spacing: 8) {
                            Circle().fill(Style.color(classification: h.classification, flag: h.flag)).frame(width: 8, height: 8)
                            VStack(alignment: .leading) {
                                Text(h.symbol).bold()
                                Text(h.classification ?? h.flag ?? "").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            // Selected-period return + current price
                            VStack(alignment: .trailing, spacing: 1) {
                                Text(Style.pct(period.value(h))).font(.subheadline).monospacedDigit()
                                    .foregroundStyle((period.value(h) ?? 0) >= 0 ? .green : .red)
                                    .lineLimit(1).minimumScaleFactor(0.6)
                                Text("₹\(Style.price(h.ltp))").font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                            }.frame(width: 78, alignment: .trailing)
                            // Since-purchase return % + ₹ gain
                            VStack(alignment: .trailing, spacing: 1) {
                                Text(Style.pct(h.returnPct)).font(.subheadline).bold().monospacedDigit()
                                    .foregroundStyle((h.returnPct ?? 0) >= 0 ? .green : .red)
                                    .lineLimit(1).minimumScaleFactor(0.6)
                                Text(Style.rupeeShort(h.pnl)).font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                                    .lineLimit(1).minimumScaleFactor(0.7)
                            }.frame(width: 84, alignment: .trailing)
                        }
                        }
                    }
                } header: {
                    HStack {
                        Text("Holdings"); Spacer(); Text("\(period.label)  ·  Since buy")
                    }
                }
            }

            // New-stock ideas — a native table below holdings; tap "View full analysis" for the
            // full server-rendered one-pager. Hidden when the server has no shortlist.
            if !candidates.isEmpty {
                Section {
                    ForEach(candidates.prefix(10)) { c in CandidateRow(candidate: c) }
                    NavigationLink {
                        NewStockIdeasView()
                    } label: {
                        Label("View full analysis", systemImage: "sparkle.magnifyingglass")
                    }
                } header: {
                    HStack { Text("New-stock ideas"); Spacer(); Text("weekly") }
                }
            }

            Section {
                NavigationLink {
                    WebReportView(title: "Daily Report", url: SettingsStore.reportURL, pdfName: "SM Adviser Report")
                } label: {
                    Label("Full report (view / share)", systemImage: "doc.text")
                }
                Button { Task { await load() } } label: { Label("Refresh now", systemImage: "arrow.clockwise") }
                Button { WidgetCenter.shared.reloadAllTimelines() } label: {
                    Label("Reload home-screen widgets", systemImage: "square.grid.2x2")
                }
                Button(role: .destructive) { onDisconnect() } label: {
                    Label("Disconnect server", systemImage: "xmark.circle")
                }
            }
        }
        .navigationTitle("SM Adviser")
        .task { await load() }
        .onChange(of: periodRaw) { WidgetCenter.shared.reloadAllTimelines() }
    }

    private func load() async {
        if data == nil { loading = true }      // spinner only when there's nothing cached to show
        error = nil; refreshFailed = false
        await PortfolioService.refreshMeta()   // capability negotiation (gates the thesis editor etc.)
        let r = await PortfolioService.fetch()
        loading = false
        if let fresh = r.data {
            data = fresh                        // replace with the fresh snapshot
        } else if data == nil {
            error = r.error                     // nothing cached -> surface the error
        } else {
            refreshFailed = true                // keep the cached view, just flag the failed refresh
        }
        candidates = await PortfolioService.fetchCandidates()   // weekly buy-candidate shortlist
    }
}

/// One row in the New-stock ideas table: symbol + buckets, with the composite score and a
/// colour-coded verdict (green strong / amber watch / red avoid).
struct CandidateRow: View {
    let candidate: CandidateData

    private var verdictColor: Color {
        switch candidate.verdict {
        case "strong": return .green
        case "avoid": return .red
        default: return .orange
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(verdictColor).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(candidate.symbol).bold()
                if !candidate.buckets.isEmpty {
                    Text(candidate.buckets.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 1) {
                if let c = candidate.composite {
                    Text("\(Int(c))").font(.subheadline).bold().monospacedDigit()
                }
                if let v = candidate.verdict {
                    Text(v.capitalized).font(.caption2).foregroundStyle(verdictColor)
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
