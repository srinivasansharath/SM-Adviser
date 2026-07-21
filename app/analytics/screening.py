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


def price_history_days(candles: list[dict] | None) -> int | None:
    """How many traded sessions we actually have — the honest proxy for listing age. A name with
    fewer than ~250 has no verifiable public track record, whatever multi-year figures a data
    provider reports from its pre-IPO accounts."""
    return len(candles) if candles else None


def high_low_ratio(candles: list[dict] | None, lookback: int = 126) -> float | None:
    """6-month high/low ratio (≈126 sessions). 2.0 means the price doubled off its low — exactly the
    '100% high-low variation' the exchanges flag. None when candles lack usable highs/lows."""
    window = (candles or [])[-lookback:]
    highs = [c["high"] for c in window if c.get("high")]
    lows = [c["low"] for c in window if c.get("low")]
    if not highs or not lows:
        return None
    lo = min(lows)
    return round(max(highs) / lo, 2) if lo > 0 else None


def _is_recent_listing(data: dict, cfg: dict | None = None) -> bool:
    c = {**_DEFAULTS, **((cfg or {}).get("screening") or {})}
    hist = data.get("price_history_days")
    return hist is not None and hist < c["min_history_days"]


# Long-term mandate: quality + growth + DURABILITY dominate; valuation/safety/liquidity shape it.
_WEIGHTS = {"quality": 0.24, "growth": 0.20, "durability": 0.20,
            "valuation": 0.14, "safety": 0.14, "liquidity": 0.08}

_DEFAULTS = {
    "pledge_max_pct": 25.0,      # promoter pledge above this -> hard exclude (small-cap red flag)
    "min_liquidity_cr": 1.0,     # median daily traded value floor (₹ cr) -> tradability gate
    "de_max": 3.0,               # extreme leverage (non-financial) -> hard exclude
    "compounder_roe": 15.0,      # consistent ROE bar for the Compounder bucket
    "garp_growth": 15.0,         # 5y profit CAGR bar for GARP
    "garp_peg_max": 1.5,         # PEG ceiling for GARP
    # --- price-risk / low-base guards (a recent listing's pre-IPO CAGRs distort everything) ---
    "min_history_days": 250,     # fewer traded sessions than this -> treat as a RECENT LISTING
    "peg_growth_cap": 40.0,      # cap the PEG growth denominator; a 158% low-base CAGR isn't durable
    "pe_rich": 50.0,             # absolute richness: caution + valuation-score ceiling
    "valuation_cap_when_rich": 55.0,  # a rich multiple can't earn top valuation marks
    "hl_ratio_max": 2.0,         # 6-month high/low above this = 100%+ swing (exchange caution rule)
}


def _scale(x: float | None, lo: float, hi: float) -> float | None:
    """Map x from [lo, hi] onto [0, 100], clamped. lo may exceed hi to invert (lower x = better)."""
    if x is None:
        return None
    frac = (x - lo) / (hi - lo)
    return round(max(0.0, min(1.0, frac)) * 100, 1)


def _band(x: float | None, good: float, great: float) -> float | None:
    """Concave 'higher is better' score with diminishing returns: 0..good -> 0..70 (linear), then
    good..great -> 70..100. Rewards clearing the 'good' bar and still discriminates the exceptional
    up to 'great', but a freak value (e.g. 165% ROCE) can't out-score a strong-but-sane one by much.
    Non-positive -> 0 (a metric at/below zero earns nothing)."""
    if x is None:
        return None
    if x <= 0:
        return 0.0
    if x <= good:
        return round(x / good * 70, 1)
    return round(min(100.0, 70 + (x - good) / (great - good) * 30), 1)


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


def peg(data: dict, cfg: dict | None = None) -> float | None:
    """P/E to 5y-profit-growth, with the growth denominator CAPPED.

    Uncapped, a low-base CAGR (e.g. a recent listing compounding 158% off near-zero pre-IPO profit)
    drives PEG toward zero and scores valuation a perfect 100 at almost any P/E. Capping the
    denominator keeps PEG meaningful: exceptional growth still helps, but can't make a name look free.
    """
    c = {**_DEFAULTS, **((cfg or {}).get("screening") or {})}
    pe, g = data.get("pe"), data.get("profit_cagr_5y")
    if pe is None or pe <= 0 or g is None or g <= 0:
        return None
    return round(pe / min(g, c["peg_growth_cap"]), 2)


def score_quality(data: dict) -> float | None:
    """Level of quality: the DURABLE (5y) ROE, reinforced by ROCE for non-financials. Uses the 5y
    ROE over the latest year so a one-off spike doesn't inflate it, and caps a freak ROCE."""
    roe_5y, roe_now = data.get("roe_5y"), data.get("roe")
    core = roe_5y if roe_5y is not None else roe_now   # durable figure preferred
    roce = data.get("roce")
    if core is None and roce is None:
        return None
    parts = [_band(core, 18, 32)]
    if not is_financial(data) and roce is not None:
        parts.append(_band(min(roce, 45), 20, 40))     # cap: 40% and 165% ROCE shouldn't both max
    return _avg(*parts)


def score_growth(data: dict) -> float | None:
    """5y sales + profit CAGR (durable growth), lightly lifted by recent quarterly acceleration."""
    base = _avg(_band(data.get("sales_cagr_5y"), 15, 30), _band(data.get("profit_cagr_5y"), 15, 30))
    if base is None:
        return None
    recent = _avg(_band(data.get("sales_growth_qtr"), 15, 40), _band(data.get("profit_growth_qtr"), 20, 60))
    return _avg(base, base, recent) if recent is not None else base  # base weighted 2x


def score_durability(data: dict, cfg: dict | None = None) -> float | None:
    """Track record + CONSISTENCY — the dimension that separates a durable compounder from a one-good-
    year fluke. Rewards a high worst-horizon ROE and a tight ROE spread across years, plus steady
    positive 5y growth. Crucially, a name with NO multi-year history scores low (25) rather than
    being renormalised away — no track record is demoted, not excused."""
    # A recent listing has no VERIFIABLE public record — floor it regardless of the multi-year
    # figures the provider reports (those are pre-IPO accounts, not a track record we can trust).
    if _is_recent_listing(data, cfg):
        return 25.0
    roe_5y, roe_3y, roe_now = data.get("roe_5y"), data.get("roe_3y"), data.get("roe")
    scagr, pcagr = data.get("sales_cagr_5y"), data.get("profit_cagr_5y")
    if all(v is None for v in (roe_5y, roe_3y, scagr, pcagr)):
        return 25.0
    parts: list[float | None] = []
    roes = [v for v in (roe_5y, roe_3y, roe_now) if v is not None]
    if len(roes) >= 2:
        parts.append(_band(min(roes), 12, 25))              # worst-horizon ROE (Coffee-Can worst year)
        parts.append(_scale(max(roes) - min(roes), 45, 5))  # tight spread = consistent (inverted)
    parts.append(_band(scagr, 8, 20))
    parts.append(_band(pcagr, 8, 22))
    return _avg(*parts)


def score_valuation(data: dict, cfg: dict | None = None) -> float | None:
    """PEG-led (growth-adjusted, capped denominator); absolute P/E band when PEG is undefined.

    An absolute ceiling applies on top: however fast it's growing, a rich multiple can't earn top
    valuation marks — growth may justify a premium, but it shouldn't hide one.
    """
    c = {**_DEFAULTS, **((cfg or {}).get("screening") or {})}
    p = peg(data, cfg)
    score = _scale(p, 2.5, 0.5) if p is not None else _scale(data.get("pe"), 60, 10)
    pe = data.get("pe")
    if score is not None and pe is not None and pe > c["pe_rich"]:
        score = min(score, c["valuation_cap_when_rich"])
    return score


def score_safety(data: dict, cfg: dict | None = None) -> float | None:
    """Low leverage + low pledge + PRICE STABILITY. Leverage skipped for financials (inherently
    geared). A violent 6-month range is a real risk to the holder, so it belongs in safety."""
    pledge = _scale(data.get("promoter_pledge"), 50, 0)
    de = None if is_financial(data) else _scale(data.get("debt_to_equity"), 2.0, 0.0)
    vol = _scale(data.get("high_low_ratio_6m"), 3.0, 1.2)  # 1.2x -> 100, 3.0x -> 0
    return _avg(de, pledge, vol)


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
    roe5, roe_now, roe3 = data.get("roe_5y"), data.get("roe"), data.get("roe_3y")
    pcagr = data.get("profit_cagr_5y")
    pledge = data.get("promoter_pledge") or 0
    roes = [v for v in (roe5, roe3, roe_now) if v is not None]

    # Compounder: a real, consistent track record — REQUIRES 5y ROE AND enough traded history.
    # A recent listing can never be a Compounder, however flattering its pre-IPO accounts look.
    if not _is_recent_listing(data, cfg) \
            and roe5 is not None and roe5 >= c["compounder_roe"] and (roe_now or 0) >= c["compounder_roe"] \
            and (pcagr or 0) >= 8 and pledge <= 10 and (not roes or min(roes) >= 10):
        out.append("Compounder")
    p = peg(data, cfg)
    if (pcagr or 0) >= c["garp_growth"] and p is not None and p <= c["garp_peg_max"]:
        out.append("GARP")
    # Tailwind: recent acceleration MEANINGFULLY above the 5y trend, on a company with real quality —
    # not just a micro-cap quarterly spike. (LLM confirms the actual sector story in Stage 4.)
    quality_floor = (roe5 or roe_now or 0) >= 12 or (data.get("roce") or 0) >= 15
    sqtr = data.get("sales_growth_qtr") or 0
    if quality_floor and sqtr >= 20 and sqtr >= 1.5 * (data.get("sales_cagr_5y") or 0.001) \
            and (data.get("profit_growth_qtr") or 0) >= 25:
        out.append("Tailwind")
    return out


def coarse_score(row: dict) -> float:
    """Stage-1 rank over ONLY the bulk-screen columns (no deep fetch yet). Purely to prioritise
    which names get a per-stock deep fetch — never excludes, just orders. Higher = fetch sooner.
    ROCE is capped and quarterly growth down-weighted so freak micro-cap trailing numbers don't
    crowd out steadier names; a mild size tilt favours those more likely to have a track record."""
    roce = row.get("roce")
    quality = _band(min(roce, 45) if roce is not None else None, 18, 40) or 0
    growth = _avg(_band(row.get("profit_growth_qtr"), 15, 60),
                  _band(row.get("sales_growth_qtr"), 12, 40)) or 0
    val = _scale(peg({"pe": row.get("pe"), "profit_cagr_5y": row.get("profit_growth_qtr")}), 3.0, 0.5)
    val = val if val is not None else (_scale(row.get("pe"), 80, 10) or 0)
    size = _scale(row.get("market_cap"), 100, 20000) or 0
    return round(0.45 * quality + 0.28 * growth + 0.15 * val + 0.12 * size, 1)


def diversified_featured(scored: list[dict], per_sector: int = 3, sectors: int = 4) -> list[dict]:
    """Sector-diversified shortlist: the top `per_sector` candidates from each of the top `sectors`
    sectors, so one hot sector (e.g. solar/renewables) can't dominate the whole table. Sectors are
    ranked by their strongest candidate's composite; within a sector, by composite. Returns a flat
    list grouped sector-by-sector (so the table visibly mixes sectors)."""
    by_sector: dict[str, list[dict]] = {}
    for r in sorted(scored, key=lambda r: r.get("composite") or 0, reverse=True):
        sec = ((r.get("data") or {}).get("sector")) or "Other"
        by_sector.setdefault(sec, []).append(r)
    ranked = sorted(by_sector.items(), key=lambda kv: kv[1][0].get("composite") or 0, reverse=True)
    featured: list[dict] = []
    for _sec, rows in ranked[:sectors]:
        featured.extend(rows[:per_sector])
    return featured


def cautions(data: dict, cfg: dict | None = None) -> list[str]:
    """NON-excluding warnings surfaced beside a candidate — the same idea as an exchange's
    'regulatory caution' notice. These don't remove a name from the shortlist (that's `red_flags`);
    they make the risk explicit so it can't hide behind a high composite."""
    c = {**_DEFAULTS, **((cfg or {}).get("screening") or {})}
    out: list[str] = []
    hist = data.get("price_history_days")
    if _is_recent_listing(data, cfg):
        out.append(f"recent listing: only {hist} traded sessions — no verifiable public track record")
    pe = data.get("pe")
    if pe is not None and pe > c["pe_rich"]:
        out.append(f"rich valuation: P/E {pe:.0f} above {c['pe_rich']:.0f}")
    hl = data.get("high_low_ratio_6m")
    if hl is not None and hl > c["hl_ratio_max"]:
        out.append(f"volatile: 6-month high/low {hl:.1f}x (>{c['hl_ratio_max']:.1f}x = 100%+ swing)")
    g = data.get("profit_cagr_5y")
    if g is not None and g > c["peg_growth_cap"]:
        out.append(f"low-base growth: {g:.0f}% 5y CAGR capped at {c['peg_growth_cap']:.0f}% for PEG")
    return out


def score_candidate(data: dict, cfg: dict | None = None) -> dict:
    """Full Stage-2 assessment: sub-scores, composite, buckets, red-flag gate, cautions."""
    subs = {
        "quality": score_quality(data),
        "growth": score_growth(data),
        "durability": score_durability(data, cfg),
        "valuation": score_valuation(data, cfg),
        "safety": score_safety(data, cfg),
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
        "cautions": cautions(data, cfg),
        "peg": peg(data, cfg),
        "is_financial": is_financial(data),
    }
