"""FastAPI app serving widget.json + the latest report to the iOS widget over Tailscale.

Read-only. Bearer-token auth is enforced when WIDGET_API_TOKEN is set (recommended on the
NUC); left open only for local dev, where it also sits behind Tailscale. Run with:
    uvicorn app.api.main:app --host 0.0.0.0 --port 8787
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import get_settings, load_yaml_config

app = FastAPI(title="SM-Adviser Widget API", docs_url=None, redoc_url=None)


def get_output_dir() -> Path:
    cfg = load_yaml_config(get_settings().portfolio_config)
    return Path((cfg.get("report") or {}).get("output_dir", "reports_out"))


def get_expected_token() -> str | None:
    return get_settings().widget_api_token


def require_auth(
    authorization: str | None = Header(default=None),
    expected: str | None = Depends(get_expected_token),
) -> None:
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/widget.json")
def widget(_: None = Depends(require_auth), output_dir: Path = Depends(get_output_dir)):
    path = output_dir / "widget.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="widget.json not generated yet")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/report/latest", response_class=HTMLResponse)
def latest_report(_: None = Depends(require_auth), output_dir: Path = Depends(get_output_dir)) -> str:
    reports = sorted(output_dir.glob("report_*.html"))
    if not reports:
        raise HTTPException(status_code=404, detail="no report generated yet")
    return reports[-1].read_text(encoding="utf-8")


@app.get("/stock/{symbol}", response_class=HTMLResponse)
def stock_analysis(
    symbol: str,
    _: None = Depends(require_auth),
    output_dir: Path = Depends(get_output_dir),
) -> str:
    # Sanitise to the charset used in tradingsymbols; blocks path traversal.
    safe = re.sub(r"[^A-Za-z0-9&_-]", "", symbol)
    path = output_dir / f"stock_{safe}.html"
    if not safe or not path.exists():
        raise HTTPException(status_code=404, detail="no analysis for this stock yet")
    return path.read_text(encoding="utf-8")
