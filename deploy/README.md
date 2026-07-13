# NUC Deployment

Runs the SM-Adviser backend 24/7 on the Intel NUC (Ubuntu), in Docker, reachable from the
iPhone widget over Tailscale.

## Architecture

```
                    ┌──────────────── NUC (nuc-ubuntu) ────────────────┐
 iPhone widget ──►  │  :8787  api (uvicorn)  ──reads──►  reports_out/  │
 (via Tailscale)    │            │                          ▲          │
                    │            └── Postgres (db) ◄──writes─┤          │
                    │                                        │          │
   systemd timer ──►│  morning-run (oneshot container) ──────┘          │
   Mon–Fri 08:00 IST│  kite → yfinance → NSE → screener → Claude        │
                    └───────────────────────────────────────────────────┘
```

- **db** — Postgres 16, localhost-only, data in the `pgdata` named volume.
- **api** — long-running FastAPI, serves `/widget.json`, `/report/latest`, `/health`.
- **morning-run** — the daily orchestrator; run once per day by the systemd timer, then exits.

Both app containers share one image (`sm-adviser:latest`) and bind-mount the repo at `/app`,
so `reports_out/`, `data/` and `kite_token.json` persist on the host disk.

## First-time setup

1. **Sync the repo to the NUC** (from the Mac — carries the gitignored `.env`, `config.yaml`,
   `theses.yaml` that aren't on GitHub):
   ```bash
   ./deploy/sync-to-nuc.sh
   ```

2. **On the NUC**, set the `.env` extras the server needs (append if missing):
   ```
   PORTFOLIO_CONNECTOR=zerodha
   POSTGRES_PASSWORD=<strong-random>
   WIDGET_API_TOKEN=<strong-random>       # the iOS widget presents this as a bearer token
   ```
   Leave `DATABASE_URL` unset/commented — compose injects the Postgres URL. `chmod 600 .env`.

3. **Build, migrate, start** the stack:
   ```bash
   cd ~/sm-adviser
   docker compose build
   docker compose --profile job run --rm migrate   # create/upgrade schema (Alembic)
   docker compose up -d                             # start db + api
   ```

4. **Seed the first report** (also verifies Kite/Claude end-to-end):
   ```bash
   docker compose --profile job run --rm morning-run
   ```

5. **Install the daily timer**:
   ```bash
   sudo timedatectl set-timezone Asia/Kolkata
   sudo cp deploy/sm-adviser-morning.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now sm-adviser-morning.timer
   systemctl list-timers sm-adviser-morning.timer
   ```

## Updating

```bash
./deploy/sync-to-nuc.sh --restart        # rsync latest code, rebuild + restart the API
```
Code is bind-mounted, so most changes need only an API restart; a dependency change needs
`--build` (which `--restart` does).

## Ops cheatsheet

```bash
docker compose ps                        # container status
docker compose logs -f api               # API logs
docker compose logs morning-run          # last job run
curl -fsS localhost:8787/health          # health
journalctl -u sm-adviser-morning.service # timer run history
```

## Schema changes (Alembic)

Postgres is schema-managed by **Alembic** (SQLite dev/tests still use `create_all`). After
changing a model in `app/storage/models.py`:

```bash
# on the Mac (dev): generate the migration from the model diff, review it, commit it
alembic revision --autogenerate -m "add X"

# on the NUC: sync, then apply
./deploy/sync-to-nuc.sh
ssh NUC-HadesCanyon-Linux 'cd ~/sm-adviser && docker compose --profile job run --rm migrate'
```

`migrate` runs `alembic upgrade head`. Existing rows are preserved (no more drop-and-recreate).
Check state with `docker compose --profile job run --rm migrate alembic current`.
