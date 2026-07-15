# CLAUDE.md — project context for Claude Code

## What this is
SM Adviser is a **private, read-only, daily portfolio-intelligence agent** for the Indian market
(Zerodha/Kite). Each morning it reads the user's holdings, computes technicals + fundamentals,
scores each holding against its written thesis, classifies it **Hold / Watch / Accumulate / Trim /
Exit-Candidate** with reasoning + evidence, and writes a Claude-generated narrative. It **never
places trades** — advisory only. A native iOS app + home-screen widget read the output over HTTPS.

Self-hosted: the user runs the backend on their own machine with their own credentials. To set up
a fresh server, follow **`SELF_HOSTING.md`**. Deployment/ops details are in **`deploy/README.md`**.
Design rationale and phase history are in **`BUILD_PLAN.md`**.

## Architecture (Python 3.12)
```
app/
  jobs/morning_run.py     # THE orchestrator: connectors → analytics → scoring → narrative → render
  jobs/intraday_refresh.py# light widget.json price refresh during market hours (no DB/LLM)
  connectors/             # swappable interfaces + impls: portfolio (mock|zerodha), market_data
                          #   (yfinance), order_flow (nse), fundamentals (screener)
  auth/kite_login.py      # daily Kite access-token: cached-per-day + headless TOTP login
  analytics/              # technicals.py, fundamentals.py, order_flow.py (pure functions)
  reasoning/              # scoring.py (6 sub-scores→composite→bands+hysteresis), theses.py,
                          #   recommender.py, llm.py (Anthropic|mock), narrative.py, prompts.py
  reports/                # gather.py (join a run's data), daily_report.py, widget_json.py,
                          #   stock_page.py (per-stock analysis one-pager)
  api/main.py             # FastAPI: /widget.json, /report/latest, /stock/{symbol}, /theses,
                          #   /status (connector health + LLM token/cost), /meta, /health (bearer auth)
  storage/                # SQLAlchemy models + engine/session (db.py)
  safety/guardrails.py    # ReadOnlyKite wrapper (blocks orders), bounded-language enforcement
ios/PortfolioWidget/      # SwiftUI app + WidgetKit extension (XcodeGen project.yml)
migrations/               # Alembic
deploy/                   # Dockerfile is at root; systemd units, sync script, monitoring, README
```
Everything is **dependency-injected** (connectors, session factory, run_date) so tests are hermetic.

## Run & test
```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest                                   # hermetic, in-memory SQLite, ~85 tests
python -m app.jobs.morning_run           # mock pipeline, no creds, writes data/portfolio.db
```
Optional deps are extras: `connectors, analytics, marketdata, fundamentals, api, llm, postgres, dev`.

## Production runtime (Docker)
`docker-compose.yml` services: **db** (Postgres 16), **api** (uvicorn :8787), and job-profile
services **morning-run**, **intraday-run**, **migrate** (run via `docker compose --profile job run --rm <svc>`).
Code is bind-mounted at `/app`, so a code change = restart, not rebuild (deps change = `--build`).

## Conventions & gotchas
- **DB schema:** SQLite (dev/tests) auto-creates via `create_all`; **Postgres is Alembic-managed**.
  After changing `app/storage/models.py`: `alembic revision --autogenerate -m "..."`, commit it,
  then `docker compose --profile job run --rm migrate`. Do NOT hand-`ALTER`.
- **API route changes** need an API restart to load: `docker compose restart api`.
- **Secrets** live in `.env` / `theses.yaml` / `config.yaml` / `kite_token.json` — all gitignored.
  Never print or commit them; never echo a token to stdout.
- **Kite tokens** are single-use, ~2-min, and cached per-day in `kite_token.json`.
- **order_flow returns 0** from datacenter IPs (NSE anti-bot); harmless, confirmation-only.
- **The app requires HTTPS** (ATS enforced); serve via Tailscale (`tailscale serve --https=8443 8787`).
- Keep the read-only, no-auto-trading boundary and the "not investment advice" disclaimers intact.

## Tests must pass before commit
`pytest` is the gate. Match existing style; keep functions pure and injectable.
