from app.reports.signals import evaluate_flags

CFG = {"portfolio": {"max_position_weight_pct": 12}}


def m(**kw):
    base = {"sma_50": None, "sma_200": None, "rel_strength": None, "drawdown": None, "rsi": None}
    base.update(kw)
    return base


def test_clean_holding_is_ok():
    r = evaluate_flags(
        {"weight_pct": 5, "ltp": 100},
        m(sma_50=90, sma_200=80, rel_strength=2, drawdown=-5, rsi=55),
        {"signal": "normal"},
        CFG,
    )
    assert r["flag"] == "ok"
    assert r["reasons"] == []


def test_overweight_is_watch():
    r = evaluate_flags({"weight_pct": 13, "ltp": 100}, m(sma_50=90, sma_200=80), {}, CFG)
    assert r["flag"] == "watch"


def test_concentration_is_risk():
    r = evaluate_flags({"weight_pct": 20, "ltp": 100}, m(sma_50=90, sma_200=80), {}, CFG)
    assert r["flag"] == "risk"


def test_below_200dma_and_lagging_is_risk():
    r = evaluate_flags(
        {"weight_pct": 5, "ltp": 100}, m(sma_50=110, sma_200=120, rel_strength=-9), {}, CFG
    )
    assert r["flag"] == "risk"
    assert any("200-DMA" in x for x in r["reasons"])


def test_below_50dma_only_is_watch():
    r = evaluate_flags(
        {"weight_pct": 5, "ltp": 100}, m(sma_50=110, sma_200=90, rel_strength=1), {}, CFG
    )
    assert r["flag"] == "watch"


def test_low_delivery_adds_watch():
    r = evaluate_flags(
        {"weight_pct": 5, "ltp": 100}, m(sma_50=90, sma_200=80, rel_strength=2), {"signal": "low"}, CFG
    )
    assert r["flag"] == "watch"
