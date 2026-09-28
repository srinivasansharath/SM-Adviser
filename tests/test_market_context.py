"""Market context — "is everything red, or just my stocks?"."""

from datetime import date, datetime, timezone

from app.analytics.market import (
    benchmark_names,
    build_market,
    day_change_from_quote,
    index_from_candles,
    indices_from_quotes,
    kite_instrument,
    with_vs_market,
)
from app.api.schemas import WidgetPayload
from app.connectors.market_data import MockMarketData
from app.connectors.mock import MockConnector
from app.jobs import intraday_refresh, morning_run
from app.reports.daily_report import build_html, build_markdown
from app.reports.gather import gather_report_data
from app.reports.widget_json import build_widget
from app.storage.models import Holding, Snapshot

CFG = {"portfolio": {"benchmarks": {"broad": ["NIFTY 50", "NIFTY 500"]}}}

# Shape of a Kite index quote: net_change is commonly 0 for indices, so it must not be trusted.
NIFTY_QUOTE = {
    "last_price": 24890.10,
    "net_change": 0,
    "ohlc": {"open": 25010.0, "high": 25022.45, "low": 24851.3, "close": 25045.35},
}


def test_day_change_comes_from_prev_close_not_net_change():
    assert day_change_from_quote(NIFTY_QUOTE) == -0.62


def test_day_change_is_none_without_a_previous_close():
    assert day_change_from_quote({"last_price": 100.0, "ohlc": {}}) is None
    assert day_change_from_quote({}) is None


def test_kite_instrument_maps_the_abbreviated_index_names():
    assert kite_instrument("NIFTY 50") == "NSE:NIFTY 50"
    assert kite_instrument("NIFTY SMALLCAP 250") == "NSE:NIFTY SMLCAP 250"
    assert kite_instrument("nifty 500") == "NSE:NIFTY 500"  # config casing is normalised


def test_benchmark_names_defaults_to_nifty_50():
    assert benchmark_names({}) == ["NIFTY 50"]
    assert benchmark_names(CFG) == ["NIFTY 50", "NIFTY 500"]


def test_indices_from_quotes_skips_indices_the_feed_did_not_return():
    indices = indices_from_quotes(["NIFTY 50", "NIFTY 500"], {"NSE:NIFTY 50": NIFTY_QUOTE})
    assert [i["name"] for i in indices] == ["NIFTY 50"]
    assert indices[0]["ltp"] == 24890.1


def test_index_from_candles_uses_the_last_two_closes():
    candles = [{"close": 100.0}, {"close": 98.0}]
    assert index_from_candles("NIFTY 50", candles) == {
        "name": "NIFTY 50", "ltp": 98.0, "day_change_pct": -2.0,
    }
    assert index_from_candles("NIFTY 50", [{"close": 100.0}]) is None  # one session isn't a change
    assert index_from_candles("NIFTY 50", None) is None


def test_vs_market_is_the_portfolio_minus_the_primary_index():
    market = build_market(
        [{"name": "NIFTY 50", "ltp": 100.0, "day_change_pct": -1.9},
         {"name": "NIFTY 500", "ltp": 90.0, "day_change_pct": -2.1}],
        source="zerodha",
        portfolio_day_change_pct=-1.4,
    )
    assert market["benchmark"] == "NIFTY 50"        # primary = first configured
    assert market["vs_market_pct"] == 0.5           # down less than the market = outperforming
    assert market["source"] == "zerodha"


def test_vs_market_is_none_when_either_side_is_missing():
    market = build_market([{"name": "NIFTY 50", "day_change_pct": -1.9}], "yfinance", None)
    assert market["vs_market_pct"] is None
    assert with_vs_market(None, -1.4) is None       # no market block stays no market block


def test_build_market_is_none_without_any_index():
    assert build_market([], "yfinance", -1.4) is None


def test_mock_connector_serves_index_quotes():
    quotes = MockConnector().get_quotes(["NSE:NIFTY 50", "NSE:NOPE"])
    assert set(quotes) == {"NSE:NIFTY 50"}
    assert day_change_from_quote(quotes["NSE:NIFTY 50"]) is not None


def test_morning_run_freezes_market_context(session_factory):
    rd = date(2026, 7, 10)
    morning_run.run(
        connector=MockConnector(), session_factory=session_factory, run_date=rd,
        config=CFG, market_data=MockMarketData(),
    )
    with session_factory() as s:
        snap = s.query(Snapshot).filter_by(run_date=rd, kind="market").first()
        assert snap is not None and snap.source == "mock"
        assert [i["name"] for i in snap.payload["indices"]] == ["NIFTY 50", "NIFTY 500"]
        assert snap.payload["benchmark"] == "NIFTY 50"


def test_market_context_flows_through_gather_and_widget(session_factory):
    rd = date(2026, 7, 10)
    with session_factory() as s:
        s.add(Snapshot(run_date=rd, kind="holdings", source="mock", fetched_at=datetime.now(timezone.utc),
                       payload=[{"tradingsymbol": "TCS", "day_change_percentage": -1.4}]))
        s.add(Snapshot(run_date=rd, kind="market", source="yfinance", fetched_at=datetime.now(timezone.utc),
                       payload={"benchmark": "NIFTY 50", "source": "yfinance",
                                "indices": [{"name": "NIFTY 50", "ltp": 24890.1, "day_change_pct": -1.9}]}))
        s.add(Holding(run_date=rd, symbol="TCS", exchange="NSE", qty=5, avg_price=2300, ltp=2070,
                      pnl=-1150, weight_pct=100))
        s.commit()

    with session_factory() as s:
        data = gather_report_data(s, rd, CFG)

    assert data["portfolio"]["day_change_pct"] == -1.4
    assert data["market"]["vs_market_pct"] == 0.5   # computed against the run's own day change

    payload = build_widget(data)
    WidgetPayload.model_validate(payload)           # the new block is contract-valid
    assert payload["market"]["indices"][0]["day_change_pct"] == -1.9
    assert payload["market"]["vs_market_pct"] == 0.5


def test_widget_omits_market_when_no_market_data_ran(session_factory):
    rd = date(2026, 7, 10)
    with session_factory() as s:
        s.add(Holding(run_date=rd, symbol="TCS", exchange="NSE", qty=5, avg_price=2300, ltp=2070,
                      pnl=-1150, weight_pct=100))
        s.commit()
    with session_factory() as s:
        payload = build_widget(gather_report_data(s, rd, CFG))
    assert payload["market"] is None
    WidgetPayload.model_validate(payload)           # still contract-valid: the block is optional


class _QuotingConnector:
    """Connector that quotes indices, the way ZerodhaConnector does."""

    name = "zerodha"

    def get_quotes(self, instruments):
        return {"NSE:NIFTY 50": NIFTY_QUOTE}


class _BrokenConnector:
    name = "zerodha"

    def get_quotes(self, instruments):
        raise RuntimeError("kite unreachable")


def test_intraday_refresh_requotes_indices_live():
    doc = {}
    intraday_refresh._refresh_market(doc, _QuotingConnector(), CFG)
    assert doc["market"]["indices"][0]["day_change_pct"] == -0.62
    assert doc["market"]["source"] == "zerodha"     # live quote, not the morning run's close


def test_intraday_refresh_keeps_morning_context_when_quotes_fail():
    stale = {"benchmark": "NIFTY 50", "source": "yfinance",
             "indices": [{"name": "NIFTY 50", "ltp": 25045.35, "day_change_pct": -0.3}]}
    doc = {"market": stale}
    intraday_refresh._refresh_market(doc, _BrokenConnector(), CFG)
    assert doc["market"] is stale                   # stale context beats a blanked field


_REPORT_DATA = {
    "run_date": "2026-09-25",
    "portfolio": {"value": 300000.0, "total_pnl": 10000.0, "day_change_pct": -1.4,
                  "attention_count": 1, "holdings_count": 5, "top5_pct": 60.0,
                  "fii_net": None, "dii_net": None},
    "market": {"benchmark": "NIFTY 50", "vs_market_pct": 0.5,
               "indices": [{"name": "NIFTY 50", "day_change_pct": -1.9},
                           {"name": "NIFTY 500", "day_change_pct": -2.1}]},
    "holdings": [],
}


def test_daily_report_states_the_market_baseline():
    line = "NIFTY 50 -1.90%, NIFTY 500 -2.10% \u00b7 portfolio +0.50% vs NIFTY 50"
    assert f"- Market: {line}" in build_markdown(_REPORT_DATA)
    assert f"<li>Market: {line}</li>" in build_html(_REPORT_DATA)


def test_daily_report_drops_the_market_line_without_market_data():
    data = {**_REPORT_DATA, "market": None}
    assert "Market:" not in build_markdown(data)
    assert "Market:" not in build_html(data)


def test_narrative_prompt_carries_the_market_block():
    from app.reasoning.prompts import build_user_prompt

    data = {**_REPORT_DATA, "holdings": [{"symbol": "TCS", "day_change_pct": -1.8}]}
    prompt = build_user_prompt(data, theses={}, fundamentals_data=None)
    assert '"vs_market_pct": 0.5' in prompt        # the LLM can see it was a market-wide day
    assert '"day_change_pct": -1.8' in prompt      # ...and how this holding moved against it
