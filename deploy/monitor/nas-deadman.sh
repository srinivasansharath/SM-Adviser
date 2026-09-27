#!/usr/bin/env bash
# DEAD-MAN'S SWITCH — runs ON THE SYNOLOGY, not on the server it watches.
#
# The Mac Mini writes heartbeat files to the NAS (deploy/monitor/sma-heartbeat.sh). This script
# raises the alarm when they stop arriving or report failure. It lives on the NAS because the NAS
# is independently powered (separate UPS line from the office) — so it survives the exact events
# that take the Mini down, which is the whole point.
#
# WHY this exists: on 2026-09-26 the Mini rebooted and sat at the FileVault login window with
# Colima, Docker, the API and all four launchd agents down. The on-box watchdog is itself a user
# LaunchAgent, so it died too and reported nothing — no mail, every state file still "ok". Silence
# looked identical to health. This inverts that: silence IS the alarm.
#
# DELIVERY: sends its own email via sma_sendmail.py, and ALSO exits non-zero.
#
# It used to rely solely on DSM's "send run details when the script terminates abnormally". On
# 2026-09-26 that was configured, the task ran, the script exited non-zero — and no mail arrived.
# DSM's scheduler logs need root to diagnose, and an alarm must not depend on a delivery path that
# cannot be tested. Sending directly means the send can be verified end to end (and it was: Gmail
# accepted the message). The non-zero exit is kept so DSM remains a second channel if it ever
# starts working; a duplicate alert is vastly better than none.
#
# Credentials live in ~/.sma-deadman-mail.env (chmod 600), never in this repo.
#
# Thresholds are deliberately tolerant: one missed heartbeat must not page anyone.
#
# RATE LIMITING. DSM runs this every 20 min, and it emails whenever the script exits non-zero. A
# naive implementation therefore sends ~30 mails during an overnight outage. So it tracks state:
# it exits non-zero on the TRANSITION into a fault and then stays quiet, re-reminding only every
# REMIND_HOURS while the fault persists. Recovery cannot be announced through this channel (exit 0
# means DSM sends nothing), so it is simply recorded in the state file.
set -uo pipefail

STATE_DIR="${DEADMAN_STATE_DIR:-/volume1/homes/sharath/.sm-adviser-deadman}"
REMIND_HOURS="${REMIND_HOURS:-6}"
mkdir -p "$STATE_DIR" 2>/dev/null

DIR="${HEARTBEAT_DIR:-/volume1/homes/sharath/sm-adviser-heartbeat}"

# watchdog beats every 20 min -> 60 min tolerates two misses.
WATCHDOG_MAX_MIN="${WATCHDOG_MAX_MIN:-60}"
# morning-run is Mon-Fri, so the gap across a weekend is ~72h. 90h clears it, matching
# STALE_HOURS in the on-box watchdog.
MORNING_MAX_HOURS="${MORNING_MAX_HOURS:-90}"
# weekly-screen runs Sunday 07:00. 9 days tolerates one missed week without crying wolf, while
# still catching a screener that has quietly stopped (the shortlist would otherwise just go stale
# and nobody would notice).
WEEKLY_MAX_HOURS="${WEEKLY_MAX_HOURS:-216}"

problems=()

now="$(date +%s)"

read_field() {  # read_field <file> <key>
  python3 - "$1" "$2" <<'PY' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1]) as fh:
        print(json.load(fh).get(sys.argv[2], ""))
except Exception:
    pass
PY
}

check() {  # check <name> <max_age_seconds> <human_window>
  local name="$1" max="$2" window="$3"
  local f="$DIR/$name.json"

  if [ ! -f "$f" ]; then
    problems+=("$name: NO heartbeat file at all ($f) — the Mini has never reported, or the file was removed")
    return
  fi

  local mtime age status detail at
  mtime="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
  age=$(( now - mtime ))
  status="$(read_field "$f" status)"
  detail="$(read_field "$f" detail)"
  at="$(read_field "$f" at)"

  if [ "$age" -gt "$max" ]; then
    problems+=("$name: LAST SEEN $(( age / 60 )) min ago (limit $window) — last said '${status:-?}' at ${at:-unknown}. The Mini is off, asleep, stuck at the login window, or its launchd agents are not armed.")
  elif [ "$status" != "ok" ]; then
    problems+=("$name: heartbeat is current but reports status='${status}' (${detail:-no detail}) at ${at:-unknown} — the host is alive but unhealthy.")
  fi
}

check watchdog      $(( WATCHDOG_MAX_MIN * 60 ))    "${WATCHDOG_MAX_MIN}m"
check morning-run   $(( MORNING_MAX_HOURS * 3600 )) "${MORNING_MAX_HOURS}h"
check weekly-screen $(( WEEKLY_MAX_HOURS * 3600 ))  "${WEEKLY_MAX_HOURS}h"

STATE="$STATE_DIR/last_alert"

if [ "${#problems[@]}" -eq 0 ]; then
  # Healthy. Clear the fault state so the NEXT fault alerts immediately rather than being
  # swallowed by a stale reminder window.
  if [ -f "$STATE" ]; then
    echo "recovered $(date '+%F %T %Z')" > "$STATE_DIR/last_recovery" 2>/dev/null
    rm -f "$STATE" 2>/dev/null
  fi
  exit 0          # silent = healthy; DSM sends nothing
fi

# Faulty. Alert on the transition, then at most once every REMIND_HOURS.
last_alert=0
[ -f "$STATE" ] && last_alert="$(cat "$STATE" 2>/dev/null || echo 0)"
case "$last_alert" in ''|*[!0-9]*) last_alert=0 ;; esac
since=$(( now - last_alert ))

if [ "$last_alert" -gt 0 ] && [ "$since" -lt $(( REMIND_HOURS * 3600 )) ]; then
  # Already reported and still inside the quiet window — stay silent so DSM sends nothing.
  exit 0
fi
echo "$now" > "$STATE" 2>/dev/null

if [ "$last_alert" -gt 0 ]; then
  SUBJECT="SM Adviser ALERT (reminder): still tripped after $(( since / 3600 ))h"
  HEADER="SM Adviser dead-man's switch STILL TRIPPED on $(hostname) at $(date '+%F %T %Z')
(reminder — first reported $(( since / 3600 ))h ago; repeats every ${REMIND_HOURS}h until fixed)"
else
  SUBJECT="SM Adviser ALERT: the Mac Mini stopped reporting in"
  HEADER="SM Adviser dead-man's switch tripped on $(hostname) at $(date '+%F %T %Z')."
fi

{
echo "$HEADER"
echo
printf '  - %s\n' "${problems[@]}"
echo
echo "The Mac Mini stopped reporting in. Most likely causes, in order:"
echo "  1. It rebooted and is waiting at the FileVault login window — nothing starts until"
echo "     someone logs in. Screen Sharing to 192.168.1.40 (port 5900) reaches that screen."
echo "  2. Colima is not running, so Docker and the API are down:"
echo "       ssh mini 'colima status && docker compose -f ~/sm-adviser/docker-compose.yml ps'"
echo "  3. The launchd agents are not armed:"
echo "       ssh mini 'launchctl list | grep sm-adviser'   # expect 4"
echo "  4. The NAS SMB mount on the Mini dropped, so heartbeats cannot be written even though"
echo "     the Mini is fine. Check: ssh mini 'ls /Volumes/home >/dev/null && echo mounted'"
echo
echo "Heartbeat directory on this NAS: $DIR"
ls -la "$DIR" 2>/dev/null | sed 's/^/  /'
} > "$STATE_DIR/last_report.txt"
cat "$STATE_DIR/last_report.txt"      # DSM still sees the report on stdout

# Send it ourselves rather than trusting DSM (see DELIVERY above).
SENDER="${SENDMAIL_BIN:-$HOME/sma_sendmail.py}"
if [ -x "$SENDER" ]; then
  if python3 "$SENDER" "$SUBJECT" < "$STATE_DIR/last_report.txt" >>"$STATE_DIR/send.log" 2>&1; then
    echo "(alert emailed)" >> "$STATE_DIR/send.log"
  else
    echo "ALERT COULD NOT BE EMAILED — see $STATE_DIR/send.log" >&2
  fi
else
  echo "no sender at $SENDER — relying on DSM notification only" >&2
fi

exit 1
