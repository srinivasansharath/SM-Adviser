"""Gather a run's stored data into one structure the report + widget both render from."""

from __future__ import annotations

from datetime import date

from ..storage.models import Holding, MarketFlow, Metric, OrderFlow, Recommendation, Snapshot
from .signals import evaluate_flags

_METRIC_FIELDS = (
    "ret_1d", "ret_5d", "ret_20d", "ret_252d", "drawdown", "rsi", "vol_spike", "rel_strength",
    "sma_20", "sma_50", "sma_200",
)


def _metric_dict(m: Metric | None) -> dict:
    return {f: getattr(m, f) for f in _METRIC_FIELDS} if m else {f: None for f in _METRIC_FIELDS}


def _of_dict(o: OrderFlow | None) -> dict:
    if not o:
        return {"delivery_pct": None, "avg_delivery_pct": None, "signal": None}
    return {"delivery_pct": o.delivery_pct, "avg_delivery_pct": o.avg_delivery_pct, "signal": o.signal}


def gather_report_data(session, run_date: date, config: dict) -> dict:
    holdings = session.query(Holding).filter_by(run_date=run_date).all()
    metrics = {m.symbol: m for m in session.query(Metric).filter_by(run_date=run_date)}
    flows = {o.symbol: o for o in session.query(OrderFlow).filter_by(run_date=run_date)}
    recs = {r.symbol: r for r in session.query(Recommendation).filter_by(run_date=run_date)}
    market_flow = session.query(MarketFlow).filter_by(run_date=run_date).first()

    # Real intraday day-change comes from the frozen holdings snapshot (Kite payload).
    snap = session.query(Snapshot).filter_by(run_date=run_date, kind="holdings").first()
    day_change = {}
    if snap and isinstance(snap.payload, list):
        for r in snap.payload:
            day_change[r.get("tradingsymbol")] = r.get("day_change_percentage")

    total_value = sum(h.ltp * h.qty for h in holdings)
    total_pnl = sum((h.pnl or 0) for h in holdings)
    cost_basis = sum(h.avg_price * h.qty for h in holdings)
    total_return_pct = round(total_pnl / cost_basis * 100, 2) if cost_basis else None

    rows = []
    for h in holdings:
        md = _metric_dict(metrics.get(h.symbol))
        ofd = _of_dict(flows.get(h.symbol))
        flags = evaluate_flags({"weight_pct": h.weight_pct, "ltp": h.ltp}, md, ofd, config)
        rec = recs.get(h.symbol)
        rows.append(
            {
                "symbol": h.symbol,
                "name": h.symbol,  # company names not in Kite holdings; enrich later
                "qty": h.qty,
                "avg_price": h.avg_price,
                "ltp": h.ltp,
                "pnl": h.pnl,
                # Since-purchase return: current vs average buy price. Always available.
                "return_pct": (
                    round((h.ltp / h.avg_price - 1) * 100, 2) if h.avg_price else None
                ),
                "weight_pct": h.weight_pct,
                "day_change_pct": day_change.get(h.symbol),
                "above_50dma": (h.ltp >= md["sma_50"]) if md["sma_50"] else None,
                "above_200dma": (h.ltp >= md["sma_200"]) if md["sma_200"] else None,
                # Phase 4 thesis-aware classification (None until scoring has run).
                "classification": rec.classification if rec else None,
                "confidence": rec.confidence if rec else None,
                "prev_classification": rec.prev_classification if rec else None,
                "rec_reason": rec.reason if rec else None,
                **md,
                **ofd,
                **flags,
            }
        )
    rows.sort(key=lambda r: r["weight_pct"] or 0, reverse=True)

    wsum = acc = 0.0
    for h in holdings:
        dc = day_change.get(h.symbol)
        if dc is not None:
            v = h.ltp * h.qty
            acc += v * dc
            wsum += v
    day_change_pct = round(acc / wsum, 2) if wsum else None

    # "Needs attention" prefers the classification when present, else the technical flag.
    def needs_attention(r: dict) -> bool:
        if r["classification"]:
            return r["classification"] not in ("Hold", "Accumulate Candidate")
        return r["flag"] != "ok"

    attention = [r for r in rows if needs_attention(r)]
    return {
        "run_date": str(run_date),
        "portfolio": {
            "value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": total_return_pct,
            "day_change_pct": day_change_pct,
            "top5_pct": round(sum((r["weight_pct"] or 0) for r in rows[:5]), 1),
            "holdings_count": len(rows),
            "attention_count": len(attention),
            "fii_net": market_flow.fii_net if market_flow else None,
            "dii_net": market_flow.dii_net if market_flow else None,
        },
        "holdings": rows,
    }
