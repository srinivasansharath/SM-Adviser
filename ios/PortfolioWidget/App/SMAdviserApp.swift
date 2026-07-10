import SwiftUI

@main
struct SMAdviserApp: App {
    init() {
        // Test hook: auto-configure from launch env (used by Simulator E2E). Harmless in prod.
        let env = ProcessInfo.processInfo.environment
        if let url = env["SMA_SERVER_URL"], !url.isEmpty, !SettingsStore.isConfigured {
            SettingsStore.save(ServerSettings(baseURL: url, token: env["SMA_TOKEN"] ?? ""))
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
