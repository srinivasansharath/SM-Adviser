import SwiftUI
import WidgetKit

struct ChangePill: View {
    let pct: Double?
    var body: some View {
        let up = (pct ?? 0) >= 0
        Text(Style.pct(pct))
            .font(.system(size: 10, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background((up ? Color.green : Color.red).opacity(0.9), in: RoundedRectangle(cornerRadius: 4))
    }
}

struct HoldingRow: View {
    let h: Holding
    var body: some View {
        HStack(spacing: 8) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Style.color(classification: h.classification, flag: h.flag))
                .frame(width: 3, height: 30)
            VStack(alignment: .leading, spacing: 1) {
                Text(h.symbol).font(.system(size: 13, weight: .semibold))
                Text(Style.shortLabel(h.classification).isEmpty ? (h.name ?? "") : Style.shortLabel(h.classification))
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 2) {
                Text("₹\(Style.price(h.ltp))").font(.system(size: 13, weight: .medium, design: .rounded))
                ChangePill(pct: h.changePct)
            }
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
                ChangePill(pct: data.portfolio.dayChangePct)
                if let a = data.portfolio.attentionCount, a > 0 {
                    Text("\(a) to review").font(.system(size: 9, weight: .medium)).foregroundStyle(.orange)
                }
            }
        }
    }
}

struct ListView: View {
    let data: WidgetData
    let maxRows: Int
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            PortfolioHeader(data: data)
            Divider()
            ForEach(data.holdings.prefix(maxRows)) { HoldingRow(h: $0) }
            Spacer(minLength: 0)
        }
    }
}

struct SmallView: View {
    let data: WidgetData
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("SM Adviser").font(.system(size: 9, weight: .bold)).foregroundStyle(.secondary)
            Text("₹\(Int(data.portfolio.value).formatted())").font(.system(size: 18, weight: .bold, design: .rounded))
            ChangePill(pct: data.portfolio.dayChangePct)
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
