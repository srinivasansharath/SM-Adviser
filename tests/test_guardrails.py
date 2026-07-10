import pytest

from app.safety.guardrails import OrderBlockedError, ReadOnlyKite


class FakeKite:
    def holdings(self):
        return [{"tradingsymbol": "TCS"}]

    def place_order(self, **kwargs):  # should never be reachable through ReadOnlyKite
        return "ORDER123"

    def set_access_token(self, token):
        return token


def test_read_methods_pass_through():
    ro = ReadOnlyKite(FakeKite())
    assert ro.holdings()[0]["tradingsymbol"] == "TCS"


@pytest.mark.parametrize("method", ["place_order", "modify_order", "cancel_order", "place_gtt", "set_access_token"])
def test_order_methods_are_blocked(method):
    ro = ReadOnlyKite(FakeKite())
    with pytest.raises(OrderBlockedError):
        getattr(ro, method)


def test_cannot_mutate_wrapper():
    ro = ReadOnlyKite(FakeKite())
    with pytest.raises(OrderBlockedError):
        ro._kite = "tampered"
