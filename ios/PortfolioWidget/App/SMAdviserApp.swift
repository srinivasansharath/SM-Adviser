import SwiftUI

@main
struct SMAdviserApp: App {
    init() {
        // Test hook: auto-configure from launch env (used by Simulator E2E). Harmless in prod.
        let env = ProcessInfo.processInfo.environment
        if env["SMA_RESET"] == "1" { SettingsStore.clear() }          // screenshot: setup screen
        if env["SMA_DEMO"] == "1" { SettingsStore.isDemo = true }      // screenshot: demo data
        if let url = env["SMA_SERVER_URL"], !url.isEmpty, !SettingsStore.isConfigured {
            SettingsStore.save(ServerSettings(baseURL: url, token: env["SMA_TOKEN"] ?? ""))
        }
    }

    var body: some Scene {
        WindowGroup {
            if ProcessInfo.processInfo.environment["SMA_SCREEN"] == "stock" {
                NavigationStack { StockDetailView(symbol: "TATACHEM") }   // screenshot: analysis page
            } else {
                ContentView()
            }
        }
    }
}
