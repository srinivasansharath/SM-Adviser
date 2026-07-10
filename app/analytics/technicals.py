"""Technical metrics computed from daily candles (BUILD_PLAN §5.1 Technical sub-score inputs).

Pure functions over a candle list (oldest -> newest). Return None when there isn't enough
history, so callers store nulls rather than crashing. RSI uses simple-moving-average smoothing.
"""

from __future__ import annotations

import pandas as pd


def _closes(candles: list[dict]) -> pd.Series:
    return pd.Series([c["close"] for c in candles], dtype=float)


def _volumes(candles: list[dict]) -> pd.Series:
    return pd.Series([c.get("volume", 0) for c in candles], dtype=float)


def pct_return(candles: list[dict], n: int) -> float | None:
    s = _closes(candles)
    if len(s) <= n or s.iloc[-1 - n] == 0:
        return None
    return round((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 2)


def sma(candles: list[dict], n: int) -> float | None:
    s = _closes(candles)
    if len(s) < n:
        return None
    return round(s.tail(n).mean(), 2)


def rsi(candles: list[dict], period: int = 14) -> float | None:
    s = _closes(candles)
    if len(s) < period + 1:
        return None
    delta = s.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def max_drawdown(candles: list[dict]) -> float | None:
    s = _closes(candles)
    if s.empty:
        return None
    dd = (s / s.cummax() - 1) * 100
    return round(dd.min(), 2)


def volume_spike(candles: list[dict], n: int = 20) -> float | None:
    """Latest volume as a multiple of the average of the prior `n` days (1.0 = average)."""
    v = _volumes(candles)
    if len(v) < n + 1:
        return None
    prior_avg = v.iloc[-(n + 1) : -1].mean()
    if prior_avg == 0:
        return None
    return round(v.iloc[-1] / prior_avg, 2)


def relative_strength(candles: list[dict], index_candles: list[dict] | None, n: int = 20) -> float | None:
    """Stock's n-day return minus the benchmark's n-day return (percentage points)."""
    if not index_candles:
        return None
    r_stock = pct_return(candles, n)
    r_index = pct_return(index_candles, n)
    if r_stock is None or r_index is None:
        return None
    return round(r_stock - r_index, 2)


def compute_metrics(candles: list[dict], index_candles: list[dict] | None = None) -> dict:
    """The Metric-table row values for one holding."""
    return {
        "ret_1d": pct_return(candles, 1),
        "ret_5d": pct_return(candles, 5),
        "ret_20d": pct_return(candles, 20),
        "drawdown": max_drawdown(candles),
        "rsi": rsi(candles, 14),
        "vol_spike": volume_spike(candles, 20),
        "rel_strength": relative_strength(candles, index_candles, 20),
        "sma_20": sma(candles, 20),
        "sma_50": sma(candles, 50),
        "sma_200": sma(candles, 200),
    }
