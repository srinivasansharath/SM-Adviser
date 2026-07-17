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

from ..analytics.screening import (
    coarse_score,
    diversified_featured,
    median_daily_value_cr,
    score_candidate,
)
from ..config import get_settings, load_yaml_config
from ..connectors.fundamentals import FundamentalsConnector
from ..connectors.fundamentals_universe import UniverseConnector
from ..connectors.market_data import MarketDataConnector
from ..reasoning.llm import LLMClient
from ..storage.db import default_session_factory
from ..storage.models import Candidate, LLMCall, Snapshot


def _screening_cfg(config: dict) -> dict:
    return config.get("screening") or {}


def _screen_health(universe, fundamentals, market_data, llm, rows, scored, assessed) -> dict:
    """Per-external-API health for the weekly run — did each source return data? Feeds /status so a
    rate-limited universe scrape, a broken fundamentals page, or a failed LLM pass surfaces."""
    n = max(len(scored), 1)
    with_ratios = sum(1 for r in scored if (r.get("data") or {}).get("roe") is not None)
    with_liq = sum(1 for r in scored if (r.get("data") or {}).get("median_daily_value_cr") is not None)

    def dget(x):
        return getattr(x, "name", "?")

    health: dict = {
        "universe": {
            "source": dget(universe),
            "status": "ok" if len(rows) > 800 else "degraded",
            "detail": f"{len(rows)} names"
            + ("" if len(rows) > 800 else " (low — a band screen may be rate-limited or failing)"),
        },
        "fundamentals": {
            "source": dget(fundamentals),
            "status": "ok" if with_ratios > n * 0.5 else "degraded",
            "detail": f"{with_ratios}/{len(scored)} deep-fetched with ratios",
        },
    }
    if market_data is not None:
        health["market_data"] = {
            "source": dget(market_data),
            "status": "ok" if with_liq > n * 0.5 else "degraded",
            "detail": f"{with_liq}/{len(scored)} with a liquidity reading",
        }
    if llm is not None:
        health["llm"] = {
            "source": dget(llm),
            "status": "ok" if assessed > 0 else "degraded",
            "detail": f"{assessed} candidates assessed"
            + ("" if assessed > 0 else " (LLM call failed after retries)"),
        }
    return health


def _store_llm_call(session_factory, run_date, prompt: str, usage) -> None:
    import hashlib

    from ..reasoning.llm import estimate_cost

    with session_factory() as session:
        session.add(LLMCall(
            run_date=run_date, model=usage.model,
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:32],
            tokens=(usage.input_tokens + usage.output_tokens),
            cost=estimate_cost(usage.model, usage.input_tokens, usage.output_tokens),
            output_ref=None,
        ))
        session.commit()


def run(
    universe: UniverseConnector,
    fundamentals: FundamentalsConnector,
    market_data: MarketDataConnector | None = None,
    session_factory: sessionmaker | None = None,
    run_date: date | None = None,
    config: dict | None = None,
    llm: LLMClient | None = None,
    top_deep: int = 150,
    per_sector: int = 3,
    sectors: int = 4,
    llm_limit: int = 15,
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
    # Sector-diversified pick (top `per_sector` of each of the top `sectors` sectors) so the table
    # isn't dominated by one hot sector; grouped sector-by-sector.
    final = diversified_featured(survivors, per_sector=per_sector, sectors=sectors)

    # --- Stage 4: LLM deep-dive on the shortlist (thesis + exit_if + verdict); optional ---
    assessed = 0
    if llm is not None and final:
        from ..reasoning.screen_llm import deep_dive

        dd = deep_dive(llm, final, limit=llm_limit)
        for r in final:
            r["llm"] = dd["assessments"].get(r["symbol"])
        assessed = len(dd["assessments"])
        if dd.get("usage"):
            _store_llm_call(session_factory, run_date, dd["prompt"], dd["usage"])

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
        # External-API health for /status (parallels the morning run's run_health).
        health = _screen_health(universe, fundamentals, market_data, llm, rows, scored, assessed)
        health["universe_count"] = len(rows)
        health["shortlist"] = len(final)
        session.query(Snapshot).filter(
            Snapshot.run_date == run_date, Snapshot.kind == "screen_health"
        ).delete()
        session.add(
            Snapshot(run_date=run_date, kind="screen_health", source=universe.name,
                     payload=health, fetched_at=datetime.now(timezone.utc))
        )
        session.commit()

    return {
        "run_date": str(run_date),
        "universe": len(rows),
        "deep_fetched": len(ranked),
        "excluded": sum(1 for r in scored if r["excluded"]),
        "shortlist": len(final),
        "assessed": assessed,
        "sectors": sorted({(r.get("data") or {}).get("sector") or "Other" for r in final}),
        "top": [{"symbol": r["symbol"], "composite": r["composite"],
                 "sector": (r.get("data") or {}).get("sector"),
                 "verdict": (r.get("llm") or {}).get("verdict")}
                for r in final],
    }


def main() -> None:
    from ..connectors.fundamentals import get_fundamentals
    from ..connectors.fundamentals_universe import get_universe_source
    from ..connectors.market_data import get_market_data
    from ..reasoning.llm import get_llm

    settings = get_settings()
    config = load_yaml_config(settings.portfolio_config)
    cfg = _screening_cfg(config)
    # screen_urls (list of market-cap-band screens) is preferred; screen_url (single) still works.
    screen_urls = cfg.get("screen_urls") or cfg.get("screen_url")
    if not screen_urls:
        raise SystemExit("Set screening.screen_urls in config.yaml (public screener.in screen URLs)")

    summary = run(
        universe=get_universe_source("screener_bulk", screen_urls=screen_urls,
                                     page_delay=float(cfg.get("page_delay_sec", 2.0))),
        fundamentals=get_fundamentals("screener"),
        market_data=get_market_data("yfinance"),
        config=config,
        llm=get_llm(settings),  # None if no ANTHROPIC_API_KEY -> deep-dive skipped, ranking stands
        top_deep=int(cfg.get("top_deep", 150)),
        per_sector=int(cfg.get("per_sector", 3)),
        sectors=int(cfg.get("sectors", 4)),
        llm_limit=int(cfg.get("llm_limit", 15)),
        throttle=float(cfg.get("throttle_sec", 0.3)),  # be polite to screener/yfinance
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
