# CLAUDE.md — project context for Claude Code

## What this is
SM Adviser is a **private, read-only, daily portfolio-intelligence agent** for the Indian market
(Zerodha/Kite). Each morning it reads the user's holdings, computes technicals + fundamentals,
scores each holding against its written thesis, classifies it **Hold / Watch / Accumulate / Trim /
Exit-Candidate** with reasoning + evidence, and writes a Claude-generated narrative. It **never
places trades** — advisory only. A native iOS app + home-screen widget read the output over HTTPS.

Self-hosted: the user runs the backend on their own machine with their own credentials. To set up
a fresh server, follow **`SELF_HOSTING.md`**. The **live host is the Mac Mini** (`mini`, Docker via
Colima, scheduled by launchd) — ops in **`deploy/macos/README.md`**; it replaced an Intel NUC
(cutover runbook: **`deploy/MIGRATE-TO-MINI.md`**). The Linux/systemd path is **`deploy/README.md`**.
Design rationale and phase history are in **`BUILD_PLAN.md`**.

## Architecture (Python 3.12)
```
app/
  jobs/morning_run.py     # THE orchestrator: connectors → analytics → scoring → narrative → render
  jobs/intraday_refresh.py# light widget.json price refresh during market hours (no DB/LLM)
  connectors/             # swappable interfaces + impls: portfolio (mock|zerodha), market_data
                          #   (yfinance), order_flow (nse), fundamentals (screener)
  auth/kite_login.py      # daily Kite access-token: cached-per-day + headless TOTP login
  analytics/              # technicals.py, fundamentals.py, order_flow.py, market.py (pure
                          #   functions; market.py = index moves + portfolio-vs-benchmark delta)
  reasoning/              # scoring.py (6 sub-scores→composite→bands+hysteresis + deterministic
                          #   price_trigger), theses.py (DB-authoritative; export_theses.py dumps
                          #   back to theses.yaml),
                          #   recommender.py, llm.py (Anthropic|mock), narrative.py, prompts.py
  reports/                # gather.py (join a run's data), daily_report.py, widget_json.py,
                          #   stock_page.py (per-stock analysis one-pager)
  api/main.py             # FastAPI: /widget.json, /report/latest, /stock/{symbol}, /theses,
                          #   /status (connector health + LLM token/cost), /meta, /health (bearer auth)
  storage/                # SQLAlchemy models + engine/session (db.py)
  safety/guardrails.py    # ReadOnlyKite wrapper (blocks orders), bounded-language enforcement
ios/PortfolioWidget/      # SwiftUI app + WidgetKit extension (XcodeGen project.yml)
migrations/               # Alembic
deploy/                   # Dockerfile is at root; sync script, monitoring, README (Linux/systemd)
  macos/                  # launchd agents + job wrapper for the live Mac Mini host
  MIGRATE-TO-MINI.md      # one-time NUC -> Mac Mini cutover runbook
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
services **morning-run**, **intraday-run**, **weekly-screen**, **migrate** (run via
`docker compose --profile job run --rm <svc>`). Code is bind-mounted at `/app`, so a code change =
restart, not rebuild (deps change = `--build`). On the Mac Mini the Docker daemon is **Colima**, and
its `$HOME` mount must be **writable** (`--mount "$HOME/sm-adviser:w"`) or every run fails to write
`reports_out/`. Schedules are **launchd** agents in `deploy/macos/`, all routed through
`sma-job.sh`; job logs are `~/Library/Logs/sm-adviser/*.log`, not journald.

## Conventions & gotchas
- **DB schema:** SQLite (dev/tests) auto-creates via `create_all`; **Postgres is Alembic-managed**.
  After changing `app/storage/models.py`: `alembic revision --autogenerate -m "..."`, commit it,
  then `docker compose --profile job run --rm migrate`. Do NOT hand-`ALTER`.
- **API route changes** need an API restart to load: `docker compose restart api`.
- **Secrets** live in `.env` / `theses.yaml` / `config.yaml` / `kite_token.json` — all gitignored.
  Never print or commit them; never echo a token to stdout. This includes **indirect** leaks:
  `bash -x`/`set -x` on `deploy/monitor/sma-watchdog.sh` expands its authed `curl` and prints
  `WIDGET_API_TOKEN` in the trace. Debug those scripts with targeted `echo`s, not shell tracing.
- **Kite tokens** are single-use, ~2-min, and cached per-day in `kite_token.json`.
- **Theses live in the DB** (app-editable), NOT `theses.yaml` — that file only seeds an *empty*
  table, so hand-editing it changes nothing. `python -m app.reasoning.export_theses` dumps the DB
  back to it; run that after thesis edits so the readable copy isn't stale, and copy it to the Mac,
  which is the rsync source. `PUT /theses/{symbol}` is a **partial** update (`exclude_unset`):
  omitted fields are preserved, so an app edit can't silently null a stop loss.
- **`exit_if` is free text judged by the LLM; `stop_below`/`take_above` are arithmetic** and fire
  in `score_holding` before any LLM runs, forcing Exit-Candidate. Price rules belong in the latter —
  a stop that depends on a model's daily reading is not a stop.
- **order_flow returns 0** from datacenter IPs (NSE anti-bot); harmless, confirmation-only.
- **Market context** (`widget.json.market`) answers "is everything red, or just my stocks?".
  **This Kite plan has no market-data subscription** — `quote`/`ltp`/`ohlc` all raise
  `PermissionException` (verified 2026-09-28), so the index move cannot come off the holdings'
  own feed and both jobs use yfinance daily candles: the last completed session pre-open, and
  today's *running* bar during the session (Yahoo keeps it updating, so a 2-candle pull is a
  live-enough intraday index move). The Kite path is still tried first and is correct for anyone
  who does hold the subscription — and there, the day change must be computed from `last_price`
  vs `ohlc.close`, because Kite returns **`net_change` = 0 for indices**.
  Benchmarks come from `config.yaml` `portfolio.benchmarks.broad` — adding one is a config line.
- **The app requires HTTPS** (ATS enforced); serve via Tailscale (`tailscale serve --https=8443 8787`).
  On macOS use the **Homebrew `tailscale` formula** (`sudo brew services start tailscale`) — the
  `.pkg`/App Store builds gate `tailscaled` behind a GUI-approved network extension. Under `sudo`,
  call it by absolute path (`/opt/homebrew/bin/tailscale`); sudo's PATH prefers `/usr/local/bin`.
- **FileVault is ON on the Mac Mini**, so it cannot boot unattended. Never `sudo reboot` it
  remotely — use `sudo fdesetup authrestart`, or it strands at the preboot unlock screen with no
  SSH. Automatic macOS updates are disabled so the OS can't reboot itself.
- **A reboot leaves the stack down until someone logs in** (verified 2026-09-26). `authrestart`
  boots the OS and returns sshd + tailscaled, but Colima, Docker, the API and all four launchd
  agents are *user* LaunchAgents: `gui/501` doesn't exist until login, and `launchctl bootstrap`
  over SSH fails with `125: Domain does not support specified action`. One login restores
  everything; Screen Sharing to :5900 reaches the login window, so it's a remote fix.
  Corollary: the watchdog is a user agent too, so it cannot alert you that the host is down. That
  is covered by an **off-box dead-man's switch**: the Mini publishes heartbeats over SSH to the NAS
  and `deploy/monitor/nas-deadman.sh` there alerts when they stop. Heartbeats go over **SSH, not the
  SMB mount** — launchd jobs get `Operation not permitted` on network volumes, so a mount-based
  heartbeat passes manual tests and never fires in production.
- Keep the read-only, no-auto-trading boundary and the "not investment advice" disclaimers intact.

## Tests must pass before commit
`pytest` is the gate. Match existing style; keep functions pure and injectable.
