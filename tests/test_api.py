import json

from fastapi.testclient import TestClient

from app.api.main import app, get_expected_token, get_output_dir, get_session_factory
from app.api.schemas import Meta, WidgetPayload
from app.api.version import API_VERSION
from app.reasoning.theses import load_theses_from_db, seed_theses_from_yaml
from app.reports.widget_json import build_widget
from app.storage.db import bootstrap


def test_health():
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_meta_contract():
    # /meta is the capability/version endpoint the app negotiates against.
    with TestClient(app) as c:
        r = c.get("/meta")
        assert r.status_code == 200
        m = Meta.model_validate(r.json())
        assert m.api_version == API_VERSION
        assert "widget" in m.features


def test_widget_payload_matches_contract():
    # The served widget payload must satisfy the published contract shape + carry api_version.
    data = {
        "run_date": "2026-07-14",
        "portfolio": {"value": 100.0, "day_change_pct": 1.0, "total_pnl": 10.0,
                      "total_return_pct": 11.0, "attention_count": 1},
        "holdings": [{"symbol": "X", "name": "X", "ltp": 10.0, "day_change_pct": 1.0,
                      "ret_20d": 2.0, "ret_252d": 3.0, "return_pct": 4.0, "pnl": 5.0,
                      "rel_strength": 0.5, "classification": "Hold", "confidence": "High",
                      "flag": "ok", "rec_reason": None, "reasons": []}],
    }
    payload = build_widget(data)
    WidgetPayload.model_validate(payload)   # required fields present + well-typed
    assert payload["api_version"] == API_VERSION


def test_widget_requires_token_when_configured(tmp_path):
    (tmp_path / "widget.json").write_text(json.dumps({"portfolio": {"value": 42}, "holdings": []}))
    app.dependency_overrides[get_output_dir] = lambda: tmp_path
    app.dependency_overrides[get_expected_token] = lambda: "secret"
    try:
        with TestClient(app) as c:
            assert c.get("/widget.json").status_code == 401  # no token
            r = c.get("/widget.json", headers={"Authorization": "Bearer secret"})
            assert r.status_code == 200
            assert r.json()["portfolio"]["value"] == 42
    finally:
        app.dependency_overrides.clear()


def test_widget_survives_nan_in_file(tmp_path):
    # A widget.json with NaN (Python writes a bare `NaN` literal) must be served as valid
    # JSON with nulls, not a 500 (Starlette's JSONResponse uses allow_nan=False).
    (tmp_path / "widget.json").write_text(
        json.dumps({
            "portfolio": {"value": 42, "day_change_pct": float("nan")},
            "holdings": [{"symbol": "X", "ret_20d": float("nan")}],
        })
    )
    app.dependency_overrides[get_output_dir] = lambda: tmp_path
    app.dependency_overrides[get_expected_token] = lambda: None
    try:
        with TestClient(app) as c:
            r = c.get("/widget.json")
            assert r.status_code == 200
            body = r.json()
            assert body["portfolio"]["day_change_pct"] is None
            assert body["holdings"][0]["ret_20d"] is None
    finally:
        app.dependency_overrides.clear()


def test_theses_put_then_get(tmp_path):
    sf = bootstrap(f"sqlite:///{tmp_path / 'theses.db'}")  # SQLite create_all builds the table
    app.dependency_overrides[get_session_factory] = lambda: sf
    app.dependency_overrides[get_expected_token] = lambda: None
    try:
        with TestClient(app) as c:
            assert c.get("/theses").json() == []
            r = c.put("/theses/tcs", json={
                "thesis": "quality IT", "conviction": "high",
                "target_weight_pct": 8, "exit_if": ["revenue decline 2 quarters"]})
            assert r.status_code == 200
            body = r.json()
            assert body["symbol"] == "TCS"  # sanitised + uppercased
            assert body["exit_if"] == ["revenue decline 2 quarters"]
            lst = c.get("/theses").json()
            assert len(lst) == 1 and lst[0]["symbol"] == "TCS"
            # update is idempotent (upsert, not duplicate)
            c.put("/theses/TCS", json={"conviction": "medium"})
            assert len(c.get("/theses").json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_theses_seed_and_load_from_db(tmp_path):
    sf = bootstrap(f"sqlite:///{tmp_path / 'seed.db'}")
    yaml_path = tmp_path / "theses.yaml"
    yaml_path.write_text("INFY:\n  thesis: digital growth\n  conviction: medium\n  exit_if:\n    - margin below 20%\n")
    assert seed_theses_from_yaml(sf, yaml_path) == 1
    assert seed_theses_from_yaml(sf, yaml_path) == 0  # idempotent: table already seeded
    theses = load_theses_from_db(sf)
    assert theses["INFY"]["conviction"] == "medium"
    assert theses["INFY"]["exit_if"] == ["margin below 20%"]


def test_widget_404_when_not_generated(tmp_path):
    app.dependency_overrides[get_output_dir] = lambda: tmp_path
    app.dependency_overrides[get_expected_token] = lambda: None  # open (dev)
    try:
        with TestClient(app) as c:
            assert c.get("/widget.json").status_code == 404
    finally:
        app.dependency_overrides.clear()
