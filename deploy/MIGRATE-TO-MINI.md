# Migration runbook: Intel NUC → Mac Mini

One-time cutover of the SM Adviser backend off the NUC (Ubuntu, systemd, spontaneously
powers off and needs a wall-socket power cycle) onto the Mac Mini (`mini`, 192.168.1.40,
M4 Pro, macOS 26.3, arm64).

**Decisions taken for this migration**

| | Choice |
|---|---|
| Container runtime | **Colima + Docker CLI** — `docker-compose.yml` is reused verbatim |
| Scheduling | **launchd** LaunchAgents (`deploy/macos/`) replace the systemd timers |
| Disk encryption | **FileVault stays ON** (reversed 25 Sep). No auto-unlock exists, so an unexpected reboot needs one manual unlock — mitigated, not eliminated |
| Cutover style | **Hard cutover** — one verified morning run on the mini, then the NUC is retired |
| Tailnet identity | Mini **takes over the NUC's MagicDNS name**, so the iOS app URL + token are untouched |

> Repo path on the mini is `/Users/sharath/sm-adviser` (was `/home/sharath/sm-adviser`).

---

## Phase 0 — Rescue the NUC's data ✅ *done 2026-09-25*

Nothing else can start until this is done. These artefacts exist **only** on the NUC's disk —
there is no backup anywhere, and `config.yaml` has already been lost once to rsync
(commit `8214e8c`).

**What the rescue actually found** (keep this: it narrows what a rebuild has to recreate)

- The NUC came back on **WiFi at the same IP** (`192.168.1.234` — the UniFi lease held), so the
  `NUC-HadesCanyon-Linux` ssh alias needed no change. Latency 17–162 ms, so transfers are slow
  and the link dropped once mid-session.
- `.env`, `theses.yaml` and `deploy/monitor/alert.env` are **byte-identical** to the Mac's copies —
  no server-side drift. **`config.yaml` is the only genuinely server-only config file** (6 sections,
  all 6 screener band URLs intact).
- `~/sma-instances/registry` is **empty (0 bytes)** — the multi-user path was scaffolded 14 Jul and
  never used. Nothing to migrate there; `deploy/multiuser/` stays unported.
- Postgres holds **12 Jul → 25 Sep**: snapshots 200, holdings/metrics/scores/recommendations 236
  each, reports 114, candidates 150, llm_calls 90, theses 8. `events`/`order_flow`/`market_flow`
  are empty by design. Alembic version `c4e9a1f2b8d0` — **exactly the repo's head**, so the
  post-restore `migrate` must report "already at head".
- Booting the NUC fired the catch-up morning run (`Persistent=true`), which **succeeded** at 17:30
  IST (narrative true, 4 866 LLM tokens, `reports_out/report_2026-09-25.md`), and the catch-up
  weekly screener, which wrote today's **11-name shortlist**.

⚠️ **Booting the NUC immediately fires catch-up runs** for every missed `Persistent=true` timer —
a morning run *and* the weekly screener (which takes ~12 min, longer on WiFi). Let them finish or
stop them before dumping; `pg_dump` is MVCC-safe either way, it just won't contain late commits.

```bash
# 0.1 Stop everything writing, so the dump is consistent. (sudo is NOPASSWD on the NUC.)
ssh NUC-HadesCanyon-Linux 'sudo systemctl disable --now \
  sm-adviser-morning.timer sm-adviser-intraday.timer sm-adviser-weekly.timer \
  sma-watchdog.timer sma-users-morning.timer sma-users-intraday.timer'

# 0.2 Rescue bundle on the Mac.
mkdir -p ~/sm-adviser-nuc-backup && cd ~/sm-adviser-nuc-backup
scp NUC-HadesCanyon-Linux:'~/sm-adviser/{.env,config.yaml,theses.yaml,kite_token.json}' .
scp NUC-HadesCanyon-Linux:'~/sm-adviser/deploy/monitor/alert.env' .
scp NUC-HadesCanyon-Linux:'~/.msmtprc' ./msmtprc          # SMTP app password
rsync -az NUC-HadesCanyon-Linux:'~/sm-adviser/reports_out/' ./reports_out/
rsync -az NUC-HadesCanyon-Linux:'~/.local/state/sm-adviser-monitor/' ./monitor-state/
chmod 600 .env msmtprc

# 0.3 Postgres dump (custom format, for pg_restore).
ssh NUC-HadesCanyon-Linux 'cd ~/sm-adviser && docker compose up -d db && sleep 8 && \
  docker exec sm-adviser-db pg_dump -U portfolio -Fc portfolio' > portfolio.dump
pg_restore -l portfolio.dump | head          # sanity: must list tables, not be empty
ls -lh portfolio.dump

# 0.4 Record the Tailscale identity we're going to inherit.
ssh NUC-HadesCanyon-Linux 'tailscale status --json | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[\"Self\"][\"DNSName\"])"; \
  tailscale serve status'

# 0.5 Is the multi-user path in use? An EMPTY ~/sma-instances/registry means no — the directory
#     existing is not enough, it's scaffolded by default.
ssh NUC-HadesCanyon-Linux 'wc -c ~/sma-instances/registry 2>/dev/null || echo "single-user only"'

# 0.6 Second copy, off both machines — this is the gap that made config.yaml a single-disk file.
#     NOTE: rsync-over-SSH to the Synology fails ("Permission denied, please try again") — DSM
#     blocks it for this non-admin user. Pipe a tar over plain ssh instead.
D="/volume1/homes/sharath/Backups/sm-adviser-nuc-$(date +%F)"
ssh home-nas "mkdir -p '$D'"
tar -czf - -C ~ sm-adviser-nuc-backup | ssh home-nas "cat > '$D/sm-adviser-nuc-backup.tgz'"
ssh home-nas "gzip -t '$D/sm-adviser-nuc-backup.tgz' && tar -tzf '$D/sm-adviser-nuc-backup.tgz' | wc -l"
find ~/sm-adviser-nuc-backup | wc -l     # must match the count above
```

**Dump verification (25 Sep):** both formats taken — `portfolio.dump` (286 K, `-Fc` for
`pg_restore`) and `portfolio.sql.gz` (252 K, plain SQL so it's readable with no Postgres client).
Row counts inside the dump match the live DB exactly (snapshots 200, holdings/metrics/scores/
recommendations 236, reports 114, candidates 150, llm_calls 90, theses 8), and the embedded
`alembic_version` is `c4e9a1f2b8d0`. The NAS tarball holds 104 files, `gzip -t` clean.

**arm64 pre-flight (25 Sep):** the image had only ever been built on x86_64, and the Dockerfile
asserts "no build toolchain needed (all deps ship wheels)". Verified for `linux/aarch64` by
resolving every production dependency with `pip download --only-binary=:all: --platform
manylinux_2_28_aarch64 --python-version 3.12`: **70/70 packages resolve to wheels, 0 source
tarballs**, including the 19 compiled ones (numpy, pandas, lxml, cryptography, cffi, curl_cffi,
psycopg-binary, uvloop, httptools, watchfiles, websockets, zope.interface, protobuf, …). So the
`python:3.12-slim` base needs no compiler on Apple Silicon either — `docker compose build` should
be clean. Re-run that check if a dependency is ever pinned upward.

**Reconcile `.env`:** verify rather than assume. On 25 Sep these came back identical, but the NUC's
copy is authoritative if they ever diverge (it holds the live `POSTGRES_PASSWORD` and
`WIDGET_API_TOKEN`). Compare key *names*, never values:

```bash
diff <(grep -oE '^[A-Z_]+=' ~/sm-adviser-nuc-backup/.env | sort) \
     <(grep -oE '^[A-Z_]+=' ~/Projects/Code/SM-Adviser-Claude/.env | sort)
```

Same for `theses.yaml` — a thesis edited server-side would exist only in the rescue bundle.
(`cmp -s` both files; on 25 Sep both were byte-identical.)

---

**Timers stay off (decided 25 Sep).** The NUC produced its last run on 2026-09-25 and is not
covering the weekend, so `portfolio.dump` in the rescue bundle is **final** — Phase 2 restores that
exact file, no re-dump needed. The consequence is a deadline: **the mini must be serving before
Mon 2026-09-28 08:00 IST**, or that morning run is simply missed (the widget goes stale; nothing
breaks). If Phase 1 slips, re-enable the NUC timers and re-dump at cutover:
`ssh NUC-HadesCanyon-Linux 'sudo systemctl enable --now sm-adviser-morning.timer sm-adviser-intraday.timer'`

---

## Phase 1 — Prepare the mini *(needs your hands: GUI + sudo)*

Run these yourself; prefix with `!` in Claude Code if you want the output in this session.

**1.1 FileVault stays ON — and there is no way around the consequence.**

On Apple Silicon FileVault encrypts the Data volume, and macOS cannot boot past the preboot unlock
screen without a human secret: no daemon runs, there is no network stack, and automatic login is
unavailable by design. So **unattended boot is impossible while FileVault is on** — this is FDE
working correctly, not a misconfiguration. Note this is *not* a Colima-vs-native tradeoff: a
LaunchDaemon can't run before the volume is unlocked either, so the runtime choice is unaffected.

What *is* true: once someone unlocks at preboot, macOS passes that authentication through and logs
the user straight in — so the LaunchAgents and Colima come back from that single password entry,
with no second login.

The goal therefore becomes **"rarely reboots, and you hear about it fast"**:

| Mitigation | What it buys |
|---|---|
| **UPS** | The real fix. A brief outage never becomes a reboot. `pmset -g batt` shows AC only today, so there's none attached. |
| **Disable automatic macOS updates** | Removes the most likely *silent* reboot. `AutomaticallyInstallMacOSUpdates = 1` today, with 26.7 and macOS 27 pending. |
| **`sudo fdesetup authrestart`** for every planned reboot | Boots through FileVault without a prompt. `fdesetup supportsauthrestart` returns **true** on this mini. Never use plain `sudo reboot` remotely. |
| **Off-box dead-man's switch** | The on-box watchdog dies with the machine, so it can't report "I'm off". Something else has to notice. |
| **IP-KVM** (JetKVM / PiKVM, on the tailnet) | The only true remote fix: lets you type the FileVault password from anywhere. |

**1.2 Stop macOS rebooting itself** (keeps security-definition updates, which don't reboot):
```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate ConfigDataInstall -bool true
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool true
defaults read /Library/Preferences/com.apple.SoftwareUpdate | grep -E 'Automatic|ConfigData|Critical'
```
The `defaults write` commands above need **no reboot** — they only stop macOS from rebooting
*itself* later, which is the whole point. Do them now.

**Deferred 25 Sep:** installing the pending OS updates (macOS 26.7 minor, macOS 27 major) and the
reboot they require. That is a deliberate "later" — but until it happens, note that the mini is
running an OS with updates outstanding, and the reboot to apply them must use
`sudo fdesetup authrestart`, never plain `sudo reboot`.

**1.3 Disk — no longer a blocker.** **33 GiB free of 460 (93 % full)**; Library 143 G,
Pictures 103 G (a 103 GB Photos library), Documents 81 G. Colima realistically consumes ~8–10 GiB
(sparse image + `python:3.12-slim` + Postgres + pgdata), so 33 GiB is enough.

The 90 %-full watchdog threshold *was* the only problem, and that threshold was simply wrong for
this host: a desktop holding a photo library sits above 90 % permanently, while what matters is
whether the stack still has room. The check now measures **absolute free space**
(`DISK_FREE_GB_MIN`, default 15 GiB) instead of percent-full — see `deploy/monitor/sma-watchdog.sh`.
At 33 GiB free the mini is comfortably clean.

**Decided 25 Sep: leave the Photos library alone.** Freeing space is optional now, so it is not
being done under cutover pressure. Recorded for whenever it is revisited:

- A `.photoslibrary` **cannot live on a NAS** — Apple requires a locally-attached APFS/HFS+ volume;
  network volumes risk database corruption. A NAS copy is a *cold archive*, not an openable library,
  and the bundle should go inside a single container (sparsebundle via `ditto`) rather than as loose
  files over SMB, which mangles xattrs and the bundle flag.
- **iCloud Photos looks OFF** on this Mac (`MobileMeAccounts` lists no enabled `CLOUDPHOTOS`, and
  `PHOTO_STREAM` is not enabled) — unconfirmed in the UI. If that holds, the 103 GB local library is
  the **only** copy, so nothing may be deleted until a verified second copy exists.
- Of the 103 GB: `originals` 72 G is irreplaceable, `resources` 27 G is regenerable derivatives,
  `database` 2.1 G, `private` 436 M.
- Any copy must be taken with **Photos quit** — `photolibraryd`/`photoanalysisd` hold the SQLite
  database open (`-wal`/`-shm` present), so a hot copy is inconsistent.

**1.4 Power behaviour** (already correct — verify, don't blindly re-apply):
```bash
pmset -g custom | grep -E 'sleep|autorestart'   # expect sleep 0, autorestart 1
sudo systemsetup -gettimezone                   # expect Asia/Kolkata
```

**1.5 Homebrew + the Docker CLI stack**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

brew install colima docker docker-compose msmtp

# docker-compose is a CLI plugin; the docker CLI only finds it once it's linked.
mkdir -p ~/.docker/cli-plugins
ln -sfn "$(brew --prefix)/opt/docker-compose/bin/docker-compose" ~/.docker/cli-plugins/docker-compose
docker compose version        # must print v2.x — if it doesn't, nothing below works
```

**1.6 Start Colima with a *writable* mount** — the single most important flag here. The stack
bind-mounts the repo at `/app` and writes `reports_out/`, `data/` and `kite_token.json` into it.
Colima mounts the home directory **read-only by default**, which would make every run fail:
```bash
colima start --cpu 4 --memory 8 --disk 30 \
  --vm-type=vz --mount-type=virtiofs \
  --mount "$HOME/sm-adviser:w"

colima status
docker run --rm -v "$HOME/sm-adviser:/t" alpine sh -c 'touch /t/.mount-write-test && echo WRITABLE'
rm -f ~/sm-adviser/.mount-write-test

# Autostart at login (the flags above are persisted in ~/.colima/default/colima.yaml).
brew services start colima
```

**1.7 Tailscale — use the Homebrew formula, NOT the standalone `.pkg`.**

The `.pkg` from pkgs.tailscale.com was tried first on 25 Sep and is a dead end for a headless host:
it installs a **GUI app** whose `tailscaled` lives inside a *network system extension*, which macOS
parks at `[activated waiting for user]` until someone approves it in System Settings → General →
Login Items & Extensions. Nothing runs until that click, and it cannot be done over SSH. (Symptom if
you use the CLI anyway: `Fatal error: The current bundleIdentifier is unknown to the registry` —
that's the app binary being run outside its bundle.)

The formula gives the same version as a plain daemon, with no extension and no GUI:
```bash
brew install tailscale
sudo brew services start tailscale     # LaunchDaemon in /Library/LaunchDaemons -> starts at BOOT
sudo /opt/homebrew/bin/tailscale up    # prints a login URL to open
```
Use the **absolute path** under `sudo`: sudo's PATH puts `/usr/local/bin` ahead of
`/opt/homebrew/bin`, so a stray `/usr/local/bin/tailscale` would win. Don't create one.

`serve` and `cert` work normally — but wait for Phase 3: there's nothing on :8787 yet. Leave the
mini under its own name (`sharath4pro24gb`); the rename happens in Phase 3.

---

## Phase 2 — Move the app onto the mini ✅ *done 2026-09-25*

Verified on completion: arm64 build clean (all wheels, no compiler); every restored row count matches
the NUC; `alembic current` = `c4e9a1f2b8d0 (head)` with `upgrade head` a no-op; both containers
healthy; a real morning run succeeded (6 holdings, ₹197,503, narrative true, 0 violations); the same
run succeeded again **via launchd** (`exit 0`, 30 s), proving the wrapper's PATH/Colima path; the
intraday gate correctly skipped outside market hours without starting a container; and the msmtp
alert path delivered (`smtpstatus=250`).

`sma_health.state` arrived from the NUC already `fail` (BSE news degraded, 0/6 filings — pre-existing,
not caused by the move), so carrying the state files across correctly suppressed a duplicate alert.

```bash
# 2.1 Push code + the gitignored config from the Mac.
cd ~/Projects/Code/SM-Adviser-Claude
SMA_HOST=mini SMA_DEST=/Users/sharath/sm-adviser ./deploy/sync-to-server.sh

# 2.2 The rescued server-only files — the sync script deliberately never carries these
#     (config.yaml isn't on the Mac at all, and it protects the server's copies from --delete).
cd ~/sm-adviser-nuc-backup
scp .env config.yaml theses.yaml mini:/Users/sharath/sm-adviser/
ssh mini 'rm -f ~/sm-adviser/kite_token.json'   # don't trust another host's cached day-token
ssh mini 'chmod 600 /Users/sharath/sm-adviser/.env'
rsync -az reports_out/ mini:/Users/sharath/sm-adviser/reports_out/   # keeps the widget warm
scp msmtprc mini:/Users/sharath/.msmtprc && ssh mini 'chmod 600 ~/.msmtprc'
# The rescued .msmtprc carries a LINUX CA path and will fail with
#   "cannot set X509 trust file /etc/ssl/certs/ca-certificates.crt": Error while reading file
ssh mini 'cd ~ && cp -p .msmtprc .msmtprc.bak && \
  sed -i "" "s|^tls_trust_file .*|tls_trust_file /etc/ssl/cert.pem|" .msmtprc && chmod 600 .msmtprc*'
# NOTE: macOS's bundled rsync has no -s/--protect-args, so the space in "Application Support"
# gets split by the remote shell and the copy SILENTLY does nothing. Pipe a tar instead.
tar -C monitor-state -cf - . | ssh mini 'mkdir -p "$HOME/Library/Application Support/sm-adviser-monitor" \
  && tar -C "$HOME/Library/Application Support/sm-adviser-monitor" -xf -'
scp portfolio.dump mini:/Users/sharath/

# 2.3 alert.env now needs macOS paths. Edit the Mac's copy (the Mac is its source of truth —
#     see deploy/monitor/alert.env.example), then re-sync.
#       MSMTP_CONFIG=/Users/sharath/.msmtprc
#       STATE_DIR="/Users/sharath/Library/Application Support/sm-adviser-monitor"
#       SMA_ENV=/Users/sharath/sm-adviser/.env
#       WIDGET_JSON=/Users/sharath/sm-adviser/reports_out/widget.json
#       HOST_LABEL="Mac Mini (mini / <tailnet-ip>)"
$EDITOR deploy/monitor/alert.env && SMA_HOST=mini ./deploy/sync-to-server.sh
```

```bash
# 2.4 Build, restore the database, start.
ssh mini
cd ~/sm-adviser
docker compose build
docker compose up -d db
docker compose ps                        # wait for db -> healthy

docker exec -i sm-adviser-db pg_restore -U portfolio -d portfolio \
  --clean --if-exists --no-owner < ~/portfolio.dump

# Should report "already at head" — that's the proof the restore landed at the right schema.
docker compose --profile job run --rm migrate

docker compose up -d                     # db + api
curl -fsS localhost:8787/health          # -> {"status":"ok"}
```

```bash
# 2.5 Verify the history actually came across (compare against the NUC before you retire it).
TOKEN=$(grep '^WIDGET_API_TOKEN=' .env | cut -d= -f2-)
curl -fsS -H "Authorization: Bearer $TOKEN" localhost:8787/status
curl -fsS -H "Authorization: Bearer $TOKEN" localhost:8787/meta
docker exec sm-adviser-db psql -U portfolio -d portfolio -c \
  "select count(*) runs, min(run_date), max(run_date) from runs;"
```

```bash
# 2.6 One real end-to-end run (logs into Kite via TOTP, calls Claude).
docker compose --profile job run --rm morning-run
```
Expect a JSON summary with your holdings count, `recommendations`, `narrative: true`, and
`stock_pages`. `order_flow: 0` stays harmless. Then check `/report/latest` and `/widget.json`
against what the NUC last produced — same holdings, same bands (hysteresis proves the restored
history is being read).

```bash
# 2.7 Schedule it.
./deploy/macos/install-launchd.sh
launchctl list | grep sm-adviser

# Fire one out of schedule to prove the wrapper + PATH + Colima autostart path works:
launchctl kickstart -p gui/$(id -u)/com.sharath.sm-adviser.intraday
tail -20 ~/Library/Logs/sm-adviser/intraday-run.log
```

```bash
# 2.8 Prove the alerting path (it's the only thing that will tell you the mini went quiet).
printf 'migration test from the mini\n' | ./deploy/monitor/sma-alert.sh 'SM Adviser: mini test'
./deploy/monitor/sma-watchdog.sh && echo "watchdog clean (no mail = all checks pass)"
```

---

## Phase 3 — Inherit the tailnet name, cut the phone over ✅ *done 2026-09-25*

Confirmed working: the mini answers as `nuc-hadescanyon.taila98dab.ts.net` with a Let's Encrypt cert
valid to 24 Dec 2026, and the iOS app + widget refresh against it with **no reconfiguration at all** —
same URL, same token. The NUC's tailnet IP changed (100.119.98.88 → 100.76.133.106) but nothing
references the IP, only the MagicDNS name.

`tailscale serve` needed **no sudo** with the Homebrew daemon.

The iOS app stores the server URL + bearer token. Reusing the NUC's MagicDNS name means
**zero changes on the phone** — no re-auth, no widget re-add.

1. On the NUC: `sudo tailscale serve reset && sudo tailscale down && sudo tailscale logout`
2. Tailscale admin console → Machines → delete the NUC node (frees the name).
3. Same console → the mini → **Edit machine name** → `nuc-hadescanyon`, so the app's URL
   `https://nuc-hadescanyon.taila98dab.ts.net:8443` keeps resolving. (Cosmetically odd for a Mac;
   the alternative is re-entering the URL in the app.)
4. On the mini, re-issue the serve so the cert matches the new name:
   ```bash
   sudo tailscale serve reset
   sudo tailscale serve --bg --https=8443 8787
   tailscale cert "$(tailscale status --json | python3 -c 'import sys,json;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
   ```
5. **Verify from a PEER, never from the mini itself.** `tailscale serve` handles traffic from other
   tailnet nodes; a node connecting to its own tailnet address on the serve port gets a TCP
   connection that then hangs in the TLS handshake. That is expected, NOT a broken config — don't
   spend time debugging it (I did). What you *can* check locally:
   ```bash
   tailscale serve status     # -> https://<name>:8443 -> proxy http://127.0.0.1:8787
   curl -fsS localhost:8787/health
   # provision/inspect the cert explicitly (writes key material — use a temp dir and delete it):
   D=$(mktemp -d); cd "$D"; tailscale cert <name>; \
     openssl x509 -in <name>.crt -noout -subject -issuer -dates; cd /; rm -rf "$D"
   ```
   Then from the phone (on the tailnet) open `https://<old-name>.ts.net:8443/health` in Safari, and
   pull-to-refresh the app and long-press → reload the widget.

---

## Phase 4 — Reboot test, then retire the NUC

**Deferred 25 Sep** along with the OS update, since it requires a reboot. The cutover *works*
without it, but this test is what proves the stack comes back by itself — so treat retiring the NUC
before running it as carrying real risk, and keep the NUC available until it passes.

⚠️ Use `fdesetup authrestart`, **not** `sudo reboot`. With FileVault on, a plain remote reboot
strands the mini at the preboot unlock screen — no SSH, no Screen Sharing — until someone walks
over to it. `authrestart` stores the unlock key for exactly one boot, so it comes back by itself.

```bash
ssh -t mini 'sudo fdesetup authrestart'      # -t: it prompts for the password interactively
# wait ~90s, then — with nobody touching the mini:
ssh mini 'colima status && docker compose -f ~/sm-adviser/docker-compose.yml ps && \
          curl -fsS localhost:8787/health && launchctl list | grep sm-adviser'
```
All four must come back on their own. If they don't, `brew services start colima` isn't in effect
(or the LaunchAgents aren't bootstrapped) — fix that before retiring the NUC.

This proves the *planned*-reboot path. It cannot prove the unplanned one: after a power cut the
mini will sit at the preboot screen until someone types the password. That's the residual risk you
accepted by keeping FileVault on, and it's what the UPS and the dead-man's switch are for.

Then:
```bash
ssh NUC-HadesCanyon-Linux 'cd ~/sm-adviser && docker compose down'
ssh NUC-HadesCanyon-Linux 'sudo poweroff'
```
Keep `~/sm-adviser-nuc-backup` (and its NAS copy) for at least 30 days. Don't wipe the NUC's
disk until the mini has produced a week of clean morning runs.

---

## Ops after the move

Day-to-day commands live in **`deploy/macos/README.md`**. The systemd units in `deploy/` are kept
for anyone self-hosting on Linux, not used here.

## Deliberately deferred

Ordered by what the FileVault-on decision leaves exposed.

- **Multi-user instances** (`deploy/multiuser/`) — systemd-only, not ported. Confirmed unnecessary:
  `~/sma-instances/registry` was empty on 25 Sep.
- **Off-machine backup job** — a weekly `pg_dump` + config bundle to the NAS. Phase 0.6 does it
  once by hand; automating it is the real fix for "config.yaml lives on one disk".
- **UPS** — the highest-value hardening left, now that FileVault stays on: it stops a power cut
  from becoming a reboot (and therefore a manual unlock) at all.
- **Off-box dead-man's switch** (explicitly deferred 25 Sep, revisit after cutover) — the on-box
  watchdog dies with the machine, so a mini that is off or stuck at the FileVault preboot screen
  reports *nothing*. Until this exists, a stale widget is the only signal. Two candidates: a
  Synology Task Scheduler job curling `/health` on the LAN, or a healthchecks.io-style ping from
  the morning job (which also catches "the run silently didn't happen").
