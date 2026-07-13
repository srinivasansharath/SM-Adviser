import SwiftUI
import WidgetKit

struct PortfolioEntry: TimelineEntry {
    let date: Date
    let data: WidgetData?
    let error: String?
    let period: Period
}

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> PortfolioEntry {
        PortfolioEntry(date: Date(), data: .sample, error: nil, period: PeriodStore.current)
    }

    func getSnapshot(in context: Context, completion: @escaping (PortfolioEntry) -> Void) {
        // Previews/gallery use sample data to render instantly.
        completion(PortfolioEntry(date: Date(), data: .sample, error: nil, period: PeriodStore.current))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<PortfolioEntry>) -> Void) {
        Task {
            let result = await PortfolioService.fetch()
            let entry = PortfolioEntry(date: Date(), data: result.data, error: result.error, period: PeriodStore.current)
            // Brisk (~15 min) while the market is open so "today" stays near-live; relaxed otherwise.
            completion(Timeline(entries: [entry], policy: .after(MarketClock.nextRefresh())))
        }
    }
}

struct PortfolioWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: PortfolioEntry

    var body: some View {
        if let data = entry.data {
            switch family {
            case .systemSmall: SmallView(data: data)
            case .systemLarge: ListView(data: data, period: entry.period, maxRows: 8)
            default: ListView(data: data, period: entry.period, maxRows: 4)
            }
        } else {
            ErrorView(message: entry.error ?? "No data")
        }
    }
}

struct PortfolioWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "PortfolioWidget", provider: Provider()) { entry in
            PortfolioWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("SM Adviser")
        .description("Your portfolio with Hold / Watch / Trim / Exit signals.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@main
struct PortfolioWidgetBundle: WidgetBundle {
    var body: some Widget {
        PortfolioWidget()
    }
}
