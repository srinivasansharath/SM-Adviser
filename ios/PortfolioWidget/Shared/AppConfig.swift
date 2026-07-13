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
    }

    static var isConfigured: Bool { load() != nil }
    static var token: String { load()?.token ?? "" }
    static var widgetURL: URL? { load().flatMap { URL(string: $0.baseURL + "/widget.json") } }
    static var healthURL: URL? { load().flatMap { URL(string: $0.baseURL + "/health") } }
    static var reportURL: URL? { load().flatMap { URL(string: $0.baseURL + "/report/latest") } }

    /// URL of the server-rendered analysis one-pager for a holding.
    static func stockURL(_ symbol: String) -> URL? {
        guard let base = load()?.baseURL else { return nil }
        let enc = symbol.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? symbol
        return URL(string: base + "/stock/" + enc)
    }
}
