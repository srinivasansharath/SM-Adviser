#!/usr/bin/env bash
# Run one job (morning-run | intraday-run) for every registered user instance. Driven by the
# looping systemd timers. Failures for one user don't stop the others.
set -uo pipefail

JOB="${1:?usage: run-all.sh <morning-run|intraday-run>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTANCES="${SMA_INSTANCES:-$HOME/sma-instances}"
COMPOSE_FILE="$REPO/deploy/multiuser/docker-compose.user.yml"
REGISTRY="$INSTANCES/registry"

[ -f "$REGISTRY" ] || { echo "no instances registered"; exit 0; }

while read -r name; do
  [ -z "$name" ] && continue
  d="$INSTANCES/$name"
  [ -f "$d/.env" ] || { echo "skip $name (no .env)"; continue; }
  echo "[$(date '+%F %T')] $JOB -> $name"
  docker compose -p "sma-$name" --env-file "$d/.env" -f "$COMPOSE_FILE" \
    --profile job run --rm "$JOB" || echo "  !! $name: $JOB failed"
done < "$REGISTRY"
