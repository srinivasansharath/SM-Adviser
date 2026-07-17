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

import re
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
    """Free screener.in provider (best-effort). Parses the public company page.

    Beyond the top-ratios (P/E, ROCE, ROE, ...), it reads the deeper sections the new-stock
    screener's Stage-2 needs: multi-year growth + ROE history (durability), promoter holding +
    pledge (governance red flag), and a debt/equity proxy from the balance sheet. Each section is
    parsed defensively, so a page missing one still yields the rest. Fails soft (returns {}) so a
    single unparseable page never sinks a run; swap in a paid API behind this same interface.
    """

    name = "screener"
    _BASE = "https://www.screener.in/company"
    _HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    _MAP = {  # screener top-ratio label -> our field
        "Stock P/E": "pe",
        "ROCE": "roce",
        "ROE": "roe",
        "Dividend Yield": "dividend_yield",
        "Book Value": "book_value",
    }
    # ranges-table title -> our field prefix (yields <prefix>_5y / <prefix>_3y)
    _RANGES = {
        "Compounded Sales Growth": "sales_cagr",
        "Compounded Profit Growth": "profit_cagr",
        "Return on Equity": "roe",
    }

    @staticmethod
    def _num(text: str) -> float | None:
        try:
            return float(text.replace(",", "").replace("%", "").replace("₹", "").strip())
        except (ValueError, AttributeError):
            return None

    def _top_ratios(self, soup) -> dict:
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

    def _ranges(self, soup) -> dict:
        """Compounded Sales/Profit Growth + Return on Equity tables -> _5y / _3y fields."""
        out: dict = {}
        for tbl in soup.find_all("table", class_="ranges-table"):
            th = tbl.find("th")
            prefix = self._RANGES.get(th.get_text(strip=True)) if th else None
            if not prefix:
                continue
            for tr in tbl.find_all("tr")[1:]:
                tds = tr.find_all("td")
                if len(tds) != 2:
                    continue
                label = tds[0].get_text(strip=True)
                if label.startswith("5 Year"):
                    out[f"{prefix}_5y"] = self._num(tds[1].get_text(strip=True))
                elif label.startswith("3 Year"):
                    out[f"{prefix}_3y"] = self._num(tds[1].get_text(strip=True))
        return out

    def _shareholding(self, soup) -> dict:
        sh = soup.find(id="shareholding")
        tbl = sh.find("table") if sh else None
        if not tbl:
            return {}
        for tr in tbl.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if tds and tds[0].get_text(strip=True).startswith("Promoters"):
                return {"promoter_holding": self._num(tds[-1].get_text(strip=True))}
        return {}

    def _pledge(self, soup) -> dict:
        # Screener states pledge as an analysis bullet; absence means no pledge.
        m = re.search(r"pledged\s+([\d.]+)%\s+of their holding", soup.get_text(" ", strip=True), re.I)
        return {"promoter_pledge": self._num(m.group(1)) if m else 0.0}

    def _sector(self, soup) -> dict:
        """Screener classifies each company via /market/IN.../ links (macro sector -> industry ->
        sub-industry). The first is the macro sector we group/diversify on; the ~3rd is the industry."""
        names = [a.get_text(strip=True) for a in soup.select('a[href*="/market/IN"]')]
        # de-dup preserving order (screener repeats the sector link)
        seen, uniq = set(), []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                uniq.append(n)
        out: dict = {}
        if uniq:
            out["sector"] = uniq[0]
            if len(uniq) >= 2:
                out["industry"] = uniq[1]
        return out

    def _debt_to_equity(self, soup) -> dict:
        bs = soup.find(id="balance-sheet")
        tbl = bs.find("table") if bs else None
        if not tbl:
            return {}
        vals: dict = {}
        for tr in tbl.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue
            label = tds[0].get_text(strip=True).rstrip("+")
            if label in ("Equity Capital", "Reserves", "Borrowings"):
                vals[label] = self._num(tds[-1].get_text(strip=True))
        net_worth = (vals.get("Equity Capital") or 0) + (vals.get("Reserves") or 0)
        borrowings = vals.get("Borrowings")
        if borrowings is not None and net_worth > 0:
            return {"debt_to_equity": round(borrowings / net_worth, 2)}
        return {}

    def _parse_all(self, soup) -> dict:
        """Merge every section; each parser is defensive so a missing section drops only itself."""
        out: dict = {}
        for parser in (self._top_ratios, self._ranges, self._shareholding, self._pledge,
                       self._debt_to_equity, self._sector):
            try:
                out.update(parser(soup))
            except Exception:
                continue
        return out

    def get_fundamentals(self, symbol: str, exchange: str = "NSE") -> dict:  # pragma: no cover - network
        try:
            import httpx
            from bs4 import BeautifulSoup

            with httpx.Client(timeout=15, headers=self._HDRS, follow_redirects=True) as c:
                r = c.get(f"{self._BASE}/{symbol}/consolidated/")
                if r.status_code == 404:
                    r = c.get(f"{self._BASE}/{symbol}/")
                return self._parse_all(BeautifulSoup(r.text, "html.parser"))
        except Exception:
            return {}


def get_fundamentals(name: str = "screener") -> FundamentalsConnector:
    name = (name or "screener").lower()
    if name == "mock":
        return MockFundamentals()
    if name == "screener":
        return ScreenerFundamentals()
    raise ValueError(f"Unknown fundamentals source: {name!r} (expected 'screener' or 'mock')")
