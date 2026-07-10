"""Fundamentals connectors — quality + valuation data per stock (BUILD_PLAN §1b).

Swappable, like the other connectors: interface + mock (tests/offline) + free screener.in
provider. Screener's public company page exposes the key top-line ratios (P/E, ROCE, ROE,
dividend yield, book value); deeper fields (D/E, margins, growth, promoter pledge) need richer
parsing/login and can be layered in later or sourced from a paid provider via this same interface.

Fundamentals dict (all fields optional, None when unavailable):
    pe, industry_pe, pb, roce, roe, opm, debt_to_equity, interest_coverage,
    net_debt_ebitda, rev_growth_3y, dividend_yield, promoter_holding, promoter_pledge
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class FundamentalsConnector(ABC):
    name: str = "base"

    @abstractmethod
    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> dict:
        """Return a fundamentals dict for a stock (empty dict if unavailable)."""


class MockFundamentals(FundamentalsConnector):
    """Deterministic synthetic fundamentals — no network, for tests/offline dev."""

    name = "mock"

    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> dict:
        h = sum(ord(c) for c in symbol)
        return {
            "pe": 12 + h % 30,
            "industry_pe": 22.0,
            "pb": round(1 + (h % 40) / 10, 1),
            "roce": 8 + h % 25,
            "roe": 6 + h % 22,
            "opm": 10 + h % 20,
            "debt_to_equity": round((h % 25) / 10, 2),
            "interest_coverage": round(1 + (h % 90) / 10, 1),
            "net_debt_ebitda": round((h % 60) / 10, 1),
            "rev_growth_3y": (h % 30) - 5,
            "dividend_yield": round((h % 40) / 10, 1),
            "promoter_holding": 40 + h % 35,
            "promoter_pledge": h % 70,
        }


class ScreenerFundamentals(FundamentalsConnector):
    """Free screener.in provider (best-effort). Parses the public company page top-ratios.

    Fails soft (returns {}) so a single unparseable page never sinks the morning run. Others
    self-hosting can swap in a paid fundamentals API behind this same interface.
    """

    name = "screener"
    _BASE = "https://www.screener.in/company"
    _HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    _MAP = {  # screener label -> our field
        "Stock P/E": "pe",
        "ROCE": "roce",
        "ROE": "roe",
        "Dividend Yield": "dividend_yield",
        "Book Value": "book_value",
    }

    @staticmethod
    def _num(text: str) -> float | None:
        try:
            return float(text.replace(",", "").replace("%", "").replace("₹", "").strip())
        except (ValueError, AttributeError):
            return None

    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> dict:  # pragma: no cover - network
        try:
            import httpx
            from bs4 import BeautifulSoup

            with httpx.Client(timeout=15, headers=self._HDRS, follow_redirects=True) as c:
                r = c.get(f"{self._BASE}/{symbol}/consolidated/")
                if r.status_code == 404:
                    r = c.get(f"{self._BASE}/{symbol}/")
                soup = BeautifulSoup(r.text, "html.parser")
                ul = soup.find(id="top-ratios")
                if not ul:
                    return {}
                out: dict = {}
                for li in ul.find_all("li"):
                    name_el = li.find("span", class_="name")
                    num_el = li.find("span", class_="number")
                    if name_el and num_el:
                        label = name_el.get_text(strip=True)
                        if label in self._MAP:
                            out[self._MAP[label]] = self._num(num_el.get_text(strip=True))
                return out
        except Exception:
            return {}


def get_fundamentals(name: str = "screener") -> FundamentalsConnector:
    name = (name or "screener").lower()
    if name == "mock":
        return MockFundamentals()
    if name == "screener":
        return ScreenerFundamentals()
    raise ValueError(f"Unknown fundamentals source: {name!r} (expected 'screener' or 'mock')")
