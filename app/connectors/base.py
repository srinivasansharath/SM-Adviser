"""Connector interface. Mock and Zerodha both satisfy this so the real one is a drop-in."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PortfolioConnector(ABC):
    """Read-only source of portfolio data. Kite-shaped dicts so Phase 1 swaps in cleanly."""

    name: str = "base"

    @abstractmethod
    def get_holdings(self) -> list[dict]:
        """Return long-term equity holdings (Kite `holdings()` shape)."""

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return intraday/short-term positions (Kite `positions()` shape)."""
