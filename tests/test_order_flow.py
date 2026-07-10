from app.analytics.order_flow import compute_delivery_signal
from app.connectors.order_flow import MockOrderFlow, NSEOrderFlow, get_order_flow


def _series(pcts):
    return [
        {"date": f"2026-06-{i + 1:02d}", "traded_qty": 100000, "delivery_qty": 50000, "delivery_pct": p}
        for i, p in enumerate(pcts)
    ]


def test_high_delivery_signal():
    # last day well above the trailing average -> conviction "high"
    row = compute_delivery_signal(_series([40, 40, 40, 40, 80]))
    assert row["delivery_pct"] == 80
    assert row["avg_delivery_pct"] == 40
    assert row["signal"] == "high"


def test_low_delivery_signal():
    row = compute_delivery_signal(_series([60, 60, 60, 60, 20]))
    assert row["signal"] == "low"


def test_normal_delivery_signal():
    row = compute_delivery_signal(_series([50, 50, 50, 50, 52]))
    assert row["signal"] == "normal"


def test_empty_series_is_null():
    row = compute_delivery_signal([])
    assert row["delivery_pct"] is None
    assert row["signal"] is None


def test_mock_connector_series_shape():
    s = MockOrderFlow().get_delivery_series("TCS", 24)
    assert len(s) == 24
    assert {"date", "traded_qty", "delivery_qty", "delivery_pct"}.issubset(s[0].keys())


def test_mock_market_flows():
    flows = MockOrderFlow().get_market_flows()
    assert "fii_net" in flows and "dii_net" in flows


def test_factory():
    assert get_order_flow("mock").name == "mock"
    assert isinstance(get_order_flow("nse"), NSEOrderFlow)
