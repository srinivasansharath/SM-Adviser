"""Pydantic models describing the API contract (spec §PROTOCOL.md).

Used to (a) generate a rich openapi.json and (b) contract-test the served payloads. Models
use the default `extra="ignore"`, so validating a payload checks that the REQUIRED fields are
present and well-typed while allowing the server to add new fields (forward-compatible).
"""

from __future__ import annotations

from pydantic import BaseModel


class Meta(BaseModel):
    api_version: int
    server_version: str
    features: list[str]
    min_app_build: int


class PortfolioOut(BaseModel):
    value: float | None = None
    day_change_pct: float | None = None
    total_pnl: float | None = None
    total_return_pct: float | None = None
    attention_count: int | None = None


class HoldingOut(BaseModel):
    symbol: str
    name: str | None = None
    ltp: float | None = None
    change_pct: float | None = None      # today
    ret_20d: float | None = None         # ~1 month
    ret_252d: float | None = None        # ~1 year
    return_pct: float | None = None      # since purchase
    pnl: float | None = None
    classification: str | None = None
    confidence: str | None = None
    thesis_status: str | None = None
    flag: str | None = None


class WidgetPayload(BaseModel):
    api_version: int
    as_of: str | None = None
    prices_as_of: str | None = None
    headline: str | None = None
    portfolio: PortfolioOut
    holdings: list[HoldingOut]
    disclaimer: str | None = None
