from datetime import date, datetime

from fastapi.testclient import TestClient

from app.api.main import app, get_expected_token, get_session_factory
from app.api.schemas import CandidatesOut
from app.reports.candidates_page import render_candidates_page
from app.storage.db import bootstrap
from app.storage.models import Candidate, Snapshot

_DETAIL = {
    "symbol": "SOLARINDS", "composite": 86.0, "buckets": ["Compounder", "GARP"], "peg": 1.2,
    "excluded": False, "red_flags": [],
    "subscores": {"quality": 90, "growth": 80, "durability": 88, "valuation": 60,
                  "safety": 95, "liquidity": 70},
    "data": {"roe": 30, "roe_5y": 28, "roce": 40, "sales_cagr_5y": 22, "profit_cagr_5y": 25,
             "pe": 45, "debt_to_equity": 0.2, "promoter_pledge": 0.0, "market_cap": 90000,
             "sector": "Commodities", "industry": "Explosives"},
    "llm": {"verdict": "watch", "conviction": "medium", "thesis": "Durable explosives franchise.",
            "tailwind": "defence capex", "exit_if": ["ROE below 18% for two years"],
            "risks": ["input-cost swings"]},
}


def _seed(tmp_path):
    sf = bootstrap(f"sqlite:///{tmp_path / 'cand.db'}")
    with sf() as s:
        s.add(Candidate(run_date=date(2026, 7, 16), symbol="SOLARINDS", rank=1, composite=86.0,
                        buckets=["Compounder", "GARP"], market_cap=90000, excluded=0,
                        red_flags=[], detail={**_DETAIL, "rank": 1}))
        s.add(Snapshot(run_date=date(2026, 7, 16), kind="screen", source="screener_bulk",
                       payload={"universe": 497, "shortlist": ["SOLARINDS"]},
                       fetched_at=datetime(2026, 7, 16)))
        s.commit()
    return sf


def test_candidates_json(tmp_path):
    sf = _seed(tmp_path)
    app.dependency_overrides[get_session_factory] = lambda: sf
    app.dependency_overrides[get_expected_token] = lambda: "secret"
    try:
        with TestClient(app) as c:
            assert c.get("/candidates.json").status_code == 401     # authed
            r = c.get("/candidates.json", headers={"Authorization": "Bearer secret"})
            assert r.status_code == 200
            body = CandidatesOut.model_validate(r.json())
            assert body.run_date == "2026-07-16" and body.universe == 497
            cand = body.candidates[0]
            assert cand.symbol == "SOLARINDS" and cand.rank == 1
            assert cand.sector == "Commodities" and cand.industry == "Explosives"
            assert cand.verdict == "watch" and "explosives" in cand.thesis
            assert cand.exit_if == ["ROE below 18% for two years"]
            assert cand.metrics["roe"] == 30 and cand.metrics["peg"] == 1.2
    finally:
        app.dependency_overrides.clear()


def test_candidates_html_and_404(tmp_path):
    sf = _seed(tmp_path)
    app.dependency_overrides[get_session_factory] = lambda: sf
    app.dependency_overrides[get_expected_token] = lambda: None
    try:
        with TestClient(app) as c:
            r = c.get("/candidates")
            assert r.status_code == 200 and "text/html" in r.headers["content-type"]
            assert "SOLARINDS" in r.text and "Compounder" in r.text and "WATCH" in r.text
            # grouped by sector, with a per-stock deep-link anchor
            assert 'id="sec-Commodities"' in r.text and 'id="stock-SOLARINDS"' in r.text
    finally:
        app.dependency_overrides.clear()

    empty = bootstrap(f"sqlite:///{tmp_path / 'empty.db'}")
    app.dependency_overrides[get_session_factory] = lambda: empty
    app.dependency_overrides[get_expected_token] = lambda: None
    try:
        with TestClient(app) as c:
            assert c.get("/candidates").status_code == 404       # no run yet
    finally:
        app.dependency_overrides.clear()


def test_render_candidates_page_smoke():
    html = render_candidates_page([{**_DETAIL, "rank": 1}], "2026-07-16", universe=497)
    assert "New-stock ideas" in html and "SOLARINDS" in html
    assert "Exit if" in html and "defence capex" in html
    assert "not investment advice" in html                       # disclaimer present
