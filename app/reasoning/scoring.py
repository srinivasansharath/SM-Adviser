"""Deterministic scoring engine (BUILD_PLAN §5).

Rules first, LLM narrates later. Sub-scores are 0-100 (higher = more bullish). We compute the
ones we have data for now (technical, portfolio_fit, thesis-proxy); fundamental / valuation /
news_risk stay None until their data sources (fundamentals connector / LLM research) land, and
the composite is renormalized over what's available with a coverage-based confidence label —
so a portfolio with no fundamentals data honestly reports Low/Medium confidence.

Free-text `exit_if` conditions are evaluated by the LLM layer (Phase 4b), not here; the thesis
sub-score uses conviction + weight-drift + technical stress as a deterministic proxy.
"""

from __future__ import annotations

from ..analytics.fundamentals import hard_override, score_fundamental, score_valuation
from ..domain import Classification
from ..reports.signals import evaluate_flags

# Default composite weights (BUILD_PLAN §5.2).
DEFAULT_WEIGHTS = {
    "fundamental": 0.25,
    "valuation": 0.20,
    "technical": 0.20,
    "thesis": 0.15,
    "news_risk": 0.12,
    "portfolio_fit": 0.08,
}

_CONVICTION_BASE = {"high": 75, "medium": 60, "low": 45}

# Composite -> classification thresholds (§5.2), highest band first.
_THRESHOLDS = [
    (75, Classification.ACCUMULATE.value),
    (60, Classification.WATCH.value),
    (45, Classification.HOLD.value),
    (30, Classification.TRIM.value),
    (0, Classification.EXIT.value),
]
# Ascending bands with the LOWER edge of each (for hysteresis boundaries).
_BANDS_ASC = [
    (Classification.EXIT.value, 0),
    (Classification.TRIM.value, 30),
    (Classification.HOLD.value, 45),
    (Classification.WATCH.value, 60),
    (Classification.ACCUMULATE.value, 75),
]


def score_technical(metric: dict | None, ltp: float | None) -> float | None:
    if not metric or ltp is None:
        return None
    keys = ("sma_50", "sma_200", "ret_20d", "rel_strength", "rsi", "drawdown")
    if all(metric.get(k) is None for k in keys):
        return None
    s = 50.0
    if metric.get("sma_200") is not None:
        s += 15 if ltp >= metric["sma_200"] else -15
    if metric.get("sma_50") is not None:
        s += 10 if ltp >= metric["sma_50"] else -10
    rs = metric.get("rel_strength")
    if rs is not None:
        s += max(-15, min(15, rs))
    rsi = metric.get("rsi")
    if rsi is not None and (rsi < 30 or rsi > 70):
        s -= 5
    dd = metric.get("drawdown")
    if dd is not None:
        s += max(-20, dd / 2)
    return round(max(0, min(100, s)), 1)


def score_portfolio_fit(weight: float | None, target: float | None, config: dict) -> float | None:
    if weight is None:
        return None
    max_wt = (config.get("portfolio") or {}).get("max_position_weight_pct", 12)
    s = 70.0
    if weight > 15:
        s -= 40
    elif weight > max_wt:
        s -= 20
    if target:
        drift = weight - target
        if drift > 5:
            s -= min(20, drift)
    return round(max(0, min(100, s)), 1)


def score_thesis(meta: dict | None, weight: float | None, metric: dict | None, ltp: float | None,
                 order_flow: dict | None) -> float:
    conviction = (meta or {}).get("conviction", "medium")
    s = float(_CONVICTION_BASE.get(conviction, 60))
    if metric and ltp and metric.get("sma_200") and ltp < metric["sma_200"] and (metric.get("rel_strength") or 0) < -5:
        s -= 15  # price below 200-DMA and lagging = thesis under pressure
    if metric and (metric.get("drawdown") or 0) < -35:
        s -= 10
    target = (meta or {}).get("target_weight_pct")
    if target and weight and weight > target * 1.5:
        s -= 10  # position much larger than the thesis warrants
    if order_flow and order_flow.get("signal") == "low":
        s -= 5
    return round(max(0, min(100, s)), 1)


def composite(subscores: dict, weights: dict | None = None) -> tuple[float | None, float, str]:
    """Return (effective_score, coverage, confidence_label). Low coverage pulls score to 50."""
    weights = weights or DEFAULT_WEIGHTS
    avail = {k: v for k, v in subscores.items() if v is not None}
    if not avail:
        return None, 0.0, "Low"
    total_avail_w = sum(weights.get(k, 0) for k in avail) or 1
    raw = sum(subscores[k] * weights.get(k, 0) for k in avail) / total_avail_w
    coverage = sum(weights.get(k, 0) for k in avail) / sum(weights.values())
    conf = 0.5 + 0.5 * coverage
    effective = 50 + (raw - 50) * conf
    return round(effective, 1), round(coverage, 2), _confidence_label(coverage)


def _confidence_label(coverage: float) -> str:
    if coverage >= 0.85:
        return "High"
    if coverage >= 0.65:
        return "Medium-High"
    if coverage >= 0.5:
        return "Medium"
    return "Low"


def _nominal_band(score: float) -> str:
    for thr, label in _THRESHOLDS:
        if score >= thr:
            return label
    return Classification.EXIT.value


def classify(score: float, prev: str | None, config: dict) -> str:
    """Map composite -> classification with a hysteresis buffer to avoid daily churn."""
    hyst = ((config.get("scoring") or {}).get("bands") or {}).get("hysteresis_points", 3)
    nominal = _nominal_band(score)
    if not prev or prev == nominal:
        return nominal

    order = [b for b, _ in _BANDS_ASC]
    if prev not in order or nominal not in order:
        return nominal
    i_prev, i_nom = order.index(prev), order.index(nominal)
    if abs(i_prev - i_nom) == 1:
        higher_idx = max(i_prev, i_nom)
        boundary = _BANDS_ASC[higher_idx][1]
        if i_nom > i_prev and score < boundary + hyst:
            return prev  # not far enough past the boundary to upgrade
        if i_nom < i_prev and score > boundary - hyst:
            return prev  # not far enough below to downgrade
    return nominal


def score_holding(holding: dict, metric: dict | None, order_flow: dict | None,
                  fundamentals: dict | None, meta: dict | None, prev: str | None, config: dict,
                  news: list | None = None) -> dict:
    from ..analytics.news import score_news_risk

    ltp = holding.get("ltp")
    weight = holding.get("weight_pct")
    target = (meta or {}).get("target_weight_pct")

    subscores = {
        "thesis": score_thesis(meta, weight, metric, ltp, order_flow),
        "fundamental": score_fundamental(fundamentals),
        "technical": score_technical(metric, ltp),
        "valuation": score_valuation(fundamentals),
        "news_risk": score_news_risk(news),   # None when no material filings -> composite renormalizes
        "portfolio_fit": score_portfolio_fit(weight, target, config),
    }
    weights = ((config.get("scoring") or {}).get("weights")) or DEFAULT_WEIGHTS
    score, coverage, conf_label = composite(subscores, weights)

    classification = classify(score, prev, config) if score is not None else Classification.HOLD.value

    flag_info = evaluate_flags({"weight_pct": weight, "ltp": ltp}, metric or {}, order_flow or {}, config)
    reasons = list(flag_info["reasons"])
    if meta and subscores["thesis"] is not None and subscores["thesis"] < 50:
        reasons.append("Thesis proxy under pressure (conviction vs price/weight)")

    # Hard overrides (§5.3): a solvency/governance breach forces Exit-Candidate.
    override = hard_override(fundamentals, config)
    if override:
        classification = Classification.EXIT.value
        reasons.insert(0, f"OVERRIDE → Exit: {override}")

    return {
        "symbol": holding["symbol"],
        "subscores": subscores,
        "composite": score,
        "coverage": coverage,
        "classification": classification,
        "confidence": conf_label,
        "reasons": reasons,
    }
