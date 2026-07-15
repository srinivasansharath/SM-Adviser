"""News-risk sub-score over corporate announcements (BSE filings).

Deterministic and deliberately conservative: the `news_risk` sub-score only *nudges* the composite
(weight 0.12), and returns None when there are no material filings so the composite renormalizes
(no news != bad news). The nuanced judgement — does a filing actually implicate an `exit_if`
condition — is left to the LLM layer, which gets the same headlines.
"""

from __future__ import annotations

# Directional keywords, matched against subcategory + headline. Ambiguous events (credit rating
# with no direction, generic management change, results with no numbers) stay neutral.
_NEGATIVE = (
    "resignation", "resign", "downgrade", "pledge", "litigation", "penalty", "sebi order",
    "fraud", "default", "clarification sought", "auditor", "qualified opinion", "insolvency",
    "nclt", "delisting", "investigation", "lock-out", "strike", "recall", "guidance cut",
)
_DILUTIVE = ("fund raising", "fund-raising", "preferential", "warrant", "qip", "rights issue")
_POSITIVE = (
    "order received", "award of order", "bags order", "wins order", "new order win", "buyback",
    "bonus", "dividend", "record date", "highest ever", "record profit",
)


def material_items(items: list[dict] | None) -> list[dict]:
    return [i for i in (items or []) if i.get("material")]


def has_negative_news(items: list[dict] | None) -> bool:
    """True if any material filing looks negative — used to raise 'needs attention'."""
    for it in material_items(items):
        t = f"{it.get('subcategory','')} {it.get('headline','')}".lower()
        if any(k in t for k in _NEGATIVE) or any(k in t for k in _DILUTIVE):
            return True
    return False


def score_news_risk(items: list[dict] | None) -> float | None:
    """0-100 (higher = healthier). None when there are no material filings."""
    mats = material_items(items)
    if not mats:
        return None
    score = 65.0
    for it in mats:
        t = f"{it.get('subcategory','')} {it.get('headline','')}".lower()
        if any(k in t for k in _NEGATIVE):
            score -= 9
        elif any(k in t for k in _DILUTIVE):
            score -= 6      # dilution is cautionary, not alarming
        elif any(k in t for k in _POSITIVE):
            score += 5
    return max(0.0, min(100.0, round(score, 1)))
