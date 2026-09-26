#!/usr/bin/env bash
# Emit an off-box heartbeat: a small file on the NAS saying "this job ran, and how it went".
#
#   sma-heartbeat.sh <name> <ok|fail> [detail]
#
# WHY off-box. The watchdog (sma-watchdog.sh) can only report problems it is alive to observe, and
# on macOS it is a *user* LaunchAgent — it dies with the login session. On 2026-09-26 the Mac Mini
# rebooted, sat at the FileVault login window with the whole stack down, and the watchdog reported
# nothing: no mail, every state file still "ok". A ~5 minute outage passed in silence.
#
# So the alarm lives elsewhere, and it is FAIL-SAFE: silence must trigger it. This script only ever
# says "I'm alive"; the NAS (nas-deadman.sh, on a separate UPS line) raises the alarm when the
# saying stops. If the Mini is off, asleep, stuck at the login window, or its agents were never
# armed, nothing is written and the NAS notices. An active prober would instead fail silent when
# the prober died — the very bug being fixed.
#
# WHY SSH AND NOT THE SMB MOUNT. The obvious route is writing to /Volumes/home. It works from an
# interactive shell and FAILS FROM LAUNCHD with "Operation not permitted" — macOS does not grant
# launchd-spawned jobs access to the user's network volumes. That is the worst possible failure
# mode for a monitor: green in manual testing, silently never firing in production. Verified on
# 2026-09-26: the same script wrote fine over SSH and wrote nothing under `launchctl kickstart`.
# SSH has no such restriction, and it also drops the dependency on the mount being present.
#
# Deliberately never fails the caller: a heartbeat that breaks the morning run is worse than none.
set -uo pipefail

NAME="${1:?usage: sma-heartbeat.sh <name> <ok|fail> [detail]}"
STATUS="${2:-ok}"
DETAIL="${3:-}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/alert.env" ] && . "$HERE/alert.env" 2>/dev/null

HB_SSH_HOST="${HEARTBEAT_SSH_HOST:-sharath@192.168.1.62}"
HB_SSH_KEY="${HEARTBEAT_SSH_KEY:-$HOME/.ssh/id_ed25519_nas_heartbeat}"
HB_DIR="${HEARTBEAT_REMOTE_DIR:-/volume1/homes/sharath/sm-adviser-heartbeat}"

now_epoch="$(date +%s)"
now_iso="$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)"
payload="$(printf '{"name":"%s","status":"%s","at":"%s","epoch":%s,"host":"%s","detail":"%s"}' \
  "$NAME" "$STATUS" "$now_iso" "$now_epoch" "$(hostname -s)" "${DETAIL//\"/}")"

# Write to a temp name then mv, so the NAS never reads a half-written file.
if printf '%s\n' "$payload" | ssh -i "$HB_SSH_KEY" \
     -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
     "$HB_SSH_HOST" "mkdir -p '$HB_DIR' && cat > '$HB_DIR/.$NAME.tmp' && mv -f '$HB_DIR/.$NAME.tmp' '$HB_DIR/$NAME.json'" \
     >/dev/null 2>&1; then
  exit 0
fi

# Losing the heartbeat is itself worth knowing about locally — the NAS will also notice the silence.
echo "heartbeat: could not publish '$NAME' to $HB_SSH_HOST:$HB_DIR" >&2
exit 0
