"""The retrospective must measure against the benchmark, not absolute returns — otherwise a bull
market makes any screener look clever."""

import datetime as dt

from app.backtest.screen_review import _pct, report, review


def _ramp(start: float, end: float, n: int = 40) -> list[dict]:
    """A smooth series — no single-day move large enough to look like a split."""
    d0 = dt.date(2026, 7, 1)
    return [{"date": d0 + dt.timedelta(days=i * 2),
             "close": start + (end - start) * i / (n - 1)} for i in range(n)]


class FakeMarketData:
    """Symbol A doubles and B halves, both gradually; the benchmark rises 10%.
    SPLITTER gaps 80% in one day, as an unadjusted corporate action would."""

    def get_daily_candles(self, symbol, days, exchange="NSE"):
        if symbol == "A":
            return _ramp(100.0, 200.0)
        if symbol == "B":
            return _ramp(100.0, 50.0)
        if symbol == "SPLITTER":
            return (_ramp(1000.0, 1200.0, 20)
                    + [{"date": dt.date(2026, 9, 20), "close": 240.0},
                       {"date": dt.date(2026, 9, 26), "close": 250.0}])
        return []

    def get_index_candles(self, index, days):
        return [{"date": dt.date(2026, 7, 1), "close": 1000.0},
                {"date": dt.date(2026, 7, 16), "close": 1000.0},
                {"date": dt.date(2026, 9, 26), "close": 1100.0}]


def _sf(tmp_path, rows):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.storage.models import Base, Candidate

    engine = create_engine(f"sqlite:///{tmp_path}/c.db")
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine)
    with sf() as s:
        for r in rows:
            s.add(Candidate(**r))
        s.commit()
    return sf


def test_excess_return_is_measured_against_the_benchmark(tmp_path):
    sf = _sf(tmp_path, [
        dict(run_date=dt.date(2026, 7, 16), symbol="A", rank=1, composite=90.0,
             detail={"data": {"cmp": 100.0}, "llm": {"verdict": "strong"}}),
        dict(run_date=dt.date(2026, 7, 16), symbol="B", rank=2, composite=60.0,
             detail={"data": {"cmp": 100.0}, "llm": {"verdict": "watch"}}),
    ])
    rev = review(sf, FakeMarketData(), today=dt.date(2026, 9, 26))
    got = {r["symbol"]: r for r in rev["results"]}

    assert got["A"]["ret_pct"] == 100.0
    assert round(got["A"]["bench_pct"], 1) == 10.0
    assert round(got["A"]["excess_pct"], 1) == 90.0      # not 100 — the benchmark is subtracted
    assert round(got["B"]["excess_pct"], 1) == -60.0     # -50 return less +10 benchmark


def test_recommendations_too_recent_are_excluded_not_counted_as_zero(tmp_path):
    """A candidate picked yesterday says nothing; counting it as ~0% would dilute the result."""
    sf = _sf(tmp_path, [
        dict(run_date=dt.date(2026, 9, 25), symbol="A", rank=1, composite=90.0,
             detail={"data": {"cmp": 100.0}}),
    ])
    rev = review(sf, FakeMarketData(), today=dt.date(2026, 9, 26), min_days=14)
    assert rev["results"] == []
    assert rev["skipped_fresh"] == 1


def test_candidate_without_a_recorded_price_is_skipped(tmp_path):
    sf = _sf(tmp_path, [
        dict(run_date=dt.date(2026, 7, 16), symbol="A", rank=1, composite=90.0, detail={}),
    ])
    assert review(sf, FakeMarketData(), today=dt.date(2026, 9, 26))["results"] == []


def test_report_always_states_its_limits(tmp_path):
    sf = _sf(tmp_path, [
        dict(run_date=dt.date(2026, 7, 16), symbol="A", rank=1, composite=90.0,
             detail={"data": {"cmp": 100.0}}),
    ])
    txt = report(review(sf, FakeMarketData(), today=dt.date(2026, 9, 26)))
    assert "noise" in txt and "cannot show that it is good" in txt


def test_unadjusted_split_is_quarantined_not_counted_as_a_loss(tmp_path):
    """ORIANA showed an 80% one-day gap (1205 -> 250, ~1:5) that yfinance had not adjusted for,
    despite auto_adjust=True. Five cohorts each read as ~-77%, which dominated the mean and
    inverted the composite finding. An artifact must never be averaged in silently."""
    from app.backtest.screen_review import suspect_corporate_action

    sf = _sf(tmp_path, [
        dict(run_date=dt.date(2026, 7, 16), symbol="SPLITTER", rank=1, composite=95.0,
             detail={"data": {"cmp": 1000.0}}),
        dict(run_date=dt.date(2026, 7, 16), symbol="A", rank=2, composite=90.0,
             detail={"data": {"cmp": 100.0}}),
    ])
    rev = review(sf, FakeMarketData(), today=dt.date(2026, 9, 26))

    assert [r["symbol"] for r in rev["results"]] == ["A"], "the artifact must not reach the stats"
    assert [r["symbol"] for r in rev["quarantined"]] == ["SPLITTER"]

    flagged, why = suspect_corporate_action(FakeMarketData().get_daily_candles("SPLITTER", 90))
    assert flagged and "1:" in why
    assert not suspect_corporate_action(FakeMarketData().get_daily_candles("A", 90))[0]

    txt = report(rev)
    assert "QUARANTINED" in txt and "SPLITTER" in txt, "the exclusion must be reported, not hidden"


def test_pct_guards_bad_input():
    assert _pct(0, 100) is None
    assert _pct(100, None) is None
    assert _pct(100, 150) == 50.0
