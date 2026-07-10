import pytest

from app.connectors.market_data import (
    MockMarketData,
    YFinanceMarketData,
    get_market_data,
)


def test_mock_returns_requested_number_of_candles():
    candles = MockMarketData().get_daily_candles("TCS", 24)
    assert len(candles) == 24
    required = {"date", "open", "high", "low", "close", "volume"}
    assert required.issubset(candles[0].keys())


def test_mock_is_deterministic_per_symbol():
    a = MockMarketData().get_daily_candles("INFY", 24)
    b = MockMarketData().get_daily_candles("INFY", 24)
    assert a == b  # same seed -> same series (hermetic tests)


def test_factory_selects_provider():
    assert get_market_data("mock").name == "mock"
    assert isinstance(get_market_data("yfinance"), YFinanceMarketData)
    with pytest.raises(ValueError):
        get_market_data("bloomberg")
