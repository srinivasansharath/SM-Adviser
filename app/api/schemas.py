"""Pydantic models describing the API contract (spec §PROTOCOL.md).

Used to (a) generate a rich openapi.json and (b) contract-test the served payloads. Models
use the default `extra="ignore"`, so validating a payload checks that the REQUIRED fields are
present and well-typed while allowing the server to add new fields (forward-compatible).
"""

from __future__ import annotations

from datetime import datetime

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


# --- Theses (app-editable) ---
class ThesisUpsert(BaseModel):
    thesis: str | None = None
    bought_reason: str | None = None
    conviction: str | None = None          # high | medium | low
    target_weight_pct: float | None = None
    exit_if: list[str] = []


class ThesisOut(ThesisUpsert):
    symbol: str
    updated_at: datetime | None = None


# --- New-stock screener (Phase 6) ---
class CandidateOut(BaseModel):
    symbol: str
    rank: int | None = None
    composite: float | None = None
    buckets: list[str] = []
    verdict: str | None = None          # strong | watch | avoid (LLM)
    conviction: str | None = None       # high | medium | low
    thesis: str | None = None
    tailwind: str | None = None
    exit_if: list[str] = []
    risks: list[str] = []
    subscores: dict = {}
    metrics: dict = {}                   # the key ratios (roe, roce, cagrs, pe, peg, ...)


class CandidatesOut(BaseModel):
    api_version: int
    run_date: str | None = None
    universe: int | None = None
    candidates: list[CandidateOut] = []
    disclaimer: str | None = None
