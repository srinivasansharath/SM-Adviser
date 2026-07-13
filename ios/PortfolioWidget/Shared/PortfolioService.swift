import Foundation

/// Fetches and decodes widget.json from the user's self-hosted server (settings via SettingsStore).
enum PortfolioService {
    static func fetch() async -> (data: WidgetData?, error: String?) {
        if SettingsStore.isDemo { return (WidgetData.sample, nil) }
        guard let url = SettingsStore.widgetURL else {
            return (nil, "Not connected. Open SM Adviser to add your server.")
        }
        var req = URLRequest(url: url)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.timeoutInterval = 15
        let token = SettingsStore.token
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            if let http = resp as? HTTPURLResponse, http.statusCode != 200 {
                return (nil, "Server returned HTTP \(http.statusCode)")
            }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return (try decoder.decode(WidgetData.self, from: data), nil)
        } catch {
            return (nil, error.localizedDescription)
        }
    }

    /// Used by the setup screen to confirm the entered server is reachable. Returns nil on success.
    static func validate() async -> String? {
        guard let url = SettingsStore.healthURL else { return "Enter a valid server URL" }
        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        let token = SettingsStore.token
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else { return "No response from server" }
            if http.statusCode == 200 { return nil }
            if http.statusCode == 401 { return "Connected, but the token was rejected (401)" }
            return "Server returned HTTP \(http.statusCode)"
        } catch {
            return error.localizedDescription
        }
    }
}
