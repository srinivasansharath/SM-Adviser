import SwiftUI

/// "NIFTY 50 -1.92% · +0.52% vs mkt" — how the market moved, and how the portfolio did against it.
///
/// Two deliberate choices:
/// - the index move is neutral-coloured, because it is context, not your money;
/// - the vs-market delta is tinted by *relative* performance, so beating a falling market reads
///   green even on a day when every row on the screen is red. That is the whole point of the line:
///   answering "is everything down, or just my stocks?" without opening another app.
struct MarketLine: View {
    let market: Market?
    var size: CGFloat = 9
    /// The widget has room for the primary benchmark only; the app shows every configured index.
    var allIndices = false
    /// Small-widget mode: one number only. The vs-market delta carries more meaning per character
    /// than the index level, so it wins when both would not fit.
    var compact = false

    private var shown: [MarketIndex] {
        let list = market?.list ?? []
        return allIndices ? list : Array(list.prefix(1))
    }

    private var style: Font { .system(size: size, weight: .medium, design: .rounded) }

    var body: some View {
        if compact {
            if let vs = market?.vsMarketPct {
                Text("\(Style.pct(vs)) vs mkt")
                    .font(style).monospacedDigit().lineLimit(1).minimumScaleFactor(0.7)
                    .foregroundStyle(vs >= 0 ? Color.green : Color.red)
            } else if let idx = shown.first {
                Text("\(idx.name) \(Style.pct(idx.dayChangePct))")
                    .font(style).monospacedDigit().lineLimit(1).minimumScaleFactor(0.7)
                    .foregroundStyle(.secondary)
            }
        } else if !shown.isEmpty {
            HStack(spacing: 4) {
                ForEach(shown) { idx in
                    Text("\(idx.name) \(Style.pct(idx.dayChangePct))")
                        .foregroundStyle(.secondary)
                }
                if let vs = market?.vsMarketPct {
                    Text("·").foregroundStyle(.secondary)
                    Text("\(Style.pct(vs)) vs mkt")
                        .foregroundStyle(vs >= 0 ? Color.green : Color.red)
                }
            }
            .font(style)
            .monospacedDigit()
            .lineLimit(1)
            .minimumScaleFactor(0.7)
        }
    }
}
