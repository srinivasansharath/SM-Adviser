"""Market context — how the broad market moved, so a red portfolio can be read correctly.

A portfolio down 1.4% on a day the market is down 1.9% is a *market* day, not a stock-picking
problem. That distinction needs the index move measured over the same window and from the same
tick source as the holdings, so these helpers derive it two ways:

- **live** (`indices_from_quotes`) — from a Kite `quote()` payload, the same feed the intraday
  refresh reads holdings prices from, so the comparison is time-aligned to the minute.
- **end-of-day** (`index_from_candles`) — from the daily candles the morning run already
  fetches for rel-strength, i.e. the last completed session. That is the right number at
  08:00 IST, when "today" has not started and Kite's holdings day-change is also last session's.

Pure functions: no network, no DB.
"""

from __future__ import annotations

# NSE index -> Kite instrument key ("EXCHANGE:TRADINGSYMBOL"). Kite abbreviates the broader
# indices ("NIFTY SMLCAP 250", not "NIFTY SMALLCAP 250"), so config names are mapped, not
# formatted. Anything unmapped falls through as NSE:<name>, which is right for NIFTY 50/500.
KITE_INDEX_MAP = {
    "NIFTY 50": "NSE:NIFTY 50",
    "NIFTY 500": "NSE:NIFTY 500",
    "NIFTY BANK": "NSE:NIFTY BANK",
    "NIFTY IT": "NSE:NIFTY IT",
    "NIFTY MIDCAP 100": "NSE:NIFTY MIDCAP 100",
    "NIFTY SMALLCAP 100": "NSE:NIFTY SMLCAP 100",
    "NIFTY SMALLCAP 250": "NSE:NIFTY SMLCAP 250",
}


def kite_instrument(index: str) -> str:
    """Kite instrument key for a benchmark named the way config.yaml names it."""
    name = (index or "").strip().upper()
    return KITE_INDEX_MAP.get(name, f"NSE:{name}")


def benchmark_names(config: dict) -> list[str]:
    """The benchmarks to report, from config `portfolio.benchmarks.broad` (first = primary)."""
    broad = ((config.get("portfolio") or {}).get("benchmarks") or {}).get("broad") or ["NIFTY 50"]
    return [str(b) for b in broad]


def day_change_from_quote(q: dict) -> float | None:
    """Percent move from a Kite quote.

    Computed from `last_price` vs `ohlc.close` (the PREVIOUS session's close) rather than the
    quote's own `net_change`, which Kite commonly returns as 0 for index instruments.
    """
    if not isinstance(q, dict):
        return None
    last = q.get("last_price")
    prev = (q.get("ohlc") or {}).get("close")
    if not last or not prev:
        return None
    return round((float(last) / float(prev) - 1) * 100, 2)


def indices_from_quotes(names: list[str], quotes: dict) -> list[dict]:
    """[{name, ltp, day_change_pct}] for each benchmark that the quote payload covers."""
    out = []
    for name in names:
        q = (quotes or {}).get(kite_instrument(name))
        pct = day_change_from_quote(q)
        if pct is None:
            continue
        out.append({"name": name, "ltp": round(float(q["last_price"]), 2), "day_change_pct": pct})
    return out


def index_from_candles(name: str, candles: list[dict] | None) -> dict | None:
    """{name, ltp, day_change_pct} from the last two daily closes, or None if unavailable."""
    if not candles or len(candles) < 2:
        return None
    prev, last = candles[-2].get("close"), candles[-1].get("close")
    if not prev or not last:
        return None
    return {
        "name": name,
        "ltp": round(float(last), 2),
        "day_change_pct": round((float(last) / float(prev) - 1) * 100, 2),
    }


def build_market(indices: list[dict], source: str, portfolio_day_change_pct: float | None = None) -> dict | None:
    """Assemble the payload block, deriving the number that actually answers the question:
    how the portfolio did *relative* to its primary benchmark."""
    indices = [i for i in indices if i]
    if not indices:
        return None
    market = {"benchmark": indices[0]["name"], "indices": indices, "source": source}
    return with_vs_market(market, portfolio_day_change_pct)


def with_vs_market(market: dict | None, portfolio_day_change_pct: float | None) -> dict | None:
    """Refresh `vs_market_pct` on an existing market block (portfolio % - primary index %)."""
    if not market or not market.get("indices"):
        return market
    primary = market["indices"][0].get("day_change_pct")
    if portfolio_day_change_pct is None or primary is None:
        market["vs_market_pct"] = None
    else:
        market["vs_market_pct"] = round(portfolio_day_change_pct - primary, 2)
    return market
