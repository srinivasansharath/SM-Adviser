"""Safety guardrails. The agent is read-only — order/state-changing calls must never fire.

`ReadOnlyKite` wraps a KiteConnect client and raises on any order/mutation method, so even a
bug in higher layers cannot place a trade (spec §12: "Never send order placement calls").
"""

from __future__ import annotations

# State-changing / order methods on KiteConnect that are hard-blocked.
BLOCKED_METHODS = frozenset(
    {
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_order",
        "place_gtt",
        "modify_gtt",
        "delete_gtt",
        "convert_position",
        "place_mf_order",
        "cancel_mf_order",
        "place_mf_sip",
        "modify_mf_sip",
        "cancel_mf_sip",
        "set_access_token",  # token is set at construction; block later mutation
    }
)


class OrderBlockedError(RuntimeError):
    pass


class ReadOnlyKite:
    """Transparent proxy to a KiteConnect client that blocks all order/mutation methods."""

    def __init__(self, kite):
        object.__setattr__(self, "_kite", kite)

    def __getattr__(self, name: str):
        if name in BLOCKED_METHODS:
            raise OrderBlockedError(
                f"Blocked state-changing call {name!r}: the portfolio agent is read-only."
            )
        return getattr(object.__getattribute__(self, "_kite"), name)

    def __setattr__(self, name, value):  # pragma: no cover - defensive
        raise OrderBlockedError("ReadOnlyKite is immutable.")


# --- Bounded-language enforcement for the LLM narrative (spec §4) -----------------------
# Phrases that overstate certainty / cross from decision-support into promises.
BANNED_PHRASES = (
    "guaranteed",
    "will definitely",
    "will go up",
    "will go down",
    "sure to",
    "for sure",
    "risk-free",
    "can't lose",
    "cannot lose",
    "no risk",
)


def enforce_bounded_language(text: str | None) -> tuple[str, list[str]]:
    """Return (text, violations). Flags overconfident phrasing; does not silently rewrite."""
    if not text:
        return "", []
    low = text.lower()
    violations = [p for p in BANNED_PHRASES if p in low]
    return text, violations
