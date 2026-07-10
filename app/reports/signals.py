"""Preliminary rule-based risk flags (Phase 3).

IMPORTANT: these are TECHNICAL + PORTFOLIO-FIT flags only — they do NOT use the investment
thesis, fundamentals, valuation, or news. They are an early-warning surface built from the
data we have now. The full thesis-aware Hold/Watch/Accumulate/Trim/Exit classification
(BUILD_PLAN §5) arrives in Phase 4. Flags: "ok" | "watch" | "risk".
"""

from __future__ import annotations

_SEVERITY = {"ok": 0, "watch": 1, "risk": 2}


def evaluate_flags(holding: dict, metric: dict, order_flow: dict, config: dict) -> dict:
    """Return {"flag": ok|watch|risk, "reasons": [...]} for one holding."""
    port = config.get("portfolio") or {}
    max_wt = port.get("max_position_weight_pct", 12)

    reasons: list[tuple[str, str]] = []  # (severity, text)

    wt = holding.get("weight_pct")
    if wt is not None:
        if wt > 15:
            reasons.append(("risk", f"Concentration: {wt:.0f}% of portfolio (>15%)"))
        elif wt > max_wt:
            reasons.append(("watch", f"Overweight: {wt:.0f}% (> {max_wt:.0f}% target)"))

    ltp = holding.get("ltp")
    sma50 = metric.get("sma_50")
    sma200 = metric.get("sma_200")
    rs = metric.get("rel_strength")
    dd = metric.get("drawdown")
    rsi = metric.get("rsi")

    lagging = rs is not None and rs < -5
    if ltp and sma200 and ltp < sma200 and lagging:
        reasons.append(("risk", f"Below 200-DMA and lagging NIFTY by {abs(rs):.0f}pts (20D)"))
    elif ltp and sma50 and ltp < sma50:
        reasons.append(("watch", "Below 50-DMA (downtrend)"))

    if dd is not None:
        if dd < -35:
            reasons.append(("risk", f"Deep drawdown {dd:.0f}% from recent high"))
        elif dd < -25:
            reasons.append(("watch", f"Drawdown {dd:.0f}% from recent high"))

    if rsi is not None and rsi < 30:
        reasons.append(("watch", f"Oversold (RSI {rsi:.0f})"))

    if rs is not None and rs < -8 and not any("lagging" in t.lower() for _, t in reasons):
        reasons.append(("watch", f"Lagging NIFTY by {abs(rs):.0f}pts (20D)"))

    if order_flow.get("signal") == "low":
        reasons.append(("watch", "Low delivery % (intraday churn, weak conviction)"))

    if not reasons:
        return {"flag": "ok", "reasons": []}
    flag = max(reasons, key=lambda r: _SEVERITY[r[0]])[0]
    return {"flag": flag, "reasons": [t for _, t in reasons]}
