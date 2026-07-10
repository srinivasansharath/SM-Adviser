from datetime import date, datetime, timezone

from app.reports.daily_report import build_html, build_markdown
from app.reports.gather import gather_report_data
from app.reports.widget_json import build_widget
from app.storage.models import Holding, MarketFlow, Metric, OrderFlow, Snapshot

CFG = {"portfolio": {"max_position_weight_pct": 12}}


def _seed(session, rd):
    session.add(
        Snapshot(
            run_date=rd,
            kind="holdings",
            source="mock",
            payload=[
                {"tradingsymbol": "TCS", "day_change_percentage": -1.2},
                {"tradingsymbol": "YESBANK", "day_change_percentage": 0.5},
            ],
            fetched_at=datetime.now(timezone.utc),
        )
    )
    session.add(Holding(run_date=rd, symbol="TCS", exchange="NSE", qty=5, avg_price=2300, ltp=2070, pnl=-1150, weight_pct=20))
    session.add(Holding(run_date=rd, symbol="YESBANK", exchange="NSE", qty=3800, avg_price=18, ltp=24, pnl=22800, weight_pct=31))
    session.add(Metric(run_date=rd, symbol="TCS", ret_1d=-1.1, ret_20d=-4.3, rsi=44, drawdown=-10, rel_strength=-8.7, sma_50=2200, sma_200=2680))
    session.add(Metric(run_date=rd, symbol="YESBANK", ret_1d=1.2, ret_20d=4.0, rsi=38, drawdown=-8, rel_strength=-0.4, sma_50=23, sma_200=21))
    session.add(OrderFlow(run_date=rd, symbol="TCS", delivery_pct=45, avg_delivery_pct=50, signal="normal"))
    session.add(MarketFlow(run_date=rd, fii_net=-1200, dii_net=1500))
    session.commit()


def test_gather_flags_and_render(session_factory):
    rd = date(2026, 7, 10)
    with session_factory() as s:
        _seed(s, rd)
    with session_factory() as s:
        data = gather_report_data(s, rd, CFG)

    assert data["portfolio"]["holdings_count"] == 2
    flags = {r["symbol"]: r["flag"] for r in data["holdings"]}
    assert flags["YESBANK"] == "risk"   # 31% concentration
    assert flags["TCS"] == "risk"       # below 200-DMA and lagging NIFTY
    assert data["portfolio"]["attention_count"] == 2
    # Sorted by weight: YESBANK (31%) first.
    assert data["holdings"][0]["symbol"] == "YESBANK"

    md = build_markdown(data)
    assert "Daily Portfolio Report" in md
    assert "not investment advice" in md
    assert "TCS" in md and "Action queue" in md

    assert "<table" in build_html(data)

    widget = build_widget(data)
    assert widget["portfolio"]["attention_count"] == 2
    assert len(widget["holdings"]) == 2
    assert widget["holdings"][0]["flag"] == "risk"
    assert widget["disclaimer"]
