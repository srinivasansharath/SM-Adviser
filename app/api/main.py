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
from ..reasoning.theses import upsert_thesis
from ..reports.candidates_page import render_candidates_page
from ..reports.widget_json import json_safe
from ..storage.db import default_session_factory
from .schemas import CandidateOut, CandidatesOut, Meta, ThesisOut, ThesisUpsert
from .version import API_VERSION, FEATURES, MIN_APP_BUILD, SERVER_VERSION

_METRIC_KEYS = ("roe", "roe_5y", "roce", "sales_cagr_5y", "profit_cagr_5y", "pe",
                "debt_to_equity", "promoter_holding", "promoter_pledge", "dividend_yield",
                "market_cap")


def _load_candidates(session_factory):
    """Latest weekly shortlist from the DB: (run_date, [detail dicts w/ rank], universe count)."""
    from ..storage.models import Candidate, Snapshot

    with session_factory() as s:
        latest = s.query(Candidate).order_by(Candidate.run_date.desc()).first()
        if not latest:
            return None, [], None
        rd = latest.run_date
        rows = s.query(Candidate).filter_by(run_date=rd).order_by(Candidate.rank).all()
        details = [{**(c.detail or {}), "rank": c.rank} for c in rows]
        snap = s.query(Snapshot).filter_by(run_date=rd, kind="screen").first()
        universe = (snap.payload or {}).get("universe") if snap else None
    return str(rd), details, universe


def _candidate_out(d: dict) -> CandidateOut:
    data, llm = d.get("data") or {}, d.get("llm") or {}
    metrics = {k: data[k] for k in _METRIC_KEYS if data.get(k) is not None}
    if d.get("peg") is not None:
        metrics["peg"] = d["peg"]
    subscores = {k: v for k, v in (d.get("subscores") or {}).items() if v is not None}
    return CandidateOut(
        symbol=d.get("symbol"), rank=d.get("rank"), composite=d.get("composite"),
        sector=data.get("sector"), industry=data.get("industry"),
        buckets=d.get("buckets") or [], verdict=llm.get("verdict"), conviction=llm.get("conviction"),
        thesis=llm.get("thesis"), tailwind=llm.get("tailwind"),
        exit_if=llm.get("exit_if") or [], risks=llm.get("risks") or [],
        subscores=subscores, metrics=metrics,
    )

app = FastAPI(title="SM-Adviser API", version=SERVER_VERSION, docs_url=None, redoc_url=None)


def get_output_dir() -> Path:
    cfg = load_yaml_config(get_settings().portfolio_config)
    return Path((cfg.get("report") or {}).get("output_dir", "reports_out"))


def get_expected_token() -> str | None:
    return get_settings().widget_api_token


def get_session_factory():
    return default_session_factory()


def require_auth(
    authorization: str | None = Header(default=None),
    expected: str | None = Depends(get_expected_token),
) -> None:
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/status")
def status(_: None = Depends(require_auth), sf=Depends(get_session_factory)):
    """Operational health (authed): per-connector status from the latest run + cumulative LLM
    token/cost spend, with an optional monthly-budget flag. Lets the operator (and the watchdog)
    spot a stalled connector — e.g. BSE blacklisting the NUC's IP — and know when to recharge."""
    from ..reports.status import build_status

    return build_status(sf, budget_usd=get_settings().monthly_budget_usd)


@app.get("/meta", response_model=Meta)
def meta() -> Meta:
    """Capability + version negotiation (open, like /health). The app reads this on connect to
    gate features and detect version mismatch. See PROTOCOL.md."""
    return Meta(
        api_version=API_VERSION,
        server_version=SERVER_VERSION,
        features=FEATURES,
        min_app_build=MIN_APP_BUILD,
    )


@app.get("/widget.json")
def widget(_: None = Depends(require_auth), output_dir: Path = Depends(get_output_dir)):
    path = output_dir / "widget.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="widget.json not generated yet")
    # json_safe strips any NaN/Inf so JSONResponse (strict, allow_nan=False) never 500s.
    return JSONResponse(json_safe(json.loads(path.read_text(encoding="utf-8"))))


@app.get("/report/latest", response_class=HTMLResponse)
def latest_report(_: None = Depends(require_auth), output_dir: Path = Depends(get_output_dir)) -> str:
    reports = sorted(output_dir.glob("report_*.html"))
    if not reports:
        raise HTTPException(status_code=404, detail="no report generated yet")
    return reports[-1].read_text(encoding="utf-8")


@app.get("/theses", response_model=list[ThesisOut])
def list_theses(_: None = Depends(require_auth), sf=Depends(get_session_factory)):
    """All per-stock theses (the app's editor reads these)."""
    from ..storage.models import Thesis

    with sf() as s:
        rows = s.query(Thesis).order_by(Thesis.symbol).all()
        return [ThesisOut.model_validate(r, from_attributes=True) for r in rows]


@app.put("/theses/{symbol}", response_model=ThesisOut)
def put_thesis(symbol: str, body: ThesisUpsert, _: None = Depends(require_auth),
               sf=Depends(get_session_factory)):
    """Create/update one holding's thesis from the app. Next morning run uses it."""
    safe = re.sub(r"[^A-Za-z0-9&_-]", "", symbol).upper()
    if not safe:
        raise HTTPException(status_code=400, detail="invalid symbol")
    row = upsert_thesis(sf, safe, body.model_dump())
    return ThesisOut.model_validate(row, from_attributes=True)


@app.get("/candidates.json", response_model=CandidatesOut)
def candidates_json(_: None = Depends(require_auth), sf=Depends(get_session_factory)):
    """The latest weekly new-stock shortlist as structured JSON (app renders it natively)."""
    rd, details, universe = _load_candidates(sf)
    return CandidatesOut(
        api_version=API_VERSION, run_date=rd, universe=universe,
        candidates=[_candidate_out(d) for d in details],
        disclaimer="Decision support, not investment advice.",
    )


@app.get("/candidates", response_class=HTMLResponse)
def candidates_html(_: None = Depends(require_auth), sf=Depends(get_session_factory)) -> str:
    """The latest weekly shortlist as a one-pager (shown in the app's web view)."""
    rd, details, universe = _load_candidates(sf)
    if rd is None:
        raise HTTPException(status_code=404, detail="no screener run yet")
    return render_candidates_page(details, rd, universe)


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
