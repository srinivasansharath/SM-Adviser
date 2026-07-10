"""Order-flow analytics — turn a delivery series into a per-holding signal (§5.5).

Delivery % = fraction of traded volume actually taken to demat. High vs its own recent
average = conviction (holding/accumulating); low = intraday churn/speculation. This is a
CONFIRMATION signal — Phase 4 combines it with the price move (a low-delivery drop is froth;
a high-delivery drop is genuine distribution). It never triggers an exit on its own.
"""

from __future__ import annotations

# Bands relative to the stock's own trailing average delivery %.
HIGH_MULT = 1.2
LOW_MULT = 0.8


def compute_delivery_signal(delivery_series: list[dict]) -> dict:
    """Return the OrderFlow-table row values from a delivery series (oldest -> newest)."""
    if not delivery_series:
        return {
            "traded_qty": None,
            "delivery_qty": None,
            "delivery_pct": None,
            "avg_delivery_pct": None,
            "signal": None,
        }

    latest = delivery_series[-1]
    dp = latest.get("delivery_pct")
    prior = [d["delivery_pct"] for d in delivery_series[:-1] if d.get("delivery_pct") is not None]
    avg = round(sum(prior) / len(prior), 2) if prior else None

    signal = "normal"
    if dp is not None and avg:
        if dp >= avg * HIGH_MULT:
            signal = "high"   # conviction: elevated delivery vs its own norm
        elif dp <= avg * LOW_MULT:
            signal = "low"    # froth: churn-heavy, little delivery
    elif dp is None or avg is None:
        signal = None

    return {
        "traded_qty": latest.get("traded_qty"),
        "delivery_qty": latest.get("delivery_qty"),
        "delivery_pct": dp,
        "avg_delivery_pct": avg,
        "signal": signal,
    }
