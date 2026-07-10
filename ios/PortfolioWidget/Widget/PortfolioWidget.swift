import SwiftUI
import WidgetKit

struct PortfolioEntry: TimelineEntry {
    let date: Date
    let data: WidgetData?
    let error: String?
}

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> PortfolioEntry {
        PortfolioEntry(date: Date(), data: .sample, error: nil)
    }

    func getSnapshot(in context: Context, completion: @escaping (PortfolioEntry) -> Void) {
        // Previews/gallery use sample data to render instantly.
        completion(PortfolioEntry(date: Date(), data: .sample, error: nil))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<PortfolioEntry>) -> Void) {
        Task {
            let result = await PortfolioService.fetch()
            let entry = PortfolioEntry(date: Date(), data: result.data, error: result.error)
            // Refresh roughly hourly; the meaningful update is after the morning run.
            let next = Calendar.current.date(byAdding: .minute, value: 60, to: Date()) ?? Date().addingTimeInterval(3600)
            completion(Timeline(entries: [entry], policy: .after(next)))
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
            case .systemLarge: ListView(data: data, maxRows: 8)
            default: ListView(data: data, maxRows: 4)
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
