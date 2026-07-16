from datetime import date

from app.analytics.screening import median_daily_value_cr
from app.connectors.fundamentals import MockFundamentals
from app.connectors.fundamentals_universe import MockUniverse, UniverseConnector
from app.connectors.market_data import MockMarketData
from app.jobs import weekly_screen
from app.storage.models import Candidate, Snapshot


def test_median_daily_value_cr():
    candles = [{"close": 100, "volume": 100000}, {"close": 200, "volume": 100000},
               {"close": 300, "volume": 100000}]
    # median(close*vol) = median(1e7, 2e7, 3e7) = 2e7 -> 2.0 cr
    assert median_daily_value_cr(candles) == 2.0
    assert median_daily_value_cr([]) is None
    assert median_daily_value_cr([{"close": None, "volume": 5}]) is None


# --- deterministic mini-connectors so gating is exact ---------------------------------------
class _Uni(UniverseConnector):
    name = "test"

    def get_universe(self):
        return [
            {"symbol": "GOOD", "roce": 40, "market_cap": 5000, "profit_growth_qtr": 30,
             "sales_growth_qtr": 20, "pe": 20},
            {"symbol": "PLEDGED", "roce": 35, "market_cap": 3000, "profit_growth_qtr": 25,
             "sales_growth_qtr": 15, "pe": 18},
        ]


class _Fund(MockFundamentals):
    name = "testf"

    def get_fundamentals(self, symbol, exchange="NSE"):
        base = {"roe": 22, "roe_5y": 20, "sales_cagr_5y": 16, "profit_cagr_5y": 18,
                "debt_to_equity": 0.3, "promoter_holding": 60}
        base["promoter_pledge"] = 70.0 if symbol == "PLEDGED" else 0.0
        return base


def test_weekly_run_gates_and_ranks(session_factory):
    rd = date(2026, 7, 16)
    summary = weekly_screen.run(
        universe=_Uni(), fundamentals=_Fund(), market_data=MockMarketData(),
        session_factory=session_factory, run_date=rd, config={}, top_deep=10, shortlist=10,
    )
    assert summary["universe"] == 2
    assert summary["deep_fetched"] == 2
    assert summary["excluded"] == 1                 # PLEDGED (70% pledge) hard-gated
    assert summary["shortlist"] == 1

    with session_factory() as s:
        cands = s.query(Candidate).filter_by(run_date=rd).all()
        assert [c.symbol for c in cands] == ["GOOD"]   # only the clean name persisted
        assert cands[0].rank == 1 and cands[0].composite is not None
        assert "Compounder" in (cands[0].buckets or [])
        snap = s.query(Snapshot).filter_by(run_date=rd, kind="screen").one()
        assert snap.payload["shortlist"] == ["GOOD"] and snap.payload["excluded"] == 1


def test_weekly_run_with_mock_universe(session_factory):
    rd = date(2026, 7, 16)
    summary = weekly_screen.run(
        universe=MockUniverse(), fundamentals=MockFundamentals(), market_data=MockMarketData(),
        session_factory=session_factory, run_date=rd, config={}, top_deep=8, shortlist=5,
    )
    assert summary["universe"] == 8
    with session_factory() as s:
        cands = s.query(Candidate).filter_by(run_date=rd).order_by(Candidate.rank).all()
        assert len(cands) == summary["shortlist"] <= 5
        comps = [c.composite for c in cands]
        assert comps == sorted(comps, reverse=True)     # ranked by composite desc
        assert all(c.excluded == 0 for c in cands)


def test_weekly_run_idempotent(session_factory):
    rd = date(2026, 7, 16)
    for _ in range(2):
        weekly_screen.run(universe=_Uni(), fundamentals=_Fund(), market_data=MockMarketData(),
                          session_factory=session_factory, run_date=rd, config={})
    with session_factory() as s:
        assert s.query(Candidate).filter_by(run_date=rd).count() == 1        # replaced, not duped
        assert s.query(Snapshot).filter_by(run_date=rd, kind="screen").count() == 1
