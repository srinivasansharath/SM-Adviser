"""Fundamental + valuation sub-scores and hard-override checks (BUILD_PLAN §5.1/§5.3).

Scores are 0-100 (higher = more bullish), built from whatever fields the fundamentals connector
returned — partial data still scores. Thresholds come from RESEARCH_DECISION_METHODS.md.
"""

from __future__ import annotations

_FUND_FIELDS = ("roce", "roe", "debt_to_equity", "interest_coverage", "rev_growth_3y", "opm")


def score_fundamental(f: dict | None) -> float | None:
    if not f or all(f.get(k) is None for k in _FUND_FIELDS):
        return None
    s = 50.0
    roce = f.get("roce")
    if roce is not None:
        s += 15 if roce >= 20 else (7 if roce >= 15 else (-10 if roce < 8 else 0))
    roe = f.get("roe")
    if roe is not None:
        s += 12 if roe >= 20 else (6 if roe >= 15 else (-8 if roe < 8 else 0))
    de = f.get("debt_to_equity")
    if de is not None:
        s += 8 if de < 0.5 else (3 if de < 1 else (-12 if de > 1.5 else -4))
    ic = f.get("interest_coverage")
    if ic is not None:
        s += 6 if ic > 5 else (-15 if ic < 1.5 else 0)
    g = f.get("rev_growth_3y")
    if g is not None:
        s += 8 if g > 15 else (4 if g > 10 else (-8 if g < 0 else 0))
    opm = f.get("opm")
    if opm is not None:
        s += 4 if opm > 20 else (-4 if opm < 8 else 0)
    return round(max(0, min(100, s)), 1)


def score_valuation(f: dict | None) -> float | None:
    if not f or (f.get("pe") is None and f.get("pb") is None):
        return None
    s = 50.0
    pe = f.get("pe")
    ipe = f.get("industry_pe")
    if pe is not None and pe > 0:
        if ipe:
            ratio = pe / ipe
            s += 15 if ratio < 0.8 else (-15 if ratio > 1.3 else 0)
        else:
            s += 12 if pe < 15 else (-12 if pe > 35 else 0)
    pb = f.get("pb")
    if pb is not None:
        s += 6 if pb < 1.5 else (-6 if pb > 5 else 0)
    dy = f.get("dividend_yield")
    if dy is not None and dy > 2:
        s += 4
    return round(max(0, min(100, s)), 1)


def hard_override(f: dict | None, config: dict) -> str | None:
    """Return a reason string if a solvency/governance breach forces Exit-Candidate, else None."""
    if not f:
        return None
    ov = (config.get("scoring") or {}).get("hard_overrides") or {}
    ic = f.get("interest_coverage")
    if ic is not None and ic < ov.get("interest_coverage_below", 1.5):
        return f"Interest coverage {ic} below {ov.get('interest_coverage_below', 1.5)} (solvency risk)"
    pledge = f.get("promoter_pledge")
    if pledge is not None and pledge > ov.get("promoter_pledge_pct_above", 50):
        return f"Promoter pledge {pledge}% above {ov.get('promoter_pledge_pct_above', 50)}%"
    nde = f.get("net_debt_ebitda")
    if nde is not None and nde > ov.get("net_debt_ebitda_above", 4.0):
        return f"Net debt/EBITDA {nde} above {ov.get('net_debt_ebitda_above', 4.0)}"
    return None
