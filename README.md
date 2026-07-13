# Portfolio Agent — Indian Market Intelligence (Zerodha/Kite)

A **private, read-only, advisory** daily portfolio agent for the Indian stock market.
Each morning it reads your Zerodha portfolio, analyzes what changed, checks each holding
against your written investment thesis, and classifies it **Hold / Watch / Accumulate /
Trim / Exit-Candidate** with reasoning, confidence, and evidence.

> **Boundary:** decision support, not autonomous advice. It never places trades. Commercial
> use in India requires SEBI IA/RA review. See `Zerodha_Indian_Market_Portfolio_Agent_Spec.docx`
> and `BUILD_PLAN.md`.

## Status

**Working end-to-end.** The full daily pipeline runs against a live Zerodha account:
holdings → technicals (yfinance) → fundamentals (screener.in) → six-sub-score thesis-aware
scoring → Claude narrative → daily report + `widget.json` + per-stock analysis pages, served by
FastAPI. A native **iOS app + home-screen widget** (in `ios/`) reads it over HTTPS, with near-live
intraday prices and PDF-shareable analysis. Runs 24/7 in Docker (Postgres) with scheduled jobs.

Design rationale and phase history: `BUILD_PLAN.md`.

## Run your own (self-hosting)

The backend is **self-hosted** — you run it on your own always-on machine with your own Zerodha +
Anthropic credentials; the app connects to *your* server. Full walkthrough (from `git clone` to a
scheduled agent + the app), including a "let Claude Code do it" path:

### → [`SELF_HOSTING.md`](SELF_HOSTING.md)

Ops/deployment details (Docker stack, migrations, systemd timers, monitoring): [`deploy/README.md`](deploy/README.md).

## Quickstart (local dev — no credentials)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the tests (hermetic, in-memory SQLite)
pytest

# Run the daily job against the mock portfolio (writes to data/portfolio.db)
python -m app.jobs.morning_run
# or, after install:  morning-run
```

Copy the example configs before customizing:

```bash
cp .env.example .env                 # runtime + secrets (gitignored)
cp config.example.yaml config.yaml   # tunables (gitignored)
cp theses.example.yaml theses.yaml   # WHY you own each stock — the heart of the agent
```

## Layout

```
app/
  auth/         # Kite daily-token refresh (Phase 1)
  connectors/   # mock (Phase 0) + zerodha (Phase 1) — Kite-shaped, drop-in
  analytics/    # technicals, fundamentals, portfolio risk (Phase 2+)
  reasoning/    # thesis checks, scoring, LLM narrative (Phase 4)
  reports/      # daily report + widget.json (Phase 3/7)
  api/          # FastAPI serving widget.json (Phase 3+)
  storage/      # SQLAlchemy models + engine/session
  safety/       # guardrails, bounded language (Phase 4)
  jobs/         # morning_run orchestrator
tests/          # hermetic tests + mock fixture
```

## Configuration knobs

| Where | What |
|-------|------|
| `.env` | `PORTFOLIO_CONNECTOR` (mock/zerodha), `DATABASE_URL`, Kite/LLM/widget secrets |
| `config.yaml` | benchmarks, allocation limits, analytics windows, scoring thresholds, source allowlist |
| `theses.yaml` | per-stock thesis + `exit_if` conditions |

## Database

- **Local dev / tests:** SQLite, auto-created, no setup.
- **Server (NUC):** `docker compose up -d` for Postgres, set `DATABASE_URL`, run Alembic migrations.
