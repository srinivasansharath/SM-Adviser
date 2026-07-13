import SwiftUI
import WidgetKit

/// Colored percentage text used in the period + since-purchase columns.
struct PctText: View {
    let pct: Double?
    var size: CGFloat = 12
    var weight: Font.Weight = .semibold
    var body: some View {
        Text(Style.pct(pct))
            .font(.system(size: size, weight: weight, design: .rounded))
            .foregroundStyle((pct ?? 0) >= 0 ? Color.green : Color.red)
            .monospacedDigit()
            .lineLimit(1)
            .minimumScaleFactor(0.6)   // shrink rather than wrap large returns like +636.92%
    }
}

private let kCol: CGFloat = 74   // fixed width for the two trailing columns (keeps them aligned)

struct HoldingRow: View {
    let h: Holding
    let period: Period
    var body: some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Style.color(classification: h.classification, flag: h.flag))
                .frame(width: 3, height: 26)
            // Column 1 — stock + recommendation
            VStack(alignment: .leading, spacing: 1) {
                Text(h.symbol).font(.system(size: 13, weight: .semibold))
                Text(Style.shortLabel(h.classification).isEmpty ? (h.name ?? "") : Style.shortLabel(h.classification))
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 4)
            // Column 2 — selected period return, with the current price beneath it
            VStack(alignment: .trailing, spacing: 1) {
                PctText(pct: period.value(h))
                Text("₹\(Style.price(h.ltp))").font(.system(size: 9)).foregroundStyle(.secondary).monospacedDigit()
            }.frame(width: kCol, alignment: .trailing)
            // Column 3 — since-purchase return %, with the ₹ gain beneath it
            VStack(alignment: .trailing, spacing: 1) {
                PctText(pct: h.returnPct, size: 13, weight: .bold)
                Text(Style.rupeeShort(h.pnl))
                    .font(.system(size: 9)).foregroundStyle(.secondary).monospacedDigit()
                    .lineLimit(1).minimumScaleFactor(0.7)
            }.frame(width: kCol, alignment: .trailing)
        }
    }
}

/// Column labels; the period label is a tappable button that cycles Today → 1M → 1Y.
struct ColumnHeader: View {
    let period: Period
    var body: some View {
        HStack(spacing: 6) {
            Spacer(minLength: 4)
            Button(intent: CyclePeriodIntent()) {
                HStack(spacing: 2) {
                    Text(period.label)
                    Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 7, weight: .bold))
                }
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.blue)
            }
            .buttonStyle(.plain)
            .frame(width: kCol, alignment: .trailing)
            Text("Return").font(.system(size: 9, weight: .bold)).foregroundStyle(.secondary)
                .frame(width: kCol, alignment: .trailing)
        }
    }
}

struct PortfolioHeader: View {
    let data: WidgetData
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 1) {
                Text("SM Adviser").font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary)
                Text("₹\(Int(data.portfolio.value).formatted())").font(.system(size: 17, weight: .bold, design: .rounded))
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 1) {
                // Since-purchase total return is the headline for a long-term investor.
                if let tr = data.portfolio.totalReturnPct {
                    Text("\(Style.pct(tr)) total")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundStyle(tr >= 0 ? .green : .red)
                }
                if let a = data.portfolio.attentionCount, a > 0 {
                    Text("\(a) to review").font(.system(size: 9, weight: .medium)).foregroundStyle(.orange)
                }
            }
        }
    }
}

struct ListView: View {
    let data: WidgetData
    let period: Period
    let maxRows: Int
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            PortfolioHeader(data: data)
            ColumnHeader(period: period)
            Divider()
            ForEach(data.holdings.prefix(maxRows)) { HoldingRow(h: $0, period: period) }
            Spacer(minLength: 0)
            let t = MarketClock.shortTime(data.pricesAsOf)
            if !t.isEmpty {
                Text("Prices as of \(t)").font(.system(size: 8)).foregroundStyle(.secondary)
            }
        }
    }
}

struct SmallView: View {
    let data: WidgetData
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("SM Adviser").font(.system(size: 9, weight: .bold)).foregroundStyle(.secondary)
            Text("₹\(Int(data.portfolio.value).formatted())").font(.system(size: 18, weight: .bold, design: .rounded))
            if let tr = data.portfolio.totalReturnPct {
                Text("\(Style.pct(tr)) total")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(tr >= 0 ? .green : .red)
            }
            Spacer(minLength: 2)
            if let a = data.portfolio.attentionCount {
                Text(a > 0 ? "\(a) need attention" : "All clear")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(a > 0 ? .orange : .green)
            }
            if let first = data.holdings.first(where: { $0.classification == "Trim Candidate" || $0.classification == "Exit Candidate" }) {
                Text("\(first.symbol): \(first.classification ?? "")")
                    .font(.system(size: 9)).foregroundStyle(.secondary).lineLimit(1)
            }
        }
    }
}

struct ErrorView: View {
    let message: String
    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: "exclamationmark.triangle").foregroundStyle(.orange)
            Text("SM Adviser").font(.system(size: 11, weight: .bold))
            Text(message).font(.system(size: 9)).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }.padding(6)
    }
}
