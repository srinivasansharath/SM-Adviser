from datetime import date

from app.connectors.market_data import MockMarketData
from app.connectors.mock import MockConnector
from app.connectors.news import MockNews, NewsConnector
from app.jobs import morning_run
from app.reasoning.llm import MockLLM, estimate_cost
from app.reports.status import build_status
from app.storage.models import LLMCall, Snapshot


class _DeadNews(NewsConnector):
    """A news connector that returns nothing — simulates BSE blacklisting the NUC's IP."""

    name = "dead"

    def get_announcements(self, symbol, days=30, exchange="NSE", isin=None):
        return []


class _FailingLLM(MockLLM):
    """An LLM whose every call raises — simulates an Anthropic API/network timeout."""

    name = "failing"

    def complete(self, system, prompt, max_tokens=1500):
        raise TimeoutError("handshake timed out")


def test_estimate_cost_from_tokens():
    # 1M input + 1M output on Sonnet = 3 + 15 USD.
    assert estimate_cost("claude-sonnet-5", 1_000_000, 1_000_000) == 18.0
    assert estimate_cost("mock", 100, 50) == 0.0


def test_run_records_connector_health(session_factory):
    rd = date(2026, 7, 15)
    summary = morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}},
        market_data=MockMarketData(), news=MockNews(),
    )
    assert summary["degraded"] == []  # everything returned data
    with session_factory() as s:
        snap = s.query(Snapshot).filter_by(run_date=rd, kind="run_health").one()
    assert snap.payload["market_data"]["status"] == "ok"
    assert snap.payload["news"]["status"] == "ok"


def test_dead_news_connector_flags_degraded(session_factory):
    rd = date(2026, 7, 15)
    summary = morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}},
        news=_DeadNews(),
    )
    assert "news" in summary["degraded"]
    status = build_status(session_factory, today=rd)
    assert status["status"] == "degraded"
    assert "news" in status["degraded"]
    assert "blocked" in status["connectors"]["news"]["detail"]


def test_build_status_aggregates_token_cost(session_factory):
    rd = date(2026, 7, 15)
    with session_factory() as s:
        s.add(LLMCall(run_date=rd, model="claude-sonnet-5", tokens=1000, cost=0.5))
        s.add(LLMCall(run_date=rd, model="claude-sonnet-5", tokens=2000, cost=1.0))
        s.commit()

    status = build_status(session_factory, today=rd, budget_usd=10.0)
    assert status["usage"]["this_month"]["calls"] == 2
    assert status["usage"]["this_month"]["tokens"] == 3000
    assert status["usage"]["this_month"]["cost_usd"] == 1.5
    assert status["budget"]["remaining_usd"] == 8.5
    assert status["budget"]["over_budget"] is False


def test_build_status_flags_over_budget(session_factory):
    rd = date(2026, 7, 15)
    with session_factory() as s:
        s.add(LLMCall(run_date=rd, model="claude-sonnet-5", tokens=9_000_000, cost=12.0))
        s.commit()
    status = build_status(session_factory, today=rd, budget_usd=10.0)
    assert status["budget"]["over_budget"] is True


def test_llm_timeout_does_not_sink_the_run(session_factory):
    # A timing-out LLM must degrade gracefully: the run still completes, scores/health persist,
    # and news_risk falls back to the deterministic score (no crash).
    from app.reasoning.news_llm import assess_news
    from app.storage.models import Recommendation, Snapshot

    assert assess_news(_FailingLLM(), {"TCS": [{"material": True, "subcategory": "Dividend"}]})["scores"] == {}

    rd = date(2026, 7, 15)
    summary = morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}},
        market_data=MockMarketData(), news=MockNews(),
        theses={"TCS": {"conviction": "high"}},
        llm=_FailingLLM(),
    )
    assert summary["narrative"] is False
    assert "narrative_error" in summary
    with session_factory() as s:
        assert s.query(Recommendation).filter_by(run_date=rd).count() == 5   # scoring still ran
        assert s.query(Snapshot).filter_by(run_date=rd, kind="run_health").count() == 1


def test_llm_call_stores_estimated_cost(session_factory):
    rd = date(2026, 7, 15)
    morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd,
        config={"analytics": {"lookback_trading_days": 24}},
        market_data=MockMarketData(), news=MockNews(),
        theses={"TCS": {"conviction": "high"}},
        llm=MockLLM('{"executive": "ok", "holdings": {}}'),
    )
    with session_factory() as s:
        calls = s.query(LLMCall).filter_by(run_date=rd).all()
        assert calls and all(c.cost is not None for c in calls)  # cost now populated (was None)
