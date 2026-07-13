import Foundation

/// The horizon the middle column shows. Shared by the app (segmented picker) and the
/// widget (tap-to-cycle), persisted in the App Group so both stay in sync.
enum Period: Int, CaseIterable, Identifiable {
    case today, month, year

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .today: return "Today"
        case .month: return "1M"
        case .year:  return "1Y"
        }
    }

    var next: Period { Period(rawValue: (rawValue + 1) % Period.allCases.count) ?? .today }

    /// The holding's return over this horizon (nil when the backend has no value yet).
    func value(_ h: Holding) -> Double? {
        switch self {
        case .today: return h.changePct
        case .month: return h.ret20d
        case .year:  return h.ret252d
        }
    }
}

/// Persists the selected period in the shared App Group container.
enum PeriodStore {
    static let key = "selected_period"
    private static var defaults: UserDefaults { UserDefaults(suiteName: AppConfig.appGroup) ?? .standard }

    static var current: Period {
        get { Period(rawValue: defaults.integer(forKey: key)) ?? .today }
        set { defaults.set(newValue.rawValue, forKey: key) }
    }

    static func cycle() { current = current.next }
}
