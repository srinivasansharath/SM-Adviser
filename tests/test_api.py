import json

from fastapi.testclient import TestClient

from app.api.main import app, get_expected_token, get_output_dir


def test_health():
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}


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


def test_widget_404_when_not_generated(tmp_path):
    app.dependency_overrides[get_output_dir] = lambda: tmp_path
    app.dependency_overrides[get_expected_token] = lambda: None  # open (dev)
    try:
        with TestClient(app) as c:
            assert c.get("/widget.json").status_code == 404
    finally:
        app.dependency_overrides.clear()
