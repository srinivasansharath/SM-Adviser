#!/usr/bin/env bash
# launchd job wrapper — the macOS counterpart of the systemd *.service units.
#
#   sma-job.sh morning-run      # full daily pipeline
#   sma-job.sh intraday-run     # light price refresh (self-gates to market hours)
#   sma-job.sh weekly-screen    # weekly new-stock screener
#
# Why a wrapper and not a bare `docker compose` in the plist:
#   1. launchd hands jobs a minimal PATH — Homebrew (and therefore Colima's docker) is absent.
#   2. Colima's VM may not be up yet; we start it rather than failing the run.
#   3. launchd has no `OnFailure=`, so failure alerting has to live here.
#   4. The intraday tick fires every 15 min all day; gating here avoids ~70 pointless
#      container starts outside market hours.
set -uo pipefail

JOB="${1:?usage: sma-job.sh <morning-run|intraday-run|weekly-screen>}"
REPO="${SMA_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
LOG_DIR="${SMA_LOG_DIR:-$HOME/Library/Logs/sm-adviser}"
LOG="$LOG_DIR/$JOB.log"
mkdir -p "$LOG_DIR"

# Homebrew first: that's where colima + docker live on Apple Silicon.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

log() { printf '[%s] %s\n' "$(date '+%F %T %Z')" "$*" >>"$LOG"; }

# --- 1. Market-hours gate (intraday only) ---------------------------------------
# The job itself gates precisely to 09:15-15:30 IST; this is the cheap outer guard so we
# don't spin a container just to have it no-op. Deliberately wider (09:00-15:45).
if [ "$JOB" = "intraday-run" ]; then
  dow="$(date +%u)"                        # 1=Mon .. 7=Sun
  hhmm=$((10#$(date +%H%M)))               # 10# so "0900" isn't read as octal
  if [ "$dow" -gt 5 ] || [ "$hhmm" -lt 900 ] || [ "$hhmm" -gt 1545 ]; then
    exit 0
  fi
fi

# --- 2. Make sure the Docker VM is up -------------------------------------------
# `brew services start colima` normally has it running from login; this is the backstop
# (e.g. first tick after an unattended reboot, or the VM died).
if command -v colima >/dev/null 2>&1; then
  if ! colima status >/dev/null 2>&1; then
    log "colima not running — starting it"
    if ! colima start >>"$LOG" 2>&1; then
      log "FATAL: colima start failed; skipping $JOB"
      "$REPO/deploy/monitor/sma-heartbeat.sh" "$JOB" fail "colima start failed" 2>>"$LOG"
      "$REPO/deploy/monitor/sma-morning-failure.sh" "$JOB" "$LOG" 2>/dev/null \
        || log "(failure alert could not be sent)"
      exit 1
    fi
  fi
fi

# --- 3. Run the job -------------------------------------------------------------
cd "$REPO" || { log "FATAL: repo $REPO missing"; exit 1; }
log "start $JOB"
docker compose --profile job run --rm "$JOB" >>"$LOG" 2>&1
rc=$?
log "end $JOB (exit $rc)"

# --- 3b. Off-box heartbeat (see deploy/monitor/sma-heartbeat.sh for why) ----------
# The intraday tick is excluded: it is gated to market hours, so its silence is normal and
# would produce daily false alarms. morning-run and weekly-screen are the meaningful ones.
if [ "$JOB" != "intraday-run" ]; then
  if [ "$rc" -eq 0 ]; then
    "$REPO/deploy/monitor/sma-heartbeat.sh" "$JOB" ok "exit 0" 2>>"$LOG"
  else
    "$REPO/deploy/monitor/sma-heartbeat.sh" "$JOB" fail "exit $rc" 2>>"$LOG"
  fi
fi

# --- 4. Alert on failure (systemd's OnFailure= equivalent) ----------------------
# Intraday is deliberately silent: a missed tick just means prices lag until the next one,
# and alerting every 15 min would drown the signal. Same rationale as the Linux units.
if [ "$rc" -ne 0 ] && [ "$JOB" != "intraday-run" ]; then
  "$REPO/deploy/monitor/sma-morning-failure.sh" "$JOB" "$LOG" 2>/dev/null \
    || log "(failure alert could not be sent)"
fi

exit "$rc"
