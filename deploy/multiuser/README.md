# Multi-user hosting

Host SM Adviser for a few people (family / close friends) on one NUC — each as an **isolated
instance**: their own database, port, token, and state, sharing the primary image, Postgres, and
Docker network. No multi-tenancy in the app; each person points the app at *their* instance.

> **Trust note:** each instance stores that user's Zerodha login + TOTP seed on your machine. Only
> do this for people who explicitly consent. It's read-only (the `ReadOnlyKite` guard blocks orders).

## Architecture

```
 one shared Postgres (sm-adviser-db)  ── databases: sma_<name> per user
 one shared image (sm-adviser:latest) + one Docker network (sm-adviser_default)
 primary (you):   api :8787  <- tailscale serve :8443
 user "priya":    api :8788  <- tailscale serve :8444   (db sma_priya)
 user "arjun":    api :8789  <- tailscale serve :8445   (db sma_arjun)
 state per user:  ~/sma-instances/<name>/{.env, reports_out/, kite_token.json}
```

## Add a user
On the NUC, from `~/sm-adviser`:
```bash
./deploy/multiuser/add-user.sh priya        # prompts for their Zerodha creds
# or, to smoke-test the machinery without creds:
./deploy/multiuser/add-user.sh test --mock
```
It assigns the next ports, creates their DB, migrates, starts their API, runs the first morning
job, sets up `tailscale serve` on their HTTPS port, and prints their **URL + token**.

Then:
1. **Add their phone to your tailnet** (Tailscale admin → invite), so they can reach the NUC.
2. Give them the **TestFlight** app + their **URL** (`https://<nuc>.ts.net:<port>`) + **token**.

## Schedule everyone
Install the looping timers once (they run every registered instance, staggered after your own):
```bash
sudo cp deploy/multiuser/sma-users-morning.{service,timer} /etc/systemd/system/
sudo cp deploy/multiuser/sma-users-intraday.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sma-users-morning.timer sma-users-intraday.timer
```

## Manage
```bash
cat ~/sma-instances/registry                    # who's onboarded
./deploy/multiuser/run-all.sh morning-run        # run everyone now
./deploy/multiuser/remove-user.sh priya          # stop (keeps DB + state)
./deploy/multiuser/remove-user.sh priya --purge  # stop + delete DB + state
# one instance's containers:
docker compose -p sma-priya --env-file ~/sma-instances/priya/.env \
  -f deploy/multiuser/docker-compose.user.yml ps
```

## Updating code
`git pull` in `~/sm-adviser`, rebuild the shared image once, restart each API:
```bash
docker compose build           # rebuilds sm-adviser:latest (shared)
docker compose up -d api       # primary
for n in $(cat ~/sma-instances/registry); do
  docker compose -p sma-$n --env-file ~/sma-instances/$n/.env \
    -f deploy/multiuser/docker-compose.user.yml up -d api
done
```
Schema changes: run `migrate` per instance (each has its own DB) — `run-all.sh` pattern.
