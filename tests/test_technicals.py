from app.analytics import technicals as t


def candles(closes, volumes=None):
    volumes = volumes or [100000] * len(closes)
    return [
        {"date": f"2026-06-{i + 1:02d}", "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": v}
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def test_returns_on_known_monotonic_series():
    c = candles(list(range(100, 125)))  # 25 candles, closes 100..124
    assert t.pct_return(c, 1) == round((124 / 123 - 1) * 100, 2)
    assert t.pct_return(c, 5) == round((124 / 119 - 1) * 100, 2)
    assert t.pct_return(c, 20) == round((124 / 104 - 1) * 100, 2)


def test_drawdown_zero_when_monotonic_up():
    assert t.max_drawdown(candles(list(range(100, 120)))) == 0.0


def test_drawdown_captures_dip():
    # peak 110 then down to 99 -> ~ -10%
    c = candles([100, 110, 105, 99, 101])
    assert t.max_drawdown(c) == round((99 / 110 - 1) * 100, 2)


def test_rsi_all_gains_is_100():
    assert t.rsi(candles(list(range(100, 120))), period=14) == 100.0


def test_rsi_midrange_for_mixed_moves():
    closes = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101]
    val = t.rsi(candles(closes), period=14)
    assert val is not None and 40 <= val <= 60


def test_volume_spike_detected():
    vols = [100000] * 20 + [500000]  # 21 days, last is 5x prior avg
    v = t.volume_spike(candles(list(range(100, 121)), vols), n=20)
    assert v == 5.0


def test_relative_strength_vs_index():
    stock = candles(list(range(100, 125)))       # +~19% over 20d
    index = candles(list(range(100, 113)) + list(range(112, 124)))  # weaker
    rs = t.relative_strength(stock, index, n=20)
    assert rs is not None


def test_insufficient_history_returns_none():
    c = candles([100, 101, 102])
    assert t.pct_return(c, 20) is None
    assert t.rsi(c, 14) is None


def test_compute_metrics_keys_match_model_columns():
    m = t.compute_metrics(candles(list(range(100, 125))), candles(list(range(100, 125))))
    assert set(m) == {
        "ret_1d", "ret_5d", "ret_20d", "drawdown", "rsi", "vol_spike", "rel_strength",
        "sma_20", "sma_50", "sma_200",
    }


def test_sma_computed_and_none_when_insufficient():
    from app.analytics import technicals as tt

    c = candles(list(range(100, 160)))  # 60 candles
    assert tt.sma(c, 20) == round(sum(range(140, 160)) / 20, 2)  # mean of last 20 closes
    assert tt.sma(c, 50) is not None
    assert tt.sma(c, 200) is None  # not enough history
