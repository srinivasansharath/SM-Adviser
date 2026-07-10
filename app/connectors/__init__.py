"""Connector factory."""

from __future__ import annotations

from ..config import Settings, get_settings
from .base import PortfolioConnector
from .mock import MockConnector


def get_connector(name: str, settings: Settings | None = None) -> PortfolioConnector:
    name = (name or "mock").lower()
    if name == "mock":
        return MockConnector()
    if name == "zerodha":
        # Local imports keep kiteconnect/httpx optional for Phase 0 / mock runs.
        from ..auth.kite_login import get_access_token
        from .zerodha import ZerodhaConnector

        s = settings or get_settings()
        access_token = get_access_token(s)  # cached per day, or headless-login refresh
        return ZerodhaConnector(access_token=access_token, api_key=s.kite_api_key)
    raise ValueError(f"Unknown connector: {name!r} (expected 'mock' or 'zerodha')")
