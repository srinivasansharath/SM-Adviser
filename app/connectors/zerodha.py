"""Zerodha Kite connector — read-only holdings/positions (Phase 1).

Only the read endpoints are implemented, and the client is wrapped in ReadOnlyKite so order
APIs cannot fire even by accident. The daily access token comes from app.auth.kite_login.
"""

from __future__ import annotations

from ..safety.guardrails import ReadOnlyKite
from .base import PortfolioConnector


class ZerodhaConnector(PortfolioConnector):
    name = "zerodha"

    def __init__(self, access_token: str | None = None, api_key: str | None = None, kite_client=None):
        self._api_key = api_key
        self._access_token = access_token
        # kite_client is injectable for tests; otherwise built lazily from kiteconnect.
        self._kite = ReadOnlyKite(kite_client) if kite_client is not None else None

    def _client(self) -> ReadOnlyKite:
        if self._kite is None:
            from kiteconnect import KiteConnect  # local import keeps kiteconnect optional

            kite = KiteConnect(api_key=self._api_key)
            if self._access_token:
                kite.set_access_token(self._access_token)
            self._kite = ReadOnlyKite(kite)
        return self._kite

    def get_holdings(self) -> list[dict]:
        return list(self._client().holdings())

    def get_positions(self) -> list[dict]:
        pos = self._client().positions()
        # Kite returns {"net": [...], "day": [...]}; long-term view uses net.
        return list(pos.get("net", []) if isinstance(pos, dict) else pos)
