import SwiftUI
import WidgetKit

/// Branches on whether the user has connected a server yet (Home-Assistant style).
struct ContentView: View {
    @State private var configured = SettingsStore.isConfigured

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

    @State private var data: WidgetData?
    @State private var error: String?
    @State private var loading = false

    var body: some View {
        List {
            Section {
                if loading {
                    HStack { ProgressView(); Text("Fetching…").foregroundStyle(.secondary) }
                } else if let error {
                    Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                } else if let data {
                    HStack {
                        Text("Portfolio").bold()
                        Spacer()
                        Text("₹\(Int(data.portfolio.value).formatted())").monospacedDigit()
                        Text(Style.pct(data.portfolio.dayChangePct))
                            .foregroundStyle((data.portfolio.dayChangePct ?? 0) >= 0 ? .green : .red)
                    }
                    if let h = data.headline { Text(h).font(.footnote).foregroundStyle(.secondary) }
                }
            }

            if let data {
                Section("Holdings") {
                    ForEach(data.holdings) { h in
                        HStack {
                            Circle().fill(Style.color(classification: h.classification, flag: h.flag)).frame(width: 8, height: 8)
                            VStack(alignment: .leading) {
                                Text(h.symbol).bold()
                                Text(h.classification ?? h.flag ?? "").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text("₹\(Style.price(h.ltp))").monospacedDigit()
                            Text(Style.pct(h.changePct)).font(.caption)
                                .foregroundStyle((h.changePct ?? 0) >= 0 ? .green : .red)
                        }
                    }
                }
            }

            Section {
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
    }

    private func load() async {
        loading = true; error = nil
        let r = await PortfolioService.fetch()
        data = r.data; error = r.error; loading = false
    }
}

#Preview {
    ContentView()
}
