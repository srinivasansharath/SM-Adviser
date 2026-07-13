import AppIntents
import WidgetKit

/// Tapping the period label on the widget cycles Today → 1M → 1Y. WidgetKit reloads the
/// timeline after the intent runs, so the middle column re-renders with the new horizon.
struct CyclePeriodIntent: AppIntent {
    static var title: LocalizedStringResource = "Cycle period"
    static var isDiscoverable: Bool = false

    func perform() async throws -> some IntentResult {
        PeriodStore.cycle()
        WidgetCenter.shared.reloadAllTimelines()
        return .result()
    }
}
