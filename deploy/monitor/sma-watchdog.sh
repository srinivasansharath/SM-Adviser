#!/usr/bin/env bash
# Periodic health watchdog. Emails ONCE when a check breaks and ONCE when it recovers
# (state-tracked under STATE_DIR); silent otherwise. Run by sma-watchdog.timer.
set -uo pipefail   # intentionally no -e: each check handles its own failure
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# launchd (macOS) gives a minimal PATH — docker, colima and msmtp live under Homebrew.
# Harmless on Linux, where these dirs simply don't exist.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# shellcheck source=/dev/null
source "$HERE/alert.env"
mkdir -p "$STATE_DIR"

breaks=()
recovers=()

# transition <name> <ok|fail> <failure-detail>
transition() {
  local name="$1" status="$2" detail="$3"
  local sf="$STATE_DIR/$name.state"
  local prev="ok"; [ -f "$sf" ] && prev="$(cat "$sf")"
  if [ "$status" = "fail" ]; then
    [ "$prev" != "fail" ] && breaks+=("$detail")
    echo "fail" > "$sf"
  else
    [ "$prev" = "fail" ] && recovers+=("$name")
    echo "ok" > "$sf"
  fi
}

# 1. API /health
if curl -fsS -m 8 "$API_URL" 2>/dev/null | grep -q '"status"'; then
  transition api_health ok ""
else
  transition api_health fail "API /health not responding ($API_URL)"
fi

# 2. Postgres ready
if docker exec "$DB_CONTAINER" pg_isready -U portfolio -d portfolio >/dev/null 2>&1; then
  transition db_health ok ""
else
  transition db_health fail "Postgres container '$DB_CONTAINER' not accepting connections"
fi

# 3. API container running
if [ "$(docker inspect -f '{{.State.Running}}' "$API_CONTAINER" 2>/dev/null)" = "true" ]; then
  transition api_container ok ""
else
  transition api_container fail "API container '$API_CONTAINER' is not running"
fi

# 4. widget.json freshness (backstop for a silently-stopped daily timer)
if [ -f "$WIDGET_JSON" ]; then
  mtime="$(stat -f %m "$WIDGET_JSON" 2>/dev/null || stat -c %Y "$WIDGET_JSON" 2>/dev/null)"
  age_h=$(( ( $(date +%s) - ${mtime:-0} ) / 3600 ))
  if [ "$age_h" -gt "$STALE_HOURS" ]; then
    transition widget_fresh fail "widget.json is ${age_h}h old (> ${STALE_HOURS}h) — the daily run may have stopped"
  else
    transition widget_fresh ok ""
  fi
else
  transition widget_fresh fail "widget.json missing ($WIDGET_JSON)"
fi

# 5. Disk headroom — measured as absolute free space, not percent-full.
#    The Mac Mini is a desktop that legitimately stores a large photo library, so sitting at
#    ~93% full is normal and permanent there. What actually matters is whether Colima's growing
#    disk image, Postgres and the logs still have room. A percentage threshold would alert
#    forever on a big disk and stay silent on a small one; free GiB is the signal that scales.
#    (DISK_PCT_MAX is superseded and no longer read.)
free_kb=$(df -Pk / 2>/dev/null | awk 'NR==2 {print $4}')
free_gb=$(( ${free_kb:-0} / 1048576 ))
if [ "$free_gb" -lt "${DISK_FREE_GB_MIN:-15}" ]; then
  transition disk_space fail "Only ${free_gb} GiB free on / (floor is ${DISK_FREE_GB_MIN:-15} GiB)"
else
  transition disk_space ok ""
fi

# 6. App health (authed /status): rolls up both jobs' external-API health, freshness (did the
#    daily/weekly run happen?), and the LLM budget into one `issues` list. Any issue -> one alert.
TOKEN=""
[ -f "$SMA_ENV" ] && TOKEN="$(grep -E '^WIDGET_API_TOKEN=' "$SMA_ENV" | tail -1 | cut -d= -f2- | tr -d '"'\'' \t\r')"
status_json=""
if [ -n "$TOKEN" ]; then
  status_json="$(curl -fsS -m 8 -H "Authorization: Bearer $TOKEN" "$STATUS_URL" 2>/dev/null)"
fi

if [ -z "$status_json" ]; then
  # Couldn't read /status (API down is already covered by check 1; only alert if API itself is up).
  :
else
  # JSON goes in via env (the heredoc already owns stdin, so we can't pipe it in).
  issues="$(STATUS_JSON="$status_json" python3 - <<'PY'
import json, os
try:
    d = json.loads(os.environ.get("STATUS_JSON", ""))
except Exception:
    print("PARSE_FAIL"); raise SystemExit(0)
print("\n  - ".join(d.get("issues") or []))
PY
)"
  if [ "$issues" = "PARSE_FAIL" ]; then
    :  # malformed response; don't spam
  elif [ -n "$issues" ]; then
    transition sma_health fail "SM Adviser health issues:"$'\n'"  - $issues"
  else
    transition sma_health ok ""
  fi
fi

# --- Off-box heartbeat -------------------------------------------------------------
# Runs every 20 min, so its absence is what tells the NAS this host has gone quiet — the case
# this watchdog structurally cannot report, because it dies with the login session.
# Status reflects the checks above: any break => fail, so the NAS can distinguish
# "host is dead" (no file / stale) from "host is alive but unhealthy" (status=fail).
if [ "${#breaks[@]}" -gt 0 ]; then
  "$HERE/sma-heartbeat.sh" watchdog fail "${#breaks[@]} check(s) failing" 2>/dev/null
else
  "$HERE/sma-heartbeat.sh" watchdog ok "all checks pass" 2>/dev/null
fi

# --- One batched email per direction ---
if [ "${#breaks[@]}" -gt 0 ]; then
  {
    echo "The following SM Adviser check(s) started failing:"
    echo
    printf '  - %s\n' "${breaks[@]}"
    echo
    echo "Investigate on the server:"
    echo "  cd ~/sm-adviser && docker compose ps && docker compose logs --tail 50 api"
    if command -v journalctl >/dev/null 2>&1; then
      echo "  journalctl -u sm-adviser-morning.service -n 50"
    else
      echo "  tail -50 ~/Library/Logs/sm-adviser/morning-run.log"
    fi
  } | "$HERE/sma-alert.sh" "SM Adviser ALERT: ${#breaks[@]} issue(s) detected"
fi

if [ "${#recovers[@]}" -gt 0 ]; then
  {
    echo "The following SM Adviser check(s) have recovered:"
    echo
    printf '  - %s\n' "${recovers[@]}"
  } | "$HERE/sma-alert.sh" "SM Adviser: recovered (${#recovers[@]})"
fi

exit 0
