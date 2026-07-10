from app.backtest.engine import evaluate_point, forward_return_pct, run_backtest, scorecard
from app.connectors.market_data import MockMarketData


def _candles(closes):
    return [
        {"date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100000}
        for i, c in enumerate(closes)
    ]


def test_forward_return():
    c = _candles([100, 110, 121])
    assert forward_return_pct(c, 0, 2) == 21.0
    assert forward_return_pct(c, 0, 5) is None  # out of range


def test_evaluate_point_uptrend_positive_forward():
    closes = [100 + i for i in range(260)]  # steadily rising
    c = _candles(closes)
    flat_index = {cd["date"]: 1000.0 for cd in c}
    r = evaluate_point(c, flat_index, 230, [21], {})
    assert r["tech_score"] is not None and r["tech_score"] > 55  # uptrend scores bullish
    assert r["fwd"][21] > 0  # price kept rising
    assert r["excess"][21] is not None  # vs flat index


def test_evaluate_point_downtrend_negative_forward():
    closes = [400 - i for i in range(260)]  # steadily falling
    c = _candles(closes)
    flat_index = {cd["date"]: 1000.0 for cd in c}
    r = evaluate_point(c, flat_index, 230, [21], {})
    assert r["tech_score"] is not None and r["tech_score"] < 45  # downtrend scores bearish
    assert r["fwd"][21] < 0


def test_scorecard_aggregates():
    results = [
        {"tech_score": 80, "flag": "ok", "excess": {21: 5.0}},
        {"tech_score": 75, "flag": "ok", "excess": {21: 3.0}},
        {"tech_score": 20, "flag": "risk", "excess": {21: -4.0}},
        {"tech_score": 25, "flag": "risk", "excess": {21: -2.0}},
    ]
    card = scorecard(results, [21])
    h = card["horizons"][21]
    assert h["avg_excess_ok_calls"] == 4.0
    assert h["avg_excess_risk_calls"] == -3.0
    assert h["ok_outperformed_rate"] == 1.0
    assert h["risk_underperformed_rate"] == 1.0


def test_run_backtest_with_mock_market_data():
    # MockMarketData returns a rising series; just assert the harness produces observations.
    results = run_backtest(["AAA", "BBB"], MockMarketData(), as_of_offsets=[30], horizons=[21], history=300)
    assert isinstance(results, list)
    assert all("tech_score" in r for r in results)
