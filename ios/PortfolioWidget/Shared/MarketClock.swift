import Foundation

/// NSE market-hours awareness, used to pace the widget's refresh (brisk while the market is
/// open, relaxed otherwise so we stay within WidgetKit's reload budget) and to show an "as of" time.
enum MarketClock {
    static let ist = TimeZone(identifier: "Asia/Kolkata") ?? .current

    private static var istCalendar: Calendar {
        var c = Calendar(identifier: .gregorian); c.timeZone = ist; return c
    }

    static func isMarketHours(_ date: Date = Date()) -> Bool {
        let c = istCalendar.dateComponents([.weekday, .hour, .minute], from: date)
        guard let wd = c.weekday, (2...6).contains(wd) else { return false }  // Mon=2 … Fri=6
        let mins = (c.hour ?? 0) * 60 + (c.minute ?? 0)
        return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
    }

    /// Next timeline refresh: every 15 min while the market is open, every 90 min otherwise.
    static func nextRefresh(after date: Date = Date()) -> Date {
        let minutes = isMarketHours(date) ? 15 : 90
        return Calendar.current.date(byAdding: .minute, value: minutes, to: date)
            ?? date.addingTimeInterval(Double(minutes * 60))
    }

    /// "12:34" in IST from an ISO-8601 timestamp; empty string if it can't be parsed.
    static func shortTime(_ iso: String?) -> String {
        guard let iso else { return "" }
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime]
        guard let d = parser.date(from: iso) else { return "" }
        let f = DateFormatter(); f.timeZone = ist; f.dateFormat = "HH:mm"
        return f.string(from: d)
    }
}
