"""Weekly new-stock screener (BUILD_PLAN Phase 6) — the buy-candidate funnel.

Stage 1: pull the whole universe cheaply (ScreenerBulk) and coarse-rank it, so only the most
promising ~`top_deep` names earn a per-stock deep fetch.
Stage 2: for each, deep-fetch fundamentals (multi-year growth/ROE, pledge, D-E) + compute liquidity
from candles, then score → red-flag gate → bucket. Survivors ranked by composite become the
shortlist, persisted for the app/report (and, later, the LLM deep-dive in Stage 4).

Everything is injectable (connectors, session factory, run_date) so it runs hermetically in tests.
Advisory only — it ranks and explains candidates, it never says "buy".
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone

from sqlalchemy.orm import sessionmaker

from ..analytics.screening import coarse_score, median_daily_value_cr, score_candidate
from ..config import get_settings, load_yaml_config
from ..connectors.fundamentals import FundamentalsConnector
from ..connectors.fundamentals_universe import UniverseConnector
from ..connectors.market_data import MarketDataConnector
from ..storage.db import default_session_factory
from ..storage.models import Candidate, Snapshot


def _screening_cfg(config: dict) -> dict:
    return config.get("screening") or {}


def run(
    universe: UniverseConnector,
    fundamentals: FundamentalsConnector,
    market_data: MarketDataConnector | None = None,
    session_factory: sessionmaker | None = None,
    run_date: date | None = None,
    config: dict | None = None,
    top_deep: int = 150,
    shortlist: int = 25,
    throttle: float = 0.0,
) -> dict:
    """Run the two-stage funnel and persist the shortlist. Returns a summary dict."""
    config = config if config is not None else load_yaml_config(get_settings().portfolio_config)
    session_factory = session_factory or default_session_factory()
    run_date = run_date or date.today()

    # --- Stage 1: universe -> coarse rank -> deep-fetch shortlist ---
    rows = universe.get_universe()
    ranked = sorted(rows, key=coarse_score, reverse=True)[:top_deep]

    # --- Stage 2: deep fetch + liquidity + full score ---
    scored: list[dict] = []
    for row in ranked:
        slug = row.get("symbol")
        try:
            deep = fundamentals.get_fundamentals(slug)
        except Exception:
            deep = {}
        liq = None
        if market_data is not None:
            # Screener uses a BSE scrip code as the slug for some names (all digits) -> price via BSE
            # (.BO); otherwise it's an NSE symbol. Without this those names get no liquidity reading
            # and slip past the illiquidity gate.
            exch = "BSE" if str(slug).isdigit() else row.get("exchange", "NSE")
            try:
                candles = market_data.get_daily_candles(slug, 40, exchange=exch)
                liq = median_daily_value_cr(candles)
            except Exception:
                liq = None
        merged = {**row, **deep, "median_daily_value_cr": liq}
        result = score_candidate(merged, config)
        result["market_cap"] = row.get("market_cap")
        result["data"] = merged  # keep the raw ratios for audit
        scored.append(result)
        if throttle:
            time.sleep(throttle)

    survivors = [r for r in scored if not r["excluded"] and r["composite"] is not None]
    survivors.sort(key=lambda r: r["composite"], reverse=True)
    final = survivors[:shortlist]

    # --- Persist: shortlist rows + an audit snapshot of the whole scored set ---
    with session_factory() as session:
        session.query(Candidate).filter(Candidate.run_date == run_date).delete()
        for i, r in enumerate(final, start=1):
            session.add(
                Candidate(
                    run_date=run_date, symbol=r["symbol"], rank=i, composite=r["composite"],
                    buckets=r["buckets"], market_cap=r.get("market_cap"),
                    excluded=0, red_flags=r["red_flags"], detail=r,
                )
            )
        session.query(Snapshot).filter(
            Snapshot.run_date == run_date, Snapshot.kind == "screen"
        ).delete()
        session.add(
            Snapshot(
                run_date=run_date, kind="screen", source=universe.name,
                payload={"universe": len(rows), "deep_fetched": len(ranked),
                         "excluded": sum(1 for r in scored if r["excluded"]),
                         "shortlist": [r["symbol"] for r in final]},
                fetched_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    return {
        "run_date": str(run_date),
        "universe": len(rows),
        "deep_fetched": len(ranked),
        "excluded": sum(1 for r in scored if r["excluded"]),
        "shortlist": len(final),
        "top": [{"symbol": r["symbol"], "composite": r["composite"], "buckets": r["buckets"]}
                for r in final[:10]],
    }


def main() -> None:
    from ..connectors.fundamentals import get_fundamentals
    from ..connectors.fundamentals_universe import get_universe_source
    from ..connectors.market_data import get_market_data

    settings = get_settings()
    config = load_yaml_config(settings.portfolio_config)
    cfg = _screening_cfg(config)
    screen_url = cfg.get("screen_url")
    if not screen_url:
        raise SystemExit("Set screening.screen_url in config.yaml (a public screener.in screen URL)")

    summary = run(
        universe=get_universe_source("screener_bulk", screen_url=screen_url),
        fundamentals=get_fundamentals("screener"),
        market_data=get_market_data("yfinance"),
        config=config,
        top_deep=int(cfg.get("top_deep", 150)),
        shortlist=int(cfg.get("shortlist", 25)),
        throttle=float(cfg.get("throttle_sec", 0.3)),  # be polite to screener/yfinance
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
