#!/usr/bin/env bash
# Tear down a user instance: stop containers, drop Tailscale serve, unregister. Keeps their
# database + instance dir by default (pass --purge to delete those too).
set -euo pipefail

NAME="${1:?usage: remove-user.sh <name> [--purge]}"
NAME="$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
PURGE=""; [ "${2:-}" = "--purge" ] && PURGE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTANCES="${SMA_INSTANCES:-$HOME/sma-instances}"
DIR="$INSTANCES/$NAME"
COMPOSE_FILE="$REPO/deploy/multiuser/docker-compose.user.yml"
[ -f "$DIR/.env" ] || { echo "no such instance: $NAME"; exit 1; }

TS_PORT="$(grep -E '^TS_PORT=' "$DIR/.env" | cut -d= -f2)"

docker compose -p "sma-$NAME" --env-file "$DIR/.env" -f "$COMPOSE_FILE" down 2>/dev/null || true
[ -n "$TS_PORT" ] && sudo tailscale serve --https="$TS_PORT" off 2>/dev/null || true
# unregister (grep may output nothing when removing the last entry — don't let that skip the mv)
if [ -f "$INSTANCES/registry" ]; then
  grep -vxF "$NAME" "$INSTANCES/registry" > "$INSTANCES/registry.tmp" || true
  mv "$INSTANCES/registry.tmp" "$INSTANCES/registry"
fi

if [ -n "$PURGE" ]; then
  docker exec sm-adviser-db dropdb -U portfolio --if-exists "sma_$NAME" || true
  rm -rf "$DIR"
  echo "purged $NAME (database + state removed)"
else
  echo "stopped $NAME. Database sma_$NAME and $DIR kept (use --purge to delete)."
fi
