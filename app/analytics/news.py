"""News-risk sub-score over corporate announcements (BSE filings).

Deterministic and deliberately conservative: the `news_risk` sub-score only *nudges* the composite
(weight 0.12), and returns None when there are no material filings so the composite renormalizes
(no news != bad news). The nuanced judgement — does a filing actually implicate an `exit_if`
condition — is left to the LLM layer, which gets the same headlines.
"""

from __future__ import annotations

import datetime as dt

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


def _age_days(date_s: str | None, today: dt.date) -> int | None:
    try:
        return (today - dt.date.fromisoformat((date_s or "")[:10])).days
    except ValueError:
        return None


def _recency_weight(date_s: str | None, today: dt.date) -> float:
    """Recent filings matter more; old ones are likely already priced in."""
    age = _age_days(date_s, today)
    if age is None:
        return 0.5
    if age <= 2:
        return 1.0
    if age <= 7:
        return 0.7
    if age <= 15:
        return 0.5
    return 0.3


def has_negative_news(items: list[dict] | None, within_days: int = 10, today: dt.date | None = None) -> bool:
    """True if a RECENT (<= within_days) material filing looks negative — raises 'needs attention'.
    An old negative is stale, so it doesn't keep flagging."""
    today = today or dt.date.today()
    for it in material_items(items):
        age = _age_days(it.get("date"), today)
        if age is not None and age > within_days:
            continue
        t = f"{it.get('subcategory','')} {it.get('headline','')}".lower()
        if any(k in t for k in _NEGATIVE) or any(k in t for k in _DILUTIVE):
            return True
    return False


def score_news_risk(items: list[dict] | None, today: dt.date | None = None) -> float | None:
    """0-100 (higher = healthier). None when there are no material filings. Each filing's impact
    is scaled by how recent it is."""
    mats = material_items(items)
    if not mats:
        return None
    today = today or dt.date.today()
    score = 65.0
    for it in mats:
        w = _recency_weight(it.get("date"), today)
        t = f"{it.get('subcategory','')} {it.get('headline','')}".lower()
        if any(k in t for k in _NEGATIVE):
            score -= 9 * w
        elif any(k in t for k in _DILUTIVE):
            score -= 6 * w      # dilution is cautionary, not alarming
        elif any(k in t for k in _POSITIVE):
            score += 5 * w
    return max(0.0, min(100.0, round(score, 1)))
