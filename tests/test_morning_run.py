from datetime import date

from app.connectors.market_data import MockMarketData
from app.connectors.mock import MockConnector
from app.connectors.order_flow import MockOrderFlow
from app.jobs import morning_run
from app.storage.models import Holding, MarketFlow, Metric, OrderFlow, Snapshot


def test_morning_run_persists_snapshot_and_holdings(session_factory):
    rd = date(2026, 7, 10)
    summary = morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd, config={}
    )

    assert summary["connector"] == "mock"
    assert summary["holdings"] == 5

    with session_factory() as s:
        assert s.query(Snapshot).filter_by(run_date=rd, kind="holdings").count() == 1
        holdings = s.query(Holding).filter_by(run_date=rd).all()
        assert len(holdings) == 5
        # Weights are shares of total value and should sum to ~100%.
        assert abs(sum(h.weight_pct for h in holdings) - 100.0) < 0.5


def test_morning_run_computes_and_stores_metrics(session_factory):
    rd = date(2026, 7, 10)
    summary = morning_run.run(
        connector=MockConnector(),
        session_factory=session_factory,
        run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}},
        market_data=MockMarketData(),
    )
    assert summary["metrics"] == 5
    assert summary["market_data"] == "mock"

    with session_factory() as s:
        metrics = s.query(Metric).filter_by(run_date=rd).all()
        assert len(metrics) == 5
        # The mock series rises over 24 days, so the 20-day return is populated and positive.
        assert all(m.ret_20d is not None and m.ret_20d > 0 for m in metrics)


def test_metrics_skipped_when_no_market_data(session_factory):
    rd = date(2026, 7, 10)
    summary = morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd, config={}
    )
    assert summary["metrics"] == 0
    with session_factory() as s:
        assert s.query(Metric).filter_by(run_date=rd).count() == 0


def test_morning_run_stores_order_flow(session_factory):
    rd = date(2026, 7, 10)
    summary = morning_run.run(
        connector=MockConnector(),
        session_factory=session_factory,
        run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}},
        order_flow=MockOrderFlow(),
    )
    assert summary["order_flow"] == 5

    with session_factory() as s:
        flows = s.query(OrderFlow).filter_by(run_date=rd).all()
        assert len(flows) == 5
        assert all(f.delivery_pct is not None and f.signal in {"high", "low", "normal"} for f in flows)
        # Mock ends on a delivery surge, so at least one holding reads "high".
        assert any(f.signal == "high" for f in flows)
        # Market-wide FII/DII row stored once.
        assert s.query(MarketFlow).filter_by(run_date=rd).count() == 1


def test_morning_run_renders_report_and_widget(session_factory, tmp_path):
    import json
    from pathlib import Path

    from app.storage.models import Report

    rd = date(2026, 7, 10)
    summary = morning_run.run(
        connector=MockConnector(),
        session_factory=session_factory,
        run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}, "report": {"output_dir": str(tmp_path)}},
        market_data=MockMarketData(),
        order_flow=MockOrderFlow(),
        render=True,
    )
    assert Path(summary["report"]).exists()
    assert Path(summary["widget"]).exists()

    widget = json.loads(Path(summary["widget"]).read_text())
    assert widget["portfolio"]["value"] > 0
    assert len(widget["holdings"]) == 5

    with session_factory() as s:
        assert s.query(Report).filter_by(run_date=rd).count() == 3  # markdown, html, widget


def test_morning_run_scores_with_theses(session_factory):
    from app.domain import Classification
    from app.storage.models import Recommendation, Score

    rd = date(2026, 7, 10)
    theses = {
        "TCS": {"conviction": "high", "target_weight_pct": 10},
        "INFY": {"conviction": "medium", "target_weight_pct": 6},
    }
    summary = morning_run.run(
        connector=MockConnector(),
        session_factory=session_factory,
        run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}, "portfolio": {"max_position_weight_pct": 12}},
        market_data=MockMarketData(),
        theses=theses,
    )
    assert summary["recommendations"] == 5

    with session_factory() as s:
        recs = s.query(Recommendation).filter_by(run_date=rd).all()
        assert len(recs) == 5
        assert all(r.classification in [c.value for c in Classification] for r in recs)
        assert s.query(Score).filter_by(run_date=rd).count() == 5


def test_morning_run_with_llm_narrative(session_factory, tmp_path):
    import json
    from pathlib import Path

    from app.reasoning.llm import MockLLM
    from app.storage.models import LLMCall

    rd = date(2026, 7, 10)
    canned = '{"executive": "Two names on watch.", "holdings": {"TCS": {"thesis_status": "watch", "note": "Monitor."}}}'
    summary = morning_run.run(
        connector=MockConnector(),
        session_factory=session_factory,
        run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}, "report": {"output_dir": str(tmp_path)}},
        market_data=MockMarketData(),
        theses={"TCS": {"conviction": "high"}},
        llm=MockLLM(canned),
        render=True,
    )
    assert summary.get("narrative") is True
    assert summary["llm_tokens"] > 0

    widget = json.loads(Path(summary["widget"]).read_text())
    assert widget["headline"] == "Two names on watch."
    assert "Analyst narrative" in Path(summary["report"]).read_text()

    with session_factory() as s:
        assert s.query(LLMCall).filter_by(run_date=rd).count() == 1  # audit row


def test_morning_run_is_idempotent(session_factory):
    rd = date(2026, 7, 10)
    for _ in range(2):
        morning_run.run(
            connector=MockConnector(), session_factory=session_factory, run_date=rd, config={}
        )

    with session_factory() as s:
        # Re-running the same day replaces rows, never duplicates them.
        assert s.query(Snapshot).filter_by(run_date=rd, kind="holdings").count() == 1
        assert s.query(Holding).filter_by(run_date=rd).count() == 5
