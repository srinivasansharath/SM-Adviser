"""Connector interface. Mock and Zerodha both satisfy this so the real one is a drop-in."""

from __future__ import annotations

from abc import ABC, abstractmethod


def effective_qty(h: dict) -> float:
    """Shares actually owned — settled or not.

    Kite splits a holding across `quantity` (settled, sitting in demat) and `t1_quantity` (bought
    inside the T+1 settlement window, not yet credited). A stock bought today therefore arrives as
    `quantity=0, t1_quantity=N`, so counting only `quantity` values a real position at zero: the
    portfolio total is understated by the whole purchase and every weight derived from it is wrong.
    Kite's own app counts these shares as held, so we do too.

    This is NOT the same as the deliberate zero-qty mirroring of *exited* positions — those really
    are zero on both fields, and still show until settlement purges them from Kite.
    """
    return float(h.get("quantity") or 0) + float(h.get("t1_quantity") or 0)


class PortfolioConnector(ABC):
    """Read-only source of portfolio data. Kite-shaped dicts so Phase 1 swaps in cleanly."""

    name: str = "base"

    @abstractmethod
    def get_holdings(self) -> list[dict]:
        """Return long-term equity holdings (Kite `holdings()` shape)."""

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return intraday/short-term positions (Kite `positions()` shape)."""

    def get_quotes(self, instruments: list[str]) -> dict:
        """Live quotes keyed by "EXCHANGE:TRADINGSYMBOL" (Kite `quote()` shape).

        Optional, and deliberately not abstract: a connector with no quote feed returns {} and
        callers fall back to their end-of-day source rather than failing. Used for index quotes,
        so the market comparison comes off the same tick as the holdings prices.
        """
        return {}
