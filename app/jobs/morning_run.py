"""Daily morning orchestrator.

Phase 0/1: authenticate, fetch holdings, freeze a snapshot, persist per-holding rows.
Phase 2: if a market-data connector is supplied, fetch candles per holding + benchmark and
store technical metrics (returns, RSI, drawdown, rel-strength, 20/50/200-DMA); if an
order-flow connector is supplied, store delivery-based order flow + market-wide FII/DII.

Everything is injectable (connectors, session factory, run_date) so tests run hermetically.
The run is idempotent per run_date: re-running replaces that day's rows.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from ..analytics.order_flow import compute_delivery_signal
from ..analytics.technicals import compute_metrics
from ..config import get_settings, load_yaml_config
from ..connectors import get_connector
from ..connectors.base import PortfolioConnector
from ..connectors.fundamentals import FundamentalsConnector
from ..connectors.market_data import MarketDataConnector
from ..connectors.order_flow import OrderFlowConnector
from ..reasoning.llm import LLMClient
from ..reasoning.narrative import generate_narrative
from ..reasoning.prompts import build_user_prompt
from ..reasoning.recommender import run_scoring
from ..reports.daily_report import exec_summary_line, write_report
from ..reports.gather import gather_report_data
from ..reports.widget_json import write_widget
from ..storage.db import default_session_factory
from ..storage.models import Holding, LLMCall, MarketFlow, Metric, OrderFlow, Report, Snapshot

# Enough history for the 200-day moving average; short-window metrics use the tail.
_MA_HISTORY_DAYS = 210


def _holding_value(h: dict) -> float:
    return float(h.get("last_price", 0)) * float(h.get("quantity", 0))


def _lookback(config: dict) -> int:
    return int((config.get("analytics") or {}).get("lookback_trading_days", 24))


def _store_metrics(
    session_factory: sessionmaker,
    run_date: date,
    holdings: list[dict],
    market_data: MarketDataConnector,
    config: dict,
) -> int:
    candle_days = max(_lookback(config) + 5, _MA_HISTORY_DAYS)
    benchmarks = ((config.get("portfolio") or {}).get("benchmarks") or {}).get("broad") or ["NIFTY 50"]
    try:
        index_candles = market_data.get_index_candles(benchmarks[0], candle_days)
    except Exception:
        index_candles = None

    count = 0
    with session_factory() as session:
        session.query(Metric).filter(Metric.run_date == run_date).delete()
        for h in holdings:
            symbol = h["tradingsymbol"]
            try:
                candles = market_data.get_daily_candles(symbol, candle_days, exchange=h.get("exchange", "NSE"))
            except Exception:
                continue  # one bad symbol shouldn't sink the whole run
            if not candles:
                continue
            session.add(Metric(run_date=run_date, symbol=symbol, **compute_metrics(candles, index_candles)))
            count += 1
        session.commit()
    return count


def _store_order_flow(
    session_factory: sessionmaker,
    run_date: date,
    holdings: list[dict],
    order_flow: OrderFlowConnector,
    config: dict,
) -> int:
    lookback = _lookback(config)
    count = 0
    with session_factory() as session:
        session.query(OrderFlow).filter(OrderFlow.run_date == run_date).delete()
        session.query(MarketFlow).filter(MarketFlow.run_date == run_date).delete()

        for h in holdings:
            symbol = h["tradingsymbol"]
            try:
                series = order_flow.get_delivery_series(symbol, lookback, exchange=h.get("exchange", "NSE"))
            except Exception:
                series = []
            row = compute_delivery_signal(series)
            if row["delivery_pct"] is None:
                continue  # no data (e.g. NSE blocked) -> skip rather than store an empty row
            session.add(OrderFlow(run_date=run_date, symbol=symbol, **row))
            count += 1

        try:
            flows = order_flow.get_market_flows()
        except Exception:
            flows = {}
        if flows.get("fii_net") is not None or flows.get("dii_net") is not None:
            session.add(MarketFlow(run_date=run_date, fii_net=flows.get("fii_net"), dii_net=flows.get("dii_net")))
        session.commit()
    return count


def _store_llm_call(session_factory, run_date: date, prompt: str, usage) -> None:
    import hashlib

    with session_factory() as session:
        session.add(
            LLMCall(
                run_date=run_date,
                model=usage.model,
                prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:32],
                tokens=(usage.input_tokens + usage.output_tokens),
                cost=None,  # derivable from tokens; exact rate left to the caller
                output_ref=None,
            )
        )
        session.commit()


def _render_outputs(session_factory: sessionmaker, run_date: date, config: dict, data: dict,
                    narrative: dict | None) -> dict:
    """Build the markdown/HTML report + widget.json from gathered data; record Report rows."""
    output_dir = Path((config.get("report") or {}).get("output_dir", "reports_out"))
    md_path, html_path = write_report(data, output_dir, narrative=narrative)
    as_of = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    widget_path = write_widget(data, output_dir, as_of=as_of, narrative=narrative)

    with session_factory() as session:
        session.query(Report).filter(Report.run_date == run_date).delete()
        session.add(Report(run_date=run_date, format="markdown", path=str(md_path), summary=exec_summary_line(data)))
        session.add(Report(run_date=run_date, format="html", path=str(html_path)))
        session.add(Report(run_date=run_date, format="widget", path=str(widget_path)))
        session.commit()

    return {"report": str(md_path), "html": str(html_path), "widget": str(widget_path)}


def run(
    connector: PortfolioConnector | None = None,
    session_factory: sessionmaker | None = None,
    run_date: date | None = None,
    config: dict | None = None,
    market_data: MarketDataConnector | None = None,
    order_flow: OrderFlowConnector | None = None,
    fundamentals: FundamentalsConnector | None = None,
    theses: dict | None = None,
    llm: LLMClient | None = None,
    render: bool = False,
) -> dict:
    settings = get_settings()
    config = config if config is not None else load_yaml_config(settings.portfolio_config)
    connector = connector or get_connector(settings.portfolio_connector, settings)
    session_factory = session_factory or default_session_factory()
    run_date = run_date or date.today()

    holdings = connector.get_holdings()
    total_value = sum(_holding_value(h) for h in holdings)

    with session_factory() as session:
        # Idempotency: clear any prior rows for this run_date before re-inserting.
        session.query(Holding).filter(Holding.run_date == run_date).delete()
        session.query(Snapshot).filter(
            Snapshot.run_date == run_date, Snapshot.kind == "holdings"
        ).delete()

        session.add(
            Snapshot(
                run_date=run_date,
                kind="holdings",
                source=connector.name,
                payload=holdings,
                fetched_at=datetime.now(timezone.utc),
            )
        )
        for h in holdings:
            value = _holding_value(h)
            session.add(
                Holding(
                    run_date=run_date,
                    symbol=h["tradingsymbol"],
                    exchange=h.get("exchange"),
                    qty=float(h.get("quantity", 0)),
                    avg_price=float(h.get("average_price", 0)),
                    ltp=float(h.get("last_price", 0)),
                    pnl=h.get("pnl"),
                    weight_pct=round(100 * value / total_value, 2) if total_value else None,
                    sector=None,  # enriched later
                )
            )
        session.commit()

    metrics_count = 0
    if market_data is not None:
        metrics_count = _store_metrics(session_factory, run_date, holdings, market_data, config)

    order_flow_count = 0
    if order_flow is not None:
        order_flow_count = _store_order_flow(session_factory, run_date, holdings, order_flow, config)

    fundamentals_data = None
    if fundamentals is not None:
        fundamentals_data = {}
        for h in holdings:
            sym = h["tradingsymbol"]
            try:
                fundamentals_data[sym] = fundamentals.get_fundamentals(sym, exchange=h.get("exchange", "NSE"))
            except Exception:
                fundamentals_data[sym] = {}
        with session_factory() as session:  # freeze for audit
            session.query(Snapshot).filter(
                Snapshot.run_date == run_date, Snapshot.kind == "fundamentals"
            ).delete()
            session.add(
                Snapshot(
                    run_date=run_date,
                    kind="fundamentals",
                    source=fundamentals.name,
                    payload=fundamentals_data,
                    fetched_at=datetime.now(timezone.utc),
                )
            )
            session.commit()

    recommendations = 0
    if theses is not None:
        recommendations = run_scoring(session_factory, run_date, theses, config, fundamentals_data)

    summary = {
        "run_date": str(run_date),
        "connector": connector.name,
        "holdings": len(holdings),
        "total_value": round(total_value, 2),
        "total_pnl": round(sum(float(h.get("pnl") or 0) for h in holdings), 2),
        "metrics": metrics_count,
        "market_data": market_data.name if market_data else None,
        "order_flow": order_flow_count,
        "recommendations": recommendations,
    }
    data = None
    if render or llm is not None:
        with session_factory() as session:
            data = gather_report_data(session, run_date, config)

    narrative = None
    if llm is not None and theses is not None and data is not None:
        narrative = generate_narrative(llm, data, theses, fundamentals_data)
        _store_llm_call(session_factory, run_date, build_user_prompt(data, theses, fundamentals_data), narrative["usage"])
        summary["narrative"] = True
        summary["narrative_violations"] = len(narrative["violations"])
        summary["llm_tokens"] = narrative["usage"].input_tokens + narrative["usage"].output_tokens

    if render and data is not None:
        summary.update(_render_outputs(session_factory, run_date, config, data, narrative))
    return summary


def main() -> None:
    from ..connectors.fundamentals import get_fundamentals
    from ..connectors.market_data import get_market_data
    from ..connectors.order_flow import get_order_flow
    from ..reasoning.llm import get_llm
    from ..reasoning.theses import load_theses

    summary = run(
        market_data=get_market_data(),
        order_flow=get_order_flow(),
        fundamentals=get_fundamentals(),
        theses=load_theses(),  # empty {} if theses.yaml absent -> scoring produces neutral results
        llm=get_llm(get_settings()),  # None if no ANTHROPIC_API_KEY -> narrative skipped
        render=True,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
