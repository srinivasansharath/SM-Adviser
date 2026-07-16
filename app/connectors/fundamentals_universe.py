"""Bulk universe fundamentals — the Stage-1 feed for the new-stock screener (BUILD_PLAN Phase 6).

Where `fundamentals.py` fetches deep ratios for ONE stock (the per-holding morning path), this
pulls a WHOLE universe of stocks + key ratios in one paginated sweep, cheaply, so the screener can
rank hundreds of candidates without a page-fetch per name.

Design finding (prototype, 2026-07-16): screener.in's custom-query endpoint (`/screen/raw/`) is
login-gated, BUT **public saved screens render fully without login** and expose whatever **custom
columns** the screen's author added. So the free approach is: create ONE public screen carrying a
broad pre-filter + the exact ratio columns we want, then scrape its public URL page by page. No
credentials at scrape time. Swap in a paid provider later behind this same interface.

Each row is returned as {"symbol", plus any mapped ratio fields}. All fields best-effort / optional.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class UniverseConnector(ABC):
    name: str = "base"

    @abstractmethod
    def get_universe(self) -> list[dict]:
        """Return a list of {symbol, ...ratios} for the screened universe (empty on failure)."""


class MockUniverse(UniverseConnector):
    """Deterministic synthetic universe — no network, for tests/offline dev."""

    name = "mock"
    _SYMS = ("TCS", "INFY", "HDFCBANK", "TATAPOWER", "SEPC", "TATACHEM", "SBIN", "YESBANK")

    def get_universe(self) -> list[dict]:
        out = []
        for s in self._SYMS:
            h = sum(ord(c) for c in s)
            out.append({
                "symbol": s,
                "cmp": 100 + h % 900,
                "pe": 8 + h % 40,
                "market_cap": 500 + h * 37,
                "roce": 6 + h % 30,
                "roe": 5 + h % 28,
                "dividend_yield": round((h % 40) / 10, 1),
                "sales_cagr_5y": (h % 35) - 5,
                "profit_cagr_5y": (h % 40) - 8,
                "debt_to_equity": round((h % 25) / 10, 2),
                "promoter_holding": 40 + h % 35,
                "promoter_pledge": h % 60,
            })
        return out


class ScreenerBulk(UniverseConnector):
    """Free screener.in provider: scrapes a PUBLIC saved screen's paginated results table.

    You create the screen once (see SELF_HOSTING / Phase-6 notes): pick a broad server-side filter
    and add the custom columns below, mark it Public, and put its URL in config. Fails soft (returns
    what it parsed) so a flaky page never sinks the weekly run.
    """

    name = "screener_bulk"
    _HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    # Normalised screener column header -> our field. Header text is normalised by _norm_header
    # (drops the "Rs.Cr." / "%" unit suffixes) so it's robust to screener's inline units.
    _COLMAP = {
        "CMP": "cmp",
        "P/E": "pe",
        "Mar Cap": "market_cap",
        "Div Yld": "dividend_yield",
        "ROCE": "roce",
        "ROE": "roe",
        "Qtr Profit Var": "profit_growth_qtr",
        "Qtr Sales Var": "sales_growth_qtr",
        # custom columns you add to the screen (header text must match, case-insensitive):
        "Debt to equity": "debt_to_equity",
        "Sales growth 5Years": "sales_cagr_5y",
        "Profit growth 5Years": "profit_cagr_5y",
        "Promoter holding": "promoter_holding",
        "Pledged percentage": "promoter_pledge",
    }

    def __init__(self, screen_url: str, max_pages: int = 100, client=None):
        # screen_url is the public screen page, e.g. https://www.screener.in/screens/357649/my-screen/
        self._url = screen_url.split("?")[0].rstrip("/") + "/"
        self._max_pages = max_pages
        self._client = client  # injectable for tests

    @staticmethod
    def _num(text: str) -> float | None:
        try:
            return float(text.replace(",", "").replace("%", "").replace("₹", "").strip())
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _norm_header(text: str) -> str:
        """'Mar CapRs.Cr.' -> 'Mar Cap', 'Div Yld%' -> 'Div Yld', 'ROCE%' -> 'ROCE'."""
        t = re.split(r"Rs\.|%", text or "")[0]
        return re.sub(r"\s+", " ", t).strip()

    def _field_index(self, header_cells: list[str]) -> dict[int, str]:
        """Map column index -> our field name, by (normalised) header text, case-insensitive."""
        lookup = {k.lower(): v for k, v in self._COLMAP.items()}
        idx: dict[int, str] = {}
        for i, h in enumerate(header_cells):
            field = lookup.get(self._norm_header(h).lower())
            if field:
                idx[i] = field
        return idx

    def _parse_page(self, html: str) -> list[dict]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="data-table")
        if not table:
            return []
        header_cells = [th.get_text(strip=True) for th in table.find_all("th")]
        col_field = self._field_index(header_cells)

        rows: list[dict] = []
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue  # header / spacer / total rows
            a = tr.find("a", href=re.compile(r"^/company/"))
            if not a:
                continue
            symbol = re.match(r"^/company/([^/]+)/", a["href"]).group(1)
            row: dict = {"symbol": symbol}
            for i, td in enumerate(tds):
                field = col_field.get(i)
                if field:
                    row[field] = self._num(td.get_text(strip=True))
            rows.append(row)
        return rows

    def get_universe(self) -> list[dict]:  # pragma: no cover - network
        try:
            import httpx
        except Exception:
            return []
        close = self._client is None
        client = self._client or httpx.Client(timeout=25, headers=self._HDRS, follow_redirects=True)
        out: list[dict] = []
        seen: set[str] = set()
        try:
            for page in range(1, self._max_pages + 1):
                try:
                    r = client.get(self._url, params={"page": page})
                    rows = self._parse_page(r.text)
                except Exception:
                    break  # transient page failure — stop, keep what we have (fail soft)
                if not rows:
                    break  # past the last page
                fresh = [row for row in rows if row["symbol"] not in seen]
                if not fresh:
                    break  # screener repeats the last page past the end — guard against a loop
                for row in fresh:
                    seen.add(row["symbol"])
                out.extend(fresh)
                if len(rows) < 25:
                    break  # short page = last page
        finally:
            if close:
                client.close()
        return out


def get_universe_source(name: str = "screener_bulk", screen_url: str | None = None) -> UniverseConnector:
    name = (name or "screener_bulk").lower()
    if name == "mock":
        return MockUniverse()
    if name == "screener_bulk":
        if not screen_url:
            raise ValueError("screener_bulk needs a public screen URL (config: screening.screen_url)")
        return ScreenerBulk(screen_url)
    raise ValueError(f"Unknown universe source: {name!r} (expected 'screener_bulk' or 'mock')")
