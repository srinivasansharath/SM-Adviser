#!/usr/bin/env bash
# Periodic health watchdog. Emails ONCE when a check breaks and ONCE when it recovers
# (state-tracked under STATE_DIR); silent otherwise. Run by sma-watchdog.timer.
set -uo pipefail   # intentionally no -e: each check handles its own failure
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$WIDGET_JSON") ) / 3600 ))
  if [ "$age_h" -gt "$STALE_HOURS" ]; then
    transition widget_fresh fail "widget.json is ${age_h}h old (> ${STALE_HOURS}h) — the daily run may have stopped"
  else
    transition widget_fresh ok ""
  fi
else
  transition widget_fresh fail "widget.json missing ($WIDGET_JSON)"
fi

# 5. Root disk usage
disk_pct=$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')
if [ "${disk_pct:-0}" -gt "$DISK_PCT_MAX" ]; then
  transition disk_space fail "Root filesystem ${disk_pct}% full (> ${DISK_PCT_MAX}%)"
else
  transition disk_space ok ""
fi

# --- One batched email per direction ---
if [ "${#breaks[@]}" -gt 0 ]; then
  {
    echo "The following SM Adviser check(s) started failing:"
    echo
    printf '  - %s\n' "${breaks[@]}"
    echo
    echo "Investigate on the NUC:"
    echo "  cd ~/sm-adviser && docker compose ps && docker compose logs --tail 50 api"
    echo "  journalctl -u sm-adviser-morning.service -n 50"
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
