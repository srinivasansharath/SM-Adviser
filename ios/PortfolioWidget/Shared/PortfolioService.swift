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
            let decoded = try decoder.decode(WidgetData.self, from: data)
            SettingsStore.cachedWidget = data     // remember the last good payload
            return (decoded, nil)
        } catch {
            return (nil, error.localizedDescription)
        }
    }

    /// Last successfully-fetched portfolio (from the App Group cache), for instant display on
    /// launch and as a fallback when a refresh is slow or fails. nil in demo mode / when uncached.
    static func cached() -> WidgetData? {
        guard !SettingsStore.isDemo, let data = SettingsStore.cachedWidget else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(WidgetData.self, from: data)
    }

    /// Weekly new-stock shortlist (GET /candidates.json). Demo sample in demo mode; falls back to
    /// the cached list when offline / the refresh fails, so the table survives a flaky link.
    static func fetchCandidates() async -> [CandidateData] {
        if SettingsStore.isDemo { return CandidateData.sample }
        guard SettingsStore.serverHas("screening"), let url = SettingsStore.candidatesJSONURL else {
            return cachedCandidates()
        }
        var req = URLRequest(url: url); req.timeoutInterval = 15
        authorize(&req)
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let decoded = try? JSONDecoder.snake.decode(CandidatesData.self, from: data) else {
            return cachedCandidates()
        }
        SettingsStore.cachedCandidates = data
        return decoded.candidates
    }

    /// Last successfully-fetched shortlist (App Group cache), for instant display on launch.
    static func cachedCandidates() -> [CandidateData] {
        guard !SettingsStore.isDemo, let data = SettingsStore.cachedCandidates,
              let d = try? JSONDecoder.snake.decode(CandidatesData.self, from: data) else { return [] }
        return d.candidates
    }

    /// Fetch /meta (capabilities + version) and cache the advertised features. Best-effort.
    @discardableResult
    static func refreshMeta() async -> ServerMeta? {
        guard !SettingsStore.isDemo, let url = SettingsStore.metaURL else { return nil }
        var req = URLRequest(url: url); req.timeoutInterval = 10
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let meta = try? JSONDecoder.snake.decode(ServerMeta.self, from: data) else { return nil }
        SettingsStore.features = meta.features
        return meta
    }

    /// All theses for the connected portfolio (GET /theses).
    static func fetchTheses() async -> [ThesisData]? {
        guard let url = SettingsStore.thesesURL else { return nil }
        var req = URLRequest(url: url); req.timeoutInterval = 15
        authorize(&req)
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONDecoder.snake.decode([ThesisData].self, from: data)
    }

    /// Save one thesis (PUT /theses/{symbol}). Returns nil on success, else an error string.
    static func putThesis(_ symbol: String, _ body: ThesisUpsert) async -> String? {
        guard let url = SettingsStore.thesisURL(symbol) else { return "Not connected" }
        var req = URLRequest(url: url); req.httpMethod = "PUT"; req.timeoutInterval = 15
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&req)
        req.httpBody = try? JSONEncoder.snake.encode(body)
        guard let (_, resp) = try? await URLSession.shared.data(for: req) else { return "No response" }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 200 { return nil }
        if code == 401 { return "The token was rejected (401)" }
        return "Server returned HTTP \(code)"
    }

    private static func authorize(_ req: inout URLRequest) {
        let token = SettingsStore.token
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
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
