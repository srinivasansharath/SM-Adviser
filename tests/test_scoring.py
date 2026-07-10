from app.domain import Classification
from app.reasoning.scoring import (
    classify,
    composite,
    score_holding,
    score_portfolio_fit,
    score_technical,
    score_thesis,
)

_ALL = [c.value for c in Classification]


def metric(**kw):
    base = {
        k: None
        for k in (
            "ret_1d", "ret_5d", "ret_20d", "drawdown", "rsi", "vol_spike", "rel_strength",
            "sma_20", "sma_50", "sma_200",
        )
    }
    base.update(kw)
    return base


def test_technical_uptrend_scores_high():
    s = score_technical(metric(sma_50=90, sma_200=80, rel_strength=10, rsi=55, drawdown=-5), 100)
    assert s > 60


def test_technical_downtrend_scores_low():
    s = score_technical(metric(sma_50=110, sma_200=120, rel_strength=-10, rsi=40, drawdown=-30), 100)
    assert s < 40


def test_technical_none_without_data():
    assert score_technical(metric(), 100) is None
    assert score_technical(None, 100) is None


def test_portfolio_fit_penalizes_concentration():
    cfg = {"portfolio": {"max_position_weight_pct": 12}}
    assert score_portfolio_fit(20, None, cfg) < score_portfolio_fit(5, None, cfg)


def test_thesis_conviction_baseline():
    assert score_thesis({"conviction": "high"}, 5, metric(), 100, {}) > score_thesis(
        {"conviction": "low"}, 5, metric(), 100, {}
    )


def test_composite_low_coverage_is_low_confidence():
    score, cov, conf = composite(
        {"technical": 80, "portfolio_fit": 70, "thesis": 65, "fundamental": None, "valuation": None, "news_risk": None}
    )
    assert conf == "Low"  # only 3 of 6 sub-scores present
    assert score is not None


def test_composite_pulls_toward_50_when_coverage_low():
    score, cov, conf = composite(
        {"technical": 90, "fundamental": None, "valuation": None, "news_risk": None, "thesis": None, "portfolio_fit": None}
    )
    assert 50 < score < 90  # high raw, but discounted by low coverage


def test_classify_bands():
    assert classify(80, None, {}) == Classification.ACCUMULATE.value
    assert classify(65, None, {}) == Classification.WATCH.value
    assert classify(50, None, {}) == Classification.HOLD.value
    assert classify(35, None, {}) == Classification.TRIM.value
    assert classify(20, None, {}) == Classification.EXIT.value


def test_classify_hysteresis_keeps_prev_near_boundary():
    cfg = {"scoring": {"bands": {"hysteresis_points": 3}}}
    # nominal Watch (>=60) but prev Hold and only 1pt over boundary -> stays Hold
    assert classify(61, Classification.HOLD.value, cfg) == Classification.HOLD.value
    # far enough past the buffer -> upgrades to Watch
    assert classify(64, Classification.HOLD.value, cfg) == Classification.WATCH.value


def test_score_holding_integration_with_fundamentals():
    cfg = {"portfolio": {"max_position_weight_pct": 12}}
    r = score_holding(
        {"symbol": "TCS", "ltp": 100, "weight_pct": 5},
        metric(sma_50=110, sma_200=120, rel_strength=-9, drawdown=-38, rsi=45),
        {"signal": "normal"},
        {"roce": 25, "roe": 22, "pe": 18, "industry_pe": 22, "debt_to_equity": 0.2, "interest_coverage": 8},
        {"conviction": "medium", "target_weight_pct": 6},
        None,
        cfg,
    )
    assert r["classification"] in _ALL
    assert r["subscores"]["fundamental"] is not None  # now populated from fundamentals
    assert r["subscores"]["valuation"] is not None
    assert r["confidence"] in ("Low", "Medium", "Medium-High", "High")


def test_hard_override_forces_exit():
    cfg = {"portfolio": {"max_position_weight_pct": 12}, "scoring": {"hard_overrides": {"interest_coverage_below": 1.5}}}
    r = score_holding(
        {"symbol": "XYZ", "ltp": 100, "weight_pct": 5},
        metric(sma_50=90, sma_200=80, rel_strength=5, rsi=55),  # healthy technicals
        {},
        {"roce": 18, "roe": 16, "interest_coverage": 0.9},  # but insolvent
        {"conviction": "high"},
        None,
        cfg,
    )
    from app.domain import Classification

    assert r["classification"] == Classification.EXIT.value
    assert any("OVERRIDE" in x for x in r["reasons"])
