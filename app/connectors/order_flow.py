"""Order-flow connectors — daily delivery data + market-wide FII/DII (BUILD_PLAN §5.5).

Same swappable pattern: interface + mock (tests/offline) + free NSE provider. Delivery %
(shares actually taken to demat vs intraday churn) is India's cleanest conviction signal and
is bhavcopy-only — the paid Kite API doesn't even have it, so this layer is free by nature.

NSE has anti-bot protection, so the live provider is best-effort and fails gracefully
(returns empty) rather than crashing the morning run. Others self-hosting can drop in a
different provider (paid data vendor) behind this same interface.

Delivery series shape (oldest -> newest):
    {"date": "2026-07-01", "traded_qty", "delivery_qty", "delivery_pct"}
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class OrderFlowConnector(ABC):
    name: str = "base"

    @abstractmethod
    def get_delivery_series(self, symbol: str, days: int, exchange: str = "NSE") -> list[dict]:
        """Recent daily delivery data for a stock."""

    @abstractmethod
    def get_market_flows(self) -> dict:
        """Latest market-wide FII/DII net figures: {'fii_net', 'dii_net'} in ₹ crore."""


class MockOrderFlow(OrderFlowConnector):
    """Deterministic synthetic order flow — no network, for tests/offline dev."""

    name = "mock"

    def get_delivery_series(self, symbol: str, days: int, exchange: str = "NSE") -> list[dict]:
        base = 40 + (sum(ord(c) for c in symbol) % 30)  # 40-70% baseline delivery
        out = []
        for i in range(days):
            dp = base + (i % 5) - 2
            traded = 100000 + i * 10
            out.append(
                {
                    "date": f"2026-05-{(i % 28) + 1:02d}",
                    "traded_qty": traded,
                    "delivery_qty": round(traded * dp / 100),
                    "delivery_pct": round(dp, 2),
                }
            )
        if out:
            out[-1]["delivery_pct"] = round(base + 15, 2)  # last-day delivery surge
        return out

    def get_market_flows(self) -> dict:
        return {"fii_net": -1200.5, "dii_net": 1500.0}


class NSEOrderFlow(OrderFlowConnector):
    """Free NSE provider (best-effort). Bootstraps cookies, then queries the historical API.

    NSE blocks non-browser clients, so all calls are wrapped to fail soft (return empty / {}).
    Delivery-percentage history accrues in our DB over time as the agent runs daily, so even
    partial coverage is fine.
    """

    name = "nse"
    _HOME = "https://www.nseindia.com"
    _HDRS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }

    def _client(self):  # pragma: no cover - network
        import httpx

        c = httpx.Client(timeout=15, headers=self._HDRS, follow_redirects=True)
        try:
            c.get(self._HOME)  # seed cookies
        except Exception:
            pass
        return c

    def get_delivery_series(self, symbol: str, days: int, exchange: str = "NSE") -> list[dict]:  # pragma: no cover - network
        try:
            with self._client() as c:
                url = (
                    f"{self._HOME}/api/historical/securityArchives"
                    f"?from=&to=&symbol={symbol}&dataType=priceVolumeDeliverable&series=ALL"
                )
                r = c.get(url)
                data = (r.json() or {}).get("data", [])
                out = []
                for row in data[:days]:
                    tq = row.get("COP_TOTAL_TRADED_QTY") or row.get("CH_TOT_TRADED_QTY")
                    dq = row.get("COP_DELIV_QTY")
                    dp = row.get("COP_DELIV_PERC")
                    out.append(
                        {
                            "date": row.get("mTIMESTAMP") or row.get("CH_TIMESTAMP"),
                            "traded_qty": float(tq) if tq else None,
                            "delivery_qty": float(dq) if dq else None,
                            "delivery_pct": float(dp) if dp else None,
                        }
                    )
                return list(reversed(out))  # API returns newest-first
        except Exception:
            return []

    def get_market_flows(self) -> dict:  # pragma: no cover - network
        try:
            with self._client() as c:
                r = c.get(f"{self._HOME}/api/fiidiiTradeReact")
                rows = r.json() or []
                fii = next((x for x in rows if "FII" in (x.get("category") or "")), {})
                dii = next((x for x in rows if "DII" in (x.get("category") or "")), {})
                return {
                    "fii_net": float(fii.get("netValue")) if fii.get("netValue") else None,
                    "dii_net": float(dii.get("netValue")) if dii.get("netValue") else None,
                }
        except Exception:
            return {}


def get_order_flow(name: str = "nse") -> OrderFlowConnector:
    name = (name or "nse").lower()
    if name == "mock":
        return MockOrderFlow()
    if name == "nse":
        return NSEOrderFlow()
    raise ValueError(f"Unknown order-flow source: {name!r} (expected 'nse' or 'mock')")
