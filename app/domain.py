"""Shared domain vocabulary — the bounded language the spec mandates for recommendations."""

from __future__ import annotations

from enum import Enum


class Classification(str, Enum):
    """The only allowed action labels. No free-form 'buy/sell now' language (spec §4)."""

    HOLD = "Hold"
    WATCH = "Watch"
    ACCUMULATE = "Accumulate Candidate"
    TRIM = "Trim Candidate"
    EXIT = "Exit Candidate"


class Confidence(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    MEDIUM_HIGH = "Medium-High"
    HIGH = "High"


# The six sub-scores from spec §8. Thresholds/weights get filled in Phase 4/5.
SCORE_DIMENSIONS = (
    "thesis",
    "fundamental",
    "technical",
    "valuation",
    "news_risk",
    "portfolio_fit",
)
