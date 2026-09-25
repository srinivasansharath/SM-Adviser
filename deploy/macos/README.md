# macOS deployment (Mac Mini)

Runs the SM-Adviser backend 24/7 on the Mac Mini, in Docker via **Colima**, reachable from the
iPhone widget over Tailscale. This replaced the Intel NUC (see `../MIGRATE-TO-MINI.md` for the
one-time cutover; the systemd units in `../` are kept for Linux self-hosters).

## Architecture

```
                    ┌─────────────── Mac Mini (mini) ──────────────────┐
 iPhone widget ──►  │  :8787  api (uvicorn)  ──reads──►  reports_out/  │
 (via Tailscale)    │            │                          ▲          │
                    │            └── Postgres (db) ◄──writes─┤         │
                    │                    [ Colima VM ]       │         │
   launchd agent ──►│  morning-run (oneshot container) ───────┘         │
   Mon–Fri 08:00 IST│  kite → yfinance → NSE → screener → Claude        │
                    └──────────────────────────────────────────────────┘
```

Same `docker-compose.yml` as Linux. What differs on macOS:

| | Linux (NUC) | macOS (mini) |
|---|---|---|
| Docker | native daemon | **Colima** VM (`brew services start colima`) |
| Scheduling | systemd timers | **launchd** LaunchAgents, this directory |
| Job logs | `journalctl -u …` | `~/Library/Logs/sm-adviser/*.log` |
| `OnFailure=` | systemd unit | handled inside `sma-job.sh` |
| Repo path | `/home/sharath/sm-adviser` | `/Users/sharath/sm-adviser` |
| Watchdog state | `~/.local/state/…` | `~/Library/Application Support/sm-adviser-monitor` |

## The launchd jobs

| Job | Schedule | Alerts on failure |
|---|---|---|
| `com.sharath.sm-adviser.morning` | Mon–Fri 08:00 IST | yes |
| `com.sharath.sm-adviser.intraday` | every 15 min, gated to Mon–Fri 09:00–15:45 | no (by design) |
| `com.sharath.sm-adviser.weekly` | Sun 07:00 IST | yes |
| `com.sharath.sm-adviser.watchdog` | every 20 min + at login | it *is* the alerting |

`StartCalendarInterval` jobs re-fire if the Mac was asleep or off at the scheduled time — the
equivalent of systemd's `Persistent=true`.

Everything routes through **`sma-job.sh`**, which exists because launchd won't do it for us:
it fixes up the minimal launchd `PATH`, starts Colima if the VM is down, gates the intraday tick
to market hours so we don't spin ~70 pointless containers a day, and sends the failure mail that
systemd's `OnFailure=` used to.

## Install / update / remove

```bash
./deploy/macos/install-launchd.sh              # install + start (idempotent; re-run after edits)
./deploy/macos/install-launchd.sh --uninstall   # stop + remove
```
The plists are templated (`__SMA_REPO__`, `__SMA_HOME__`); the installer substitutes real paths
into `~/Library/LaunchAgents`. Don't hand-copy them.

## Ops cheatsheet

```bash
# state
colima status                             # is the Docker VM up?
docker compose ps                         # container status
launchctl list | grep sm-adviser          # loaded jobs (last exit code is the 2nd column)
curl -fsS localhost:8787/health

# logs
tail -f ~/Library/Logs/sm-adviser/morning-run.log      # the job itself
tail -f ~/Library/Logs/sm-adviser/launchd-morning.log  # what launchd saw
docker compose logs -f api

# run a job now, off schedule
launchctl kickstart -p gui/$(id -u)/com.sharath.sm-adviser.morning
# or directly, watching it live:
docker compose --profile job run --rm morning-run

# after a code change (code is bind-mounted, so this is a restart, not a rebuild)
docker compose restart api                # API route changes need this
docker compose up -d --build api          # only when dependencies changed
```

From the Mac: `SMA_HOST=mini ./deploy/sync-to-server.sh --restart`.

## Schema changes (Alembic)

```bash
# on the Mac (dev): generate, review, commit
alembic revision --autogenerate -m "add X"

# on the mini: sync, then apply
SMA_HOST=mini ./deploy/sync-to-server.sh
ssh mini 'cd ~/sm-adviser && docker compose --profile job run --rm migrate'
```

## Gotchas specific to this host

- **The Colima mount must be writable.** The stack writes `reports_out/`, `data/` and
  `kite_token.json` through the `/app` bind mount, and Colima mounts `$HOME` **read-only by
  default**. The VM was created with `--mount "$HOME/sm-adviser:w"`; if you ever recreate it
  (`colima delete`), that flag is not optional. Check with:
  ```bash
  docker run --rm -v "$HOME/sm-adviser:/t" alpine touch /t/.w && echo WRITABLE
  ```
- **FileVault is ON, so the mini cannot boot unattended.** After an unexpected reboot (power cut,
  panic) it sits at the preboot unlock screen — no SSH, no Screen Sharing — until someone types the
  password. Once they do, macOS passes that auth through to a login session, so the LaunchAgents and
  Colima return from that one password entry. Consequences for ops:
  - **Never `sudo reboot` remotely.** Use `sudo fdesetup authrestart` (supported on this mini), which
    stores the unlock key for exactly one boot so the machine comes back by itself.
  - **Automatic macOS updates are disabled** for the same reason — an unattended update reboot would
    silently stop the morning run. Update deliberately, then `authrestart`.
  - The on-box watchdog **cannot** tell you the mini is down; that needs an off-box check.
- **LaunchAgents need a login session,** and so does Colima — which the FileVault unlock provides.
  If someone logs out (rather than reboots), the stack stops until they log back in.
- **Tailscale is the Homebrew formula, not the `.pkg` or App Store app.** The `.pkg` is a GUI app
  whose `tailscaled` sits behind a network system extension needing a click in System Settings
  before anything runs — unusable over SSH. `brew install tailscale` +
  `sudo brew services start tailscale` gives a plain LaunchDaemon that starts at boot. Serve with
  `tailscale serve --bg --https=8443 8787` (no sudo needed for `serve` with the brew daemon). Use
  the absolute path whenever you *do* prefix `sudo` — sudo's PATH prefers `/usr/local/bin`.
- **You cannot test `serve` from the mini itself.** Serve proxies traffic from *peers*; a
  self-connection to its own tailnet address on :8443 completes TCP then hangs in the TLS
  handshake. Check `tailscale serve status` + `curl localhost:8787/health` locally, and do the
  real HTTPS check from your phone or another tailnet node.
- **Disk.** The watchdog alerts above 90 % and this is a desktop machine that also holds Photos
  and Documents; Colima's disk image grows as it's used. Keep real headroom.
- **`docker compose` is a plugin** installed by Homebrew. If `docker compose version` fails,
  the `~/.docker/cli-plugins/docker-compose` symlink is missing — see `../MIGRATE-TO-MINI.md` §1.5.
