from app.analytics.fundamentals import hard_override, score_fundamental, score_valuation
from app.connectors.fundamentals import MockFundamentals, ScreenerFundamentals, get_fundamentals


def test_quality_scores_higher_than_junk():
    good = score_fundamental({"roce": 25, "roe": 22, "debt_to_equity": 0.2, "interest_coverage": 9, "rev_growth_3y": 18})
    poor = score_fundamental({"roce": 6, "roe": 5, "debt_to_equity": 2.0, "interest_coverage": 1.2, "rev_growth_3y": -3})
    assert good > 60 > poor


def test_fundamental_none_without_fields():
    assert score_fundamental({}) is None
    assert score_fundamental({"pe": 20}) is None  # pe is valuation, not a quality field


def test_valuation_cheap_vs_expensive():
    cheap = score_valuation({"pe": 15, "industry_pe": 25})
    rich = score_valuation({"pe": 40, "industry_pe": 25})
    assert cheap > rich


def test_valuation_none_without_pe_or_pb():
    assert score_valuation({"roce": 20}) is None


def test_hard_override_triggers():
    cfg = {"scoring": {"hard_overrides": {"interest_coverage_below": 1.5, "promoter_pledge_pct_above": 50}}}
    assert hard_override({"interest_coverage": 1.0}, cfg) is not None
    assert hard_override({"promoter_pledge": 65}, cfg) is not None
    assert hard_override({"interest_coverage": 8, "promoter_pledge": 5}, cfg) is None


def test_mock_connector_returns_fields():
    f = MockFundamentals().get_fundamentals("TCS")
    assert {"pe", "roce", "roe", "debt_to_equity", "interest_coverage"}.issubset(f.keys())


def test_factory():
    assert get_fundamentals("mock").name == "mock"
    assert isinstance(get_fundamentals("screener"), ScreenerFundamentals)
