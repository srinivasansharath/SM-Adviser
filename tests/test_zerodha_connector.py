import pytest

from app.connectors.zerodha import ZerodhaConnector
from app.safety.guardrails import OrderBlockedError


class FakeKite:
    def holdings(self):
        return [
            {"tradingsymbol": "TCS", "quantity": 20, "average_price": 3450, "last_price": 3890, "pnl": 8800},
        ]

    def positions(self):
        return {"net": [{"tradingsymbol": "NIFTY24FUT", "quantity": 50}], "day": []}

    def place_order(self, **kwargs):
        return "ORDER123"


def test_get_holdings_maps_kite_response():
    conn = ZerodhaConnector(kite_client=FakeKite())
    holdings = conn.get_holdings()
    assert len(holdings) == 1
    assert holdings[0]["tradingsymbol"] == "TCS"


def test_get_positions_returns_net_leg():
    conn = ZerodhaConnector(kite_client=FakeKite())
    positions = conn.get_positions()
    assert positions[0]["tradingsymbol"] == "NIFTY24FUT"


def test_connector_client_blocks_orders():
    # Even reaching into the underlying client, order placement is blocked.
    conn = ZerodhaConnector(kite_client=FakeKite())
    with pytest.raises(OrderBlockedError):
        conn._client().place_order(tradingsymbol="TCS")
