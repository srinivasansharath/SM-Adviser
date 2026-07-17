import Foundation

/// Runtime server settings (Home-Assistant style): the app is generic; each user points it at
/// their OWN self-hosted SM Adviser server. Settings are entered on-device and shared with the
/// widget extension via an App Group (add the same group to both targets in Xcode).
enum AppConfig {
    /// App Group id — must be enabled (identical) on BOTH the app and widget targets.
    static let appGroup = "group.com.sharath.smadviser"
}

struct ServerSettings: Equatable {
    var baseURL: String
    var token: String
}

/// Reads/writes the server settings in the shared App Group container.
enum SettingsStore {
    private static let kURL = "server_base_url"
    private static let kToken = "server_token"
    private static let kDemo = "demo_mode"
    // Shared App Group container; falls back to standard defaults if the group isn't provisioned
    // (e.g. an unsigned Simulator build) so the container app still works for testing.
    private static var defaults: UserDefaults { UserDefaults(suiteName: AppConfig.appGroup) ?? .standard }

    static func load() -> ServerSettings? {
        let d = defaults
        guard let url = d.string(forKey: kURL), !url.isEmpty else { return nil }
        return ServerSettings(baseURL: url, token: d.string(forKey: kToken) ?? "")
    }

    static func save(_ s: ServerSettings) {
        defaults.set(s.baseURL, forKey: kURL)
        defaults.set(s.token, forKey: kToken)
    }

    static func clear() {
        defaults.removeObject(forKey: kURL)
        defaults.removeObject(forKey: kToken)
        defaults.removeObject(forKey: kDemo)
        defaults.removeObject(forKey: kFeatures)
        defaults.removeObject(forKey: kCache)
        defaults.removeObject(forKey: kCacheAt)
        defaults.removeObject(forKey: kCandCache)
    }

    // Last successfully-fetched widget.json, so the dashboard shows instantly on launch and
    // survives a slow/failed refresh (stale-while-revalidate) instead of going blank. Cleared on
    // disconnect so a stale portfolio never lingers for a server you're no longer connected to.
    private static let kCache = "cached_widget"
    static var cachedWidget: Data? {
        get { defaults.data(forKey: kCache) }
        set {
            if let v = newValue { defaults.set(v, forKey: kCache) } else { defaults.removeObject(forKey: kCache) }
        }
    }

    // When the cached widget payload was last successfully fetched, so the app can show "Updated Xm ago".
    private static let kCacheAt = "cached_widget_at"
    static var cachedWidgetAt: Date? {
        get { let t = defaults.double(forKey: kCacheAt); return t > 0 ? Date(timeIntervalSince1970: t) : nil }
        set { defaults.set(newValue?.timeIntervalSince1970 ?? 0, forKey: kCacheAt) }
    }

    // Same idea for the weekly new-stock shortlist, so its table shows instantly on launch too.
    private static let kCandCache = "cached_candidates"
    static var cachedCandidates: Data? {
        get { defaults.data(forKey: kCandCache) }
        set {
            if let v = newValue { defaults.set(v, forKey: kCandCache) } else { defaults.removeObject(forKey: kCandCache) }
        }
    }

    /// Demo mode: preview the app with bundled sample data, no server (for onboarding / review).
    static var isDemo: Bool {
        get { defaults.bool(forKey: kDemo) }
        set { defaults.set(newValue, forKey: kDemo) }
    }

    static var isConfigured: Bool { load() != nil }
    static var token: String { load()?.token ?? "" }
    static var widgetURL: URL? { load().flatMap { URL(string: $0.baseURL + "/widget.json") } }
    static var healthURL: URL? { load().flatMap { URL(string: $0.baseURL + "/health") } }
    static var reportURL: URL? { load().flatMap { URL(string: $0.baseURL + "/report/latest") } }
    static var metaURL: URL? { load().flatMap { URL(string: $0.baseURL + "/meta") } }
    static var thesesURL: URL? { load().flatMap { URL(string: $0.baseURL + "/theses") } }
    static var candidatesURL: URL? { load().flatMap { URL(string: $0.baseURL + "/candidates") } }
    static var candidatesJSONURL: URL? { load().flatMap { URL(string: $0.baseURL + "/candidates.json") } }
    static var statusURL: URL? { load().flatMap { URL(string: $0.baseURL + "/status") } }

    static func thesisURL(_ symbol: String) -> URL? {
        guard let base = load()?.baseURL else { return nil }
        let enc = symbol.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? symbol
        return URL(string: base + "/theses/" + enc)
    }

    // Capabilities advertised by the connected server (/meta.features), for feature gating.
    private static let kFeatures = "server_features"
    static var features: [String] {
        get { defaults.stringArray(forKey: kFeatures) ?? [] }
        set { defaults.set(newValue, forKey: kFeatures) }
    }
    static func serverHas(_ feature: String) -> Bool { features.contains(feature) }

    /// URL of the server-rendered analysis one-pager for a holding.
    static func stockURL(_ symbol: String) -> URL? {
        guard let base = load()?.baseURL else { return nil }
        let enc = symbol.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? symbol
        return URL(string: base + "/stock/" + enc)
    }
}
