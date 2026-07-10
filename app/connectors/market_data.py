"""Market-data connectors — swappable source of historical candles.

Same pattern as the portfolio connectors: an interface + a free default (yfinance) + a mock
for tests/offline. A paid provider (Kite historical) can be dropped in later with zero changes
to callers — which also lets others self-host with whatever data source they have.

Candle shape (JSON-friendly, oldest -> newest):
    {"date": "2026-07-01", "open", "high", "low", "close", "volume"}
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# NSE index -> Yahoo Finance symbol (for the free provider).
YF_INDEX_MAP = {
    "NIFTY 50": "^NSEI",
    "NIFTY 500": "^CRSLDX",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
}


class MarketDataConnector(ABC):
    name: str = "base"

    @abstractmethod
    def get_daily_candles(self, symbol: str, days: int, exchange: str = "NSE") -> list[dict]:
        """Return the last `days` daily candles for a stock, oldest -> newest."""

    @abstractmethod
    def get_index_candles(self, index: str, days: int) -> list[dict]:
        """Return the last `days` daily candles for a benchmark index."""


class MockMarketData(MarketDataConnector):
    """Deterministic synthetic candles — no network, for tests and offline dev."""

    name = "mock"

    def _series(self, seed: str, days: int) -> list[dict]:
        base = 100 + (sum(ord(c) for c in seed) % 50)
        out = []
        for i in range(days):
            close = base + i * 0.5  # gently rising series
            out.append(
                {
                    "date": f"2026-05-{(i % 28) + 1:02d}",
                    "open": round(close - 1, 2),
                    "high": round(close + 1, 2),
                    "low": round(close - 2, 2),
                    "close": round(close, 2),
                    "volume": 100000 + i * 10,
                }
            )
        if out:
            out[-1]["volume"] = 500000  # a volume spike on the last day
        return out

    def get_daily_candles(self, symbol: str, days: int, exchange: str = "NSE") -> list[dict]:
        return self._series(symbol, days)

    def get_index_candles(self, index: str, days: int) -> list[dict]:
        return self._series(index, days)


class YFinanceMarketData(MarketDataConnector):
    """Free EOD candles via Yahoo Finance. Split/bonus-adjusted (auto_adjust=True)."""

    name = "yfinance"

    def _download(self, ticker: str, days: int) -> list[dict]:
        import yfinance as yf  # local import keeps yfinance optional

        # Pull extra calendar days to be sure we net `days` trading rows.
        df = yf.download(
            ticker, period=f"{days * 2 + 15}d", interval="1d", auto_adjust=True, progress=False
        )
        if df is None or df.empty:
            return []
        import pandas as pd

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.tail(days)
        candles = []
        for idx, row in df.iterrows():
            candles.append(
                {
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                }
            )
        return candles

    def get_daily_candles(self, symbol: str, days: int, exchange: str = "NSE") -> list[dict]:
        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        return self._download(symbol + suffix, days)

    def get_index_candles(self, index: str, days: int) -> list[dict]:
        return self._download(YF_INDEX_MAP.get(index, index), days)


def get_market_data(name: str = "yfinance") -> MarketDataConnector:
    name = (name or "yfinance").lower()
    if name == "mock":
        return MockMarketData()
    if name == "yfinance":
        return YFinanceMarketData()
    raise ValueError(f"Unknown market-data source: {name!r} (expected 'yfinance' or 'mock')")
