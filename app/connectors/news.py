"""Corporate-announcement news — swappable like the other connectors.

Primary source: **BSE official filings** (high-signal, low-noise, and directly aligned with the
kind of events `exit_if` conditions describe — results, board meetings, management/auditor changes,
pledges, ratings, corporate actions, litigation). NSE tradingsymbol -> BSE scrip code via a curated
map for now; production should resolve via ISIN / the BSE scrip master.

BSE's date-range params are unreliable, so we fetch the latest announcements and filter by date
client-side. Degrades gracefully (returns []) on any network/parse failure, like order-flow.
"""

from __future__ import annotations

import datetime as dt
import re
from abc import ABC, abstractmethod

_BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
_BSE_SEARCH = "https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearch/w"
_BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Referer": "https://www.bseindia.com/corporates/ann.html",
    "Accept": "application/json, text/plain, */*",
}
_ATTACH = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

# NSE tradingsymbol -> BSE scrip code (fast path). Anything not here is resolved by ISIN.
BSE_SCRIP = {
    "TCS": 532540, "INFY": 500209, "SBIN": 500112, "YESBANK": 532648,
    "TATACHEM": 500770, "TATAPOWER": 500400, "SEPC": 532945, "RELIANCE": 500325,
    "HDFCBANK": 500180, "ICICIBANK": 532174, "ITC": 500875, "LT": 500510,
    "MARUTI": 532500, "HINDUNILVR": 500696, "WIPRO": 507685, "AXISBANK": 532215,
}

_ISIN_CACHE: dict[str, int | None] = {}


def resolve_scrip_by_isin(isin: str | None) -> int | None:
    """ISIN -> BSE scrip code via BSE's smart-search (the site's search box). Cached."""
    if not isin:
        return None
    isin = isin.strip().upper()
    if isin in _ISIN_CACHE:
        return _ISIN_CACHE[isin]
    code = None
    try:
        import httpx

        r = httpx.get(_BSE_SEARCH, params={"Type": "SS", "text": isin},
                      headers=_BSE_HEADERS, timeout=15)
        text = r.text or ""
        # The response is HTML <li> items; match the segment carrying this exact ISIN.
        for seg in text.split("<li"):
            if isin in seg.upper():
                m = re.search(r"liclick\('(\d+)'", seg)
                if m:
                    code = int(m.group(1))
                    break
    except Exception:
        code = None
    _ISIN_CACHE[isin] = code
    return code

# High-signal event keywords (matched against category + subcategory). "Regulation 30" is NOT
# here — it's in nearly every filing, so it's useless as a materiality signal.
_MATERIAL_KEYS = (
    "result", "board meeting", "dividend", "corp. action", "corporate action", "amalgamation",
    "merger", "change in management", "change in director", "credit rating", "acquisition",
    "scheme of arrangement", "resignation", "retirement", "litigation", "order received",
    "award of order", "fund raising", "fund-raising", "pledge", "delisting", "buyback", "bonus",
    "stock split", "postal ballot", "agm", "egm", "clarification", "sast",
)
# Routine/noise subcategories — filed constantly, not decision-relevant.
_NOISE_KEYS = ("newspaper", "advertisement", "trading window", "investor meet", "analyst meet")


def _is_material(category: str, subcat: str, headline: str, critical) -> bool:
    if str(critical).strip() in ("1", "Y", "true", "True"):
        return True
    text = f"{category} {subcat} {headline}".lower()
    if any(k in text for k in _NOISE_KEYS):
        return False
    return any(k in text for k in _MATERIAL_KEYS)


class NewsConnector(ABC):
    name = "base"

    @abstractmethod
    def get_announcements(self, symbol: str, days: int = 30, exchange: str = "NSE",
                          isin: str | None = None) -> list[dict]:
        """Return recent announcements as
        [{date, headline, category, subcategory, material, url, source}] (newest first)."""


class MockNews(NewsConnector):
    name = "mock"

    def get_announcements(self, symbol: str, days: int = 30, exchange: str = "NSE",
                          isin: str | None = None) -> list[dict]:
        return [{
            "date": "2026-07-12", "headline": f"{symbol} Q1 results: revenue up 8% YoY",
            "category": "Result", "subcategory": "Financial Results", "material": True,
            "url": "https://example.com/filing.pdf", "source": "mock",
        }]


class BSEAnnouncements(NewsConnector):
    name = "bse"

    def get_announcements(self, symbol: str, days: int = 30, exchange: str = "NSE",
                          isin: str | None = None) -> list[dict]:  # pragma: no cover - network
        import httpx

        code = BSE_SCRIP.get(symbol.upper()) or resolve_scrip_by_isin(isin)
        if not code:
            return []
        params = {
            "pageno": 1, "strCat": "-1", "strPrevDate": "", "strScrip": str(code),
            "strSearch": "P", "strToDate": "", "strType": "C", "subcategory": "-1",
        }
        try:
            r = httpx.get(_BSE_URL, params=params, headers=_BSE_HEADERS, timeout=20)
            data = r.json()
        except Exception:
            return []
        if not isinstance(data, dict):
            return []

        cutoff = dt.date.today() - dt.timedelta(days=days)
        out: list[dict] = []
        for row in data.get("Table", []):
            date_s = str(row.get("NEWS_DT") or row.get("DT_TM") or "")[:10]
            try:
                if dt.date.fromisoformat(date_s) < cutoff:
                    continue
            except ValueError:
                pass
            att = row.get("ATTACHMENTNAME") or ""
            cat = (row.get("CATEGORYNAME") or "").strip()
            sub = (row.get("SUBCATNAME") or "").strip()
            headline = (row.get("NEWSSUB") or row.get("HEADLINE") or "").strip()
            out.append({
                "date": date_s,
                "headline": headline,
                "category": cat,
                "subcategory": sub,
                "material": _is_material(cat, sub, headline, row.get("CRITICALNEWS")),
                "url": (_ATTACH + att) if att else (row.get("NSURL") or ""),
                "source": "bse",
            })
        return out


def get_news(name: str = "bse") -> NewsConnector:
    name = (name or "bse").lower()
    if name == "mock":
        return MockNews()
    if name == "bse":
        return BSEAnnouncements()
    raise ValueError(f"Unknown news source: {name!r} (expected 'bse' or 'mock')")
