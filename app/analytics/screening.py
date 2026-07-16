"""New-stock screening logic (BUILD_PLAN Phase 6) — pure, sector-aware, None-tolerant.

Two-stage funnel:
  * coarse_score()  — cheap rank over the bulk-screen columns (ROCE/P-E/qtr growth) to pick which
                      of ~3,000 names are worth a per-stock deep fetch.
  * score_candidate() — full assessment over the deep ratios: quality / growth / valuation / safety
                      / liquidity sub-scores (0-100, higher = better), red-flag HARD GATES that
                      exclude regardless of score (the small-cap safeguard), and bucket tags
                      (Compounder / GARP / Tailwind) so ideas are presented in tiers.

Deliberately conservative and transparent: every sub-score returns None when its inputs are absent
(the composite renormalises over what's present, like the holdings engine), and financials — where
ROCE and D/E are meaningless — fall back to ROE-based quality with leverage checks skipped. This is
decision support, not advice; it ranks and explains, it never says "buy".
"""

from __future__ import annotations

import statistics


def median_daily_value_cr(candles: list[dict] | None, lookback: int = 30) -> float | None:
    """Median daily traded value (₹ crore) over the last `lookback` candles = median(close × volume).
    The tradability signal for the liquidity gate; None when there are no usable candles."""
    vals = [
        c["close"] * c["volume"]
        for c in (candles or [])[-lookback:]
        if c.get("close") and c.get("volume")
    ]
    return round(statistics.median(vals) / 1e7, 2) if vals else None


# Long-term mandate: quality + growth dominate; valuation/safety/liquidity shape the ranking.
_WEIGHTS = {"quality": 0.30, "growth": 0.30, "valuation": 0.15, "safety": 0.15, "liquidity": 0.10}

_DEFAULTS = {
    "pledge_max_pct": 25.0,      # promoter pledge above this -> hard exclude (small-cap red flag)
    "min_liquidity_cr": 1.0,     # median daily traded value floor (₹ cr) -> tradability gate
    "de_max": 3.0,               # extreme leverage (non-financial) -> hard exclude
    "compounder_roe": 15.0,      # consistent ROE bar for the Compounder bucket
    "garp_growth": 15.0,         # 5y profit CAGR bar for GARP
    "garp_peg_max": 1.5,         # PEG ceiling for GARP
}


def _scale(x: float | None, lo: float, hi: float) -> float | None:
    """Map x from [lo, hi] onto [0, 100], clamped. lo may exceed hi to invert (lower x = better)."""
    if x is None:
        return None
    frac = (x - lo) / (hi - lo)
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _avg(*vals: float | None) -> float | None:
    present = [v for v in vals if v is not None]
    return round(sum(present) / len(present), 1) if present else None


def is_financial(data: dict) -> bool:
    """Banks/NBFCs: sector hint if provided, else inferred (screener gives them no promoter row and
    no 'Borrowings' line, so both come back None while ROE is present)."""
    sector = (data.get("sector") or "").lower()
    if sector:
        return any(k in sector for k in ("bank", "financ", "nbfc", "insurance"))
    return data.get("debt_to_equity") is None and data.get("promoter_holding") is None \
        and data.get("roe") is not None


def peg(data: dict) -> float | None:
    """P/E to 5y-profit-growth. None when P/E missing or growth non-positive (PEG undefined)."""
    pe, g = data.get("pe"), data.get("profit_cagr_5y")
    if pe is None or pe <= 0 or g is None or g <= 0:
        return None
    return round(pe / g, 2)


def score_quality(data: dict) -> float | None:
    """ROE now + ROE consistency (5y); ROCE reinforces for non-financials."""
    roe_now = _scale(data.get("roe"), 5, 25)
    roe_5y = _scale(data.get("roe_5y"), 5, 25)
    parts = [roe_now, roe_5y]
    if not is_financial(data):
        parts.append(_scale(data.get("roce"), 8, 30))  # ROCE only meaningful outside financials
    return _avg(*parts)


def score_growth(data: dict) -> float | None:
    """5y sales + profit CAGR (durable growth), lightly lifted by recent quarterly acceleration."""
    base = _avg(_scale(data.get("sales_cagr_5y"), 5, 25), _scale(data.get("profit_cagr_5y"), 5, 25))
    if base is None:
        return None
    recent = _avg(_scale(data.get("sales_growth_qtr"), 0, 30), _scale(data.get("profit_growth_qtr"), 0, 40))
    return _avg(base, base, recent) if recent is not None else base  # base weighted 2x


def score_valuation(data: dict) -> float | None:
    """PEG-led (growth-adjusted); falls back to an absolute P/E band when PEG is undefined."""
    p = peg(data)
    if p is not None:
        return _scale(p, 2.5, 0.5)  # PEG 0.5 -> 100, 2.5 -> 0
    return _scale(data.get("pe"), 60, 10)  # loss-makers / no-growth: cheaper abs P/E scores higher


def score_safety(data: dict) -> float | None:
    """Low leverage + low pledge. Leverage skipped for financials (inherently geared)."""
    pledge = _scale(data.get("promoter_pledge"), 50, 0)
    de = None if is_financial(data) else _scale(data.get("debt_to_equity"), 2.0, 0.0)
    return _avg(de, pledge)


def score_liquidity(data: dict) -> float | None:
    """Median daily traded value (₹ cr) — tradability. Supplied from our market-data side."""
    return _scale(data.get("median_daily_value_cr"), 0.2, 5.0)


def composite(subscores: dict) -> float | None:
    """Weighted mean over the sub-scores that are present (renormalised)."""
    num = den = 0.0
    for k, w in _WEIGHTS.items():
        v = subscores.get(k)
        if v is not None:
            num += w * v
            den += w
    return round(num / den, 1) if den else None


def red_flags(data: dict, cfg: dict | None = None) -> list[str]:
    """HARD-GATE reasons — any non-empty list means the candidate is excluded regardless of score."""
    c = {**_DEFAULTS, **((cfg or {}).get("screening") or {})}
    flags: list[str] = []
    pledge = data.get("promoter_pledge")
    if pledge is not None and pledge > c["pledge_max_pct"]:
        flags.append(f"promoter pledge {pledge:.0f}% > {c['pledge_max_pct']:.0f}%")
    liq = data.get("median_daily_value_cr")
    if liq is not None and liq < c["min_liquidity_cr"]:
        flags.append(f"illiquid: ₹{liq:.2f} cr/day < ₹{c['min_liquidity_cr']:.1f} cr")
    de = data.get("debt_to_equity")
    if not is_financial(data) and de is not None and de > c["de_max"]:
        flags.append(f"extreme leverage D/E {de:.1f} > {c['de_max']:.1f}")
    g, roe = data.get("profit_cagr_5y"), data.get("roe")
    if g is not None and g < 0 and roe is not None and roe < 5:
        flags.append("chronic weak: negative 5y profit CAGR and ROE < 5%")
    return flags


def buckets(data: dict, cfg: dict | None = None) -> list[str]:
    """Tag which style(s) a name fits — a name can be in more than one (blend view)."""
    c = {**_DEFAULTS, **((cfg or {}).get("screening") or {})}
    out: list[str] = []
    roe5, roe_now = data.get("roe_5y"), data.get("roe")
    pcagr = data.get("profit_cagr_5y")
    pledge = data.get("promoter_pledge") or 0

    if (roe5 or 0) >= c["compounder_roe"] and (roe_now or 0) >= c["compounder_roe"] \
            and (pcagr or 0) >= 8 and pledge <= 10:
        out.append("Compounder")
    p = peg(data)
    if (pcagr or 0) >= c["garp_growth"] and p is not None and p <= c["garp_peg_max"]:
        out.append("GARP")
    # Recent acceleration vs the 5y trend — a proxy for a live tailwind (LLM confirms the sector story).
    if (data.get("profit_growth_qtr") or 0) >= 25 and (data.get("sales_growth_qtr") or 0) >= 15 \
            and (data.get("sales_growth_qtr") or 0) > (data.get("sales_cagr_5y") or 0):
        out.append("Tailwind")
    return out


def coarse_score(row: dict) -> float:
    """Stage-1 rank over ONLY the bulk-screen columns (no deep fetch yet). Purely to prioritise
    which names get a per-stock deep fetch — never excludes, just orders. Higher = fetch sooner."""
    quality = _scale(row.get("roce"), 8, 40) or 0        # ROCE is the one quality signal we get cheap
    growth = _avg(_scale(row.get("profit_growth_qtr"), 0, 40),
                  _scale(row.get("sales_growth_qtr"), 0, 30)) or 0
    val = _scale(peg({"pe": row.get("pe"), "profit_cagr_5y": row.get("profit_growth_qtr")}), 3.0, 0.5)
    val = val if val is not None else (_scale(row.get("pe"), 80, 10) or 0)
    return round(0.45 * quality + 0.35 * growth + 0.20 * val, 1)


def score_candidate(data: dict, cfg: dict | None = None) -> dict:
    """Full Stage-2 assessment: sub-scores, composite, buckets, red-flag gate."""
    subs = {
        "quality": score_quality(data),
        "growth": score_growth(data),
        "valuation": score_valuation(data),
        "safety": score_safety(data),
        "liquidity": score_liquidity(data),
    }
    flags = red_flags(data, cfg)
    return {
        "symbol": data.get("symbol"),
        "subscores": subs,
        "composite": composite(subs),
        "buckets": buckets(data, cfg),
        "red_flags": flags,
        "excluded": bool(flags),
        "peg": peg(data),
        "is_financial": is_financial(data),
    }
