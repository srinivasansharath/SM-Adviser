from app.connectors import get_connector
from app.connectors.mock import MockConnector


def test_mock_holdings_shape():
    holdings = MockConnector().get_holdings()
    assert len(holdings) >= 1
    required = {"tradingsymbol", "exchange", "quantity", "average_price", "last_price"}
    for h in holdings:
        assert required.issubset(h.keys())


def test_pnl_sign_matches_price_move():
    # Kite-shaped mock: pnl should agree with (last - avg) * qty in direction.
    for h in MockConnector().get_holdings():
        expected = (h["last_price"] - h["average_price"]) * h["quantity"]
        assert (h["pnl"] > 0) == (expected > 0)


def test_factory_returns_mock():
    assert get_connector("mock").name == "mock"
