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


def test_effective_qty_counts_unsettled_t1_shares():
    """A stock bought inside the T+1 window arrives as quantity=0 / t1_quantity=N. Counting only
    `quantity` valued it at zero, which understated the portfolio total by the whole purchase
    (JAINREC: 174 shares, ~20% of the portfolio, reported as 0%)."""
    from app.connectors.base import effective_qty

    # freshly bought, unsettled — the regression case
    assert effective_qty({"tradingsymbol": "JAINREC", "quantity": 0, "t1_quantity": 174}) == 174
    # normal settled holding
    assert effective_qty({"tradingsymbol": "TCS", "quantity": 5, "t1_quantity": 0}) == 5
    # partially settled (added to an existing position)
    assert effective_qty({"quantity": 100, "t1_quantity": 50}) == 150
    # a genuinely exited position stays zero — the deliberate mirror-Kite behaviour
    assert effective_qty({"quantity": 0, "t1_quantity": 0}) == 0
    # tolerate missing / None fields, as elsewhere in the pipeline
    assert effective_qty({}) == 0
    assert effective_qty({"quantity": None, "t1_quantity": None}) == 0
    assert effective_qty({"quantity": 7}) == 7


def test_holding_value_includes_unsettled_shares():
    """Portfolio value and therefore every weight must include T+1 shares."""
    from app.jobs.morning_run import _holding_value

    unsettled = {"tradingsymbol": "JAINREC", "quantity": 0, "t1_quantity": 174,
                 "last_price": 286.85}
    assert _holding_value(unsettled) == 174 * 286.85          # was 0.0 before the fix
    settled = {"tradingsymbol": "TCS", "quantity": 5, "t1_quantity": 0, "last_price": 2083.95}
    assert _holding_value(settled) == 5 * 2083.95
    assert _holding_value({"quantity": 0, "t1_quantity": 0, "last_price": 100.0}) == 0.0
