"""SQLAlchemy models — the audit-first schema from BUILD_PLAN §3.

Every daily run is immutable and reproducible: raw inputs are frozen in `snapshots`,
and every score/recommendation/LLM call is persisted for audit and backtesting.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    """Immutable raw payload frozen exactly as fetched from a source."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)   # holdings | positions | candles | ...
    source: Mapped[str] = mapped_column(String(64))            # mock | zerodha | nse | ...
    payload: Mapped[dict | list] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class Holding(Base):
    """Per-run position snapshot with derived weight."""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str | None] = mapped_column(String(16), nullable=True)
    qty: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    ltp: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Metric(Base):
    """Computed technicals per holding per run (Phase 2)."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    ret_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret_252d: Mapped[float | None] = mapped_column(Float, nullable=True)  # ~1 trading year
    drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_spike: Mapped[float | None] = mapped_column(Float, nullable=True)
    rel_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_200: Mapped[float | None] = mapped_column(Float, nullable=True)


class OrderFlow(Base):
    """Per-holding daily delivery-based order flow (BUILD_PLAN §5.5). Free from NSE bhavcopy."""

    __tablename__ = "order_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    traded_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_delivery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str | None] = mapped_column(String(16), nullable=True)  # high | low | normal


class MarketFlow(Base):
    """Market-wide FII/DII net activity for a run (₹ crore). Context, not per-stock."""

    __tablename__ = "market_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    fii_net: Mapped[float | None] = mapped_column(Float, nullable=True)
    dii_net: Mapped[float | None] = mapped_column(Float, nullable=True)


class Score(Base):
    """The six sub-scores from spec §8 (Phase 4)."""

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    thesis: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundamental: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation: Mapped[float | None] = mapped_column(Float, nullable=True)
    news_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    portfolio_fit: Mapped[float | None] = mapped_column(Float, nullable=True)


class Recommendation(Base):
    """Final classification with reasoning, confidence, evidence, and prev-day diff."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    classification: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prev_classification: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    format: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Event(Base):
    """Corporate action / announcement / news item feeding thesis-change detection."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)


class LLMCall(Base):
    """Cost + audit trail for every model call (spec §12)."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    model: Mapped[str] = mapped_column(String(64))
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
