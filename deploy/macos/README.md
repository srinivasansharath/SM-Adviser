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

## Off-box dead-man's switch

The on-box watchdog cannot tell you the host is down — it is a user LaunchAgent and dies with the
login session (proven 2026-09-26: a real outage, zero alerts, every state file still `ok`). So the
Mini publishes heartbeats *outward* and the NAS raises the alarm when they stop. Silence is the
alarm, which is the property an active prober cannot give you.

```
Mini                                          NAS (separate UPS line)
  sma-job.sh      --(ssh)-->  morning-run.json  --\
  sma-watchdog.sh --(ssh)-->  watchdog.json     --+--> nas-deadman.sh --(exit 1)--> DSM emails
                                                     every 15-20 min via Task Scheduler
```

| Heartbeat | Written by | Cadence | NAS tolerance |
|---|---|---|---|
| `watchdog.json` | `sma-watchdog.sh` | 20 min | 60 min (two misses) |
| `morning-run.json` | `sma-job.sh` | weekdays | 90 h (clears a weekend) |
| `weekly-screen.json` | `sma-job.sh` | Sundays 07:00 | 216 h (clears one missed week) |

`intraday-run` deliberately does **not** heartbeat: it is gated to market hours, so its silence is
normal and would alert daily. Each heartbeat carries `status` (`ok`/`fail`), so the NAS distinguishes
*"host is dead"* (stale/missing) from *"host is alive but unhealthy"* (`status=fail`).

**It publishes over SSH, not the SMB mount.** Writing to `/Volumes/home` works from a shell and
fails from launchd with `Operation not permitted` — macOS withholds network-volume access from
launchd jobs. A mount-based heartbeat therefore passes every manual test and silently never fires
in production. Uses `~/.ssh/id_ed25519_nas_heartbeat` (no passphrase), authorised on the NAS.

```bash
# check what the NAS last heard
ssh home-nas 'cat /volume1/homes/sharath/sm-adviser-heartbeat/*.json'
# run the listener by hand: silent + exit 0 = healthy, exit 1 = the report DSM would email
ssh home-nas '/volume1/homes/sharath/nas-deadman.sh; echo "exit: $?"'
# prove it still fires (then let the next real heartbeat clear it)
ssh home-nas 'touch -d "2 hours ago" /volume1/homes/sharath/sm-adviser-heartbeat/watchdog.json'
```

**Delivery does NOT go through DSM notifications.** They were configured, the task ran, the script
exited non-zero — and no mail arrived (2026-09-26). DSM's scheduler logs need root to diagnose, and
an alarm must not depend on a path that cannot be tested. `nas-deadman.sh` now sends its own mail
via `sma_sendmail.py` (python3 smtplib → Gmail), reading credentials from
`~/.sma-deadman-mail.env` (chmod 600, never in git). It still exits non-zero, so DSM stays a second
channel if it ever starts working — a duplicate alert beats none. Verified end to end: Gmail
accepted the message.

Install on the NAS: **DSM → Control Panel → Task Scheduler → Create → User-defined script**.
Schedule: Daily, start 00:00, *Continue running within the same day*, repeat **every 20 minutes**,
last run 23:40. Task Settings: `bash /volume1/homes/sharath/nas-deadman.sh`, tick *Send run details
by email* **and** *only when the script terminates abnormally* — that second tick is what makes
silence mean healthy. DSM's own notification settings deliver it, so no SMTP config or credentials
live on the NAS.

**Alert volume is rate-limited in the script, not by the schedule.** Running every 20 min means a
persistent fault would otherwise email ~30 times overnight, so `nas-deadman.sh` keeps break state in
`~/.sm-adviser-deadman/`: it alerts on the transition into a fault, stays silent while it persists,
reminds every `REMIND_HOURS` (default 6), and clears on recovery so the *next* fault alerts at once.
Recovery itself is not announced — exit 0 means DSM sends nothing by design.

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
    stores the unlock key for exactly one boot so the *machine* comes back by itself.
  - **But the stack does not.** `authrestart` creates no login session, so after a reboot you get
    sshd and tailscaled and nothing else — no Colima, no Docker, no API, and `launchctl list |
    grep -c sm-adviser` returns 0. They cannot be armed over SSH (`gui/501` doesn't exist:
    `Bootstrap failed: 125`). **One login restores all of it**, and Screen Sharing reaches the
    login window on :5900, so it's a remote fix. Verified 2026-09-26.
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
