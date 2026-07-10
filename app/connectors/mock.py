"""Mock connector — lets the whole pipeline run with zero credentials (Phase 0)."""

from __future__ import annotations

import json
from pathlib import Path

from .base import PortfolioConnector

_DEFAULT_DATA = Path(__file__).parent / "mock_portfolio.json"


class MockConnector(PortfolioConnector):
    name = "mock"

    def __init__(self, data_path: str | Path | None = None):
        self._path = Path(data_path) if data_path else _DEFAULT_DATA
        with self._path.open("r", encoding="utf-8") as f:
            self._data = json.load(f)

    def get_holdings(self) -> list[dict]:
        return list(self._data.get("holdings", []))

    def get_positions(self) -> list[dict]:
        return list(self._data.get("positions", []))
