"""Intraday price refresh — updates only the price-derived fields in widget.json.

Runs every ~15 min during market hours (Mon-Fri 09:15-15:30 IST) so the widget's
"today" column and portfolio value stay near-live, WITHOUT re-running the heavy daily
pipeline (fundamentals / scoring / LLM narrative stay from the last full morning run).

Cheap and side-effect-free: it reads the existing widget.json, refreshes ltp / today's
change / pnl / return per holding from a live Kite holdings pull, recomputes the portfolio
totals, re-quotes the benchmark indices for market context, and writes the file back atomically.
It does NOT touch the database.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from ..analytics.market import (
    benchmark_names,
    build_market,
    indices_from_quotes,
    kite_instrument,
    with_vs_market,
)
from ..config import get_settings, load_yaml_config
from ..connectors import get_connector
from ..connectors.base import effective_qty
from ..reports.widget_json import json_safe

IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN = dt.time(9, 15)
_MARKET_CLOSE = dt.time(15, 30)


def in_market_hours(now: dt.datetime) -> bool:
    """Mon-Fri, NSE regular session. (Doesn't know exchange holidays — a holiday pull just
    returns a flat day-change, which is harmless.)"""
    if now.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    return _MARKET_OPEN <= now.timetz().replace(tzinfo=None) <= _MARKET_CLOSE


def _widget_path(config: dict) -> Path:
    out_dir = Path((config.get("report") or {}).get("output_dir", "reports_out"))
    return out_dir / "widget.json"


def _refresh_market(doc: dict, connector, config: dict) -> None:
    """Re-quote the benchmark indices off the SAME Kite feed the holdings prices came from, so
    the portfolio-vs-market comparison is aligned to the same minute (a 15-min-delayed index
    quote against live holdings would make the difference lie).

    Best-effort: on any failure the morning run's end-of-day block is left in place rather than
    blanked — stale context beats none, and `source` says where it came from.
    """
    names = benchmark_names(config)
    get_quotes = getattr(connector, "get_quotes", None)
    if not get_quotes:
        return
    try:
        quotes = get_quotes([kite_instrument(n) for n in names])
    except Exception:
        return
    indices = indices_from_quotes(names, quotes)
    if indices:
        doc["market"] = build_market(indices, getattr(connector, "name", "?"))


def run(now: dt.datetime | None = None, force: bool = False) -> dict:
    settings = get_settings()
    now = now or dt.datetime.now(IST)

    if not force and not in_market_hours(now):
        return {"skipped": "outside market hours", "at": now.isoformat(timespec="seconds")}

    config = load_yaml_config(settings.portfolio_config)
    wpath = _widget_path(config)
    if not wpath.exists():
        return {"skipped": "no widget.json yet — run the full morning job first"}

    doc = json.loads(wpath.read_text(encoding="utf-8"))
    connector = get_connector(settings.portfolio_connector, settings)
    by_sym = {h.get("tradingsymbol"): h for h in connector.get_holdings()}

    total_value = total_pnl = cost_basis = 0.0
    wacc = wsum = 0.0
    updated = 0
    for row in doc.get("holdings", []):
        h = by_sym.get(row.get("symbol"))
        if not h:
            continue
        ltp = float(h.get("last_price") or 0)
        avg = float(h.get("average_price") or 0)
        qty = effective_qty(h)
        dc = h.get("day_change_percentage")
        pnl = h.get("pnl")
        row["ltp"] = ltp
        if dc is not None:
            row["change_pct"] = round(dc, 2)
        if avg:
            row["return_pct"] = round((ltp / avg - 1) * 100, 2)
        if pnl is not None:
            row["pnl"] = round(pnl, 0)
        updated += 1
        v = ltp * qty
        total_value += v
        total_pnl += pnl or 0
        cost_basis += avg * qty
        if dc is not None:
            wacc += v * dc
            wsum += v

    p = doc.setdefault("portfolio", {})
    p["value"] = round(total_value, 2)
    p["total_pnl"] = round(total_pnl, 2)
    if cost_basis:
        p["total_return_pct"] = round(total_pnl / cost_basis * 100, 2)
    if wsum:
        p["day_change_pct"] = round(wacc / wsum, 2)

    _refresh_market(doc, connector, config)
    doc["market"] = with_vs_market(doc.get("market"), p.get("day_change_pct"))
    doc["prices_as_of"] = now.isoformat(timespec="seconds")

    tmp = wpath.with_name(wpath.name + ".tmp")
    # json_safe: prices from Kite can be NaN; strip them so the served payload stays strict-JSON.
    tmp.write_text(json.dumps(json_safe(doc), indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, wpath)  # atomic swap so the API never reads a half-written file

    return {
        "updated_holdings": updated,
        "value": p["value"],
        "vs_market_pct": (doc.get("market") or {}).get("vs_market_pct"),
        "prices_as_of": doc["prices_as_of"],
    }


def main() -> None:
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
