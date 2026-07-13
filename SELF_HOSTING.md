# Self-Hosting Guide

SM Adviser is **self-hosted**: you run the backend on your own always-on machine, with your
own broker + AI credentials, and the iOS app connects to *your* server. Nothing goes through
anyone else's service — your portfolio data stays on your machine.

This guide takes you from `git clone` to a running daily agent. It's written so you can either
follow it by hand **or** open the repo in **Claude Code** and say *"set up this server following
SELF_HOSTING.md"* — see [Using Claude Code](#using-claude-code) at the end.

> **Disclaimer / compliance:** SM Adviser is for personal, informational use — it is not
> investment advice and never places trades. Publicly redistributing signals in India may
> require SEBI IA/RA registration; running it for yourself is a personal tool. Do your own
> diligence.

---

## What you're setting up

```
Your always-on machine (Linux or macOS + Docker)
  ├─ Postgres            (docker)         — stores runs
  ├─ API  :8787          (docker)         — serves the app: widget.json, reports, /stock/*
  └─ jobs (docker, scheduled):
       morning-run   — daily: Kite holdings → technicals → fundamentals → scoring → Claude → report
       intraday-run  — market hours: refresh live prices only
       migrate       — apply DB schema (Alembic)
  └─ Tailscale (optional) — private HTTPS so your phone reaches the server anywhere
```

Market candles use free Yahoo Finance; fundamentals use public screener.in — so you do **not**
need Zerodha's paid data add-ons.

---

## Prerequisites

- **A machine that stays on** for the morning run (Intel NUC, mini PC, Raspberry Pi 4/5, an old
  laptop, or a small cloud VM). Linux or macOS.
- **Docker + Docker Compose** installed ([docs.docker.com/engine/install](https://docs.docker.com/engine/install/)).
- **Git**.
- Accounts/keys (next section).

---

## Step 1 — Get your credentials

You need your own, not the author's.

### a) Zerodha Kite Connect app (broker access)
1. You need a **Zerodha** trading account.
2. Go to **[developers.kite.trade](https://developers.kite.trade/)** → create an app.
3. Copy the **API Key** and **API Secret**. (This agent only *reads holdings*, which base Kite
   Connect access covers — you do **not** need the paid historical-data add-on. App pricing is
   Zerodha's and may change; check their site.)
4. Set the app's **Redirect URL** to `http://127.0.0.1/` (used only for the manual token flow).
5. For **unattended daily login**, the agent signs in with your credentials + a TOTP seed. When
   you enable an **authenticator-app (TOTP)** as your Kite external 2FA, save the **base32 secret
   key** it shows you — that becomes `KITE_TOTP_SECRET`.
   > This uses Kite's internal login flow to get a daily token without a human — a ToS grey area
   > intended for personal use. If you'd rather not, you can paste a fresh request-token manually
   > each day instead (not cron-friendly).

### b) Anthropic API key (the analyst narrative)
- Get a key at **[console.anthropic.com](https://console.anthropic.com/)** and set a small budget
  cap. A daily run costs a few cents (~6k tokens). This is `ANTHROPIC_API_KEY`.

### c) Two secrets you generate yourself
```bash
openssl rand -hex 24   # -> POSTGRES_PASSWORD
openssl rand -hex 32   # -> WIDGET_API_TOKEN  (the app presents this as a bearer token)
```

---

## Step 2 — Clone and configure

```bash
git clone <your-fork-or-this-repo-url> sm-adviser
cd sm-adviser

cp .env.example .env
cp config.example.yaml config.yaml     # optional: benchmarks, thresholds, allocation limits
cp theses.example.yaml theses.yaml     # optional now; you'll scaffold it from your holdings later
chmod 600 .env
```

Edit **`.env`** and fill in:
```ini
PORTFOLIO_CONNECTOR=zerodha
POSTGRES_PASSWORD=<the hex you generated>
WIDGET_API_TOKEN=<the hex you generated>

KITE_API_KEY=<from step 1a>
KITE_API_SECRET=<from step 1a>
KITE_USER_ID=<your Zerodha client id, e.g. AB1234>
KITE_PASSWORD=<your Kite login password>
KITE_TOTP_SECRET=<base32 TOTP seed from step 1a>

ANTHROPIC_API_KEY=<from step 1b>
```
Leave `DATABASE_URL` **unset/commented** — Docker Compose injects the Postgres URL automatically.

---

## Step 3 — Build, migrate, run

```bash
docker compose build
docker compose --profile job run --rm migrate     # create the DB schema (Alembic)
docker compose up -d                               # start Postgres + API
docker compose ps                                  # both should be healthy
curl -fsS localhost:8787/health                    # -> {"status":"ok"}
```

First real run (logs into Kite via TOTP, pulls holdings, computes everything, writes the report +
widget + per-stock pages):
```bash
docker compose --profile job run --rm morning-run
```
You should see a JSON summary with your holdings count, `recommendations`, `narrative: true`, and
`stock_pages`. If Kite login fails, double-check `.env` char-by-char (a single typo in
`KITE_PASSWORD`/`KITE_TOTP_SECRET` is the usual culprit).

---

## Step 4 — Write your theses (the heart of the agent)

The agent judges each holding against *why you bought it*. Scaffold a starting file from your
actual holdings, then fill it in:
```bash
docker compose --profile job run --rm morning-run   # ensures holdings are in the DB
docker compose run --rm morning-run python -m app.reasoning.scaffold_theses
```
Edit `theses.yaml`: for each stock write the `thesis`, `bought_reason`, `conviction`, a
`target_weight_pct`, and tailor the `exit_if` conditions. Re-run `morning-run` — the classifications
and the Claude narrative get sharper. (`theses.yaml` is gitignored; it's yours.)

---

## Step 5 — Schedule it (daily + intraday)

On Linux with systemd, install the timers (edit the paths/user inside them first — they assume
`/home/<you>/sm-adviser`):
```bash
sudo timedatectl set-timezone Asia/Kolkata
sudo cp deploy/sm-adviser-morning.{service,timer} /etc/systemd/system/
sudo cp deploy/sm-adviser-intraday.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sm-adviser-morning.timer sm-adviser-intraday.timer
```
- **morning** runs Mon–Fri 08:00 IST (full analysis).
- **intraday** refreshes live prices every 15 min during market hours.

Optional monitoring (failure-only email alerts) is in `deploy/monitor/` — see `deploy/README.md`.

---

## Step 6 — Reach it from the iOS app (Tailscale HTTPS)

The app requires HTTPS. The easiest private, valid-certificate route is **Tailscale**:
```bash
curl -fsSL https://tailscale.com/install.sh | sudo sh
sudo tailscale up
# Enable "HTTPS Certificates" once in the Tailscale admin console (DNS page), then:
sudo tailscale serve --bg --https=8443 8787       # HTTPS 8443 -> API 8787
```
Your server is now at `https://<machine>.<your-tailnet>.ts.net:8443` with a real Let's Encrypt cert.

In the **SM Adviser** app (install TestFlight, then the app):
1. Put your phone on the **same Tailscale account**.
2. Open the app → enter your **server URL** (`https://…ts.net:8443`) and your **`WIDGET_API_TOKEN`**.
3. Add the home-screen widget. Done.

> Prefer not to use Tailscale? Any way to expose `:8787` behind HTTPS with a valid cert works
> (a reverse proxy with a real domain, Cloudflare Tunnel, etc.). The app rejects plain HTTP.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Kite login fails | Re-check `.env` (typos in `KITE_PASSWORD`/`KITE_TOTP_SECRET` are #1); confirm the TOTP seed matches your authenticator. |
| `order_flow: 0` | NSE blocks datacenter IPs; harmless (confirmation-only signal). Works on residential IPs, degrades gracefully otherwise. |
| App says "resource could not be loaded… secure connection" | The app needs HTTPS — use the Tailscale step, not `http://`. |
| Schema errors after `git pull` | `docker compose --profile job run --rm migrate` to apply new migrations. |
| API 404 on `/stock/...` after code update | Restart the API to load new routes: `docker compose restart api`. |

---

## Using Claude Code

This repo ships a `CLAUDE.md` so **Claude Code** understands it immediately. To self-host with it:
1. Install Docker + Git, `git clone` the repo, `cd` in.
2. Run `claude` and say:
   > *"Set up this SM Adviser server on this machine by following SELF_HOSTING.md. Ask me for the
   > credentials it needs (Kite, Anthropic), generate the two secrets, fill in `.env`, then build,
   > migrate, run the first morning job, and set up the daily timer."*
3. Claude will walk the steps, prompt you for each secret (it won't invent them), and verify each
   stage. You still create the Zerodha/Anthropic accounts and paste those keys yourself.
