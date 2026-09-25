#!/usr/bin/env bash
# Push the repo (code + gitignored config/secrets) from this Mac to the server.
# The gitignored files (.env, config.yaml, theses.yaml, kite_token.json) are NOT on
# GitHub, so rsync — not git — is how they reach the server.
#
#   ./deploy/sync-to-server.sh            # sync code + config
#   ./deploy/sync-to-server.sh --restart  # sync, then rebuild + restart the API on the server
#
# Host/path come from the environment so this works for any server:
#   SMA_HOST=mini SMA_DEST=/Users/sharath/sm-adviser ./deploy/sync-to-server.sh
#
# deploy/monitor/alert.env IS pushed from here (it's gitignored, so git can't hold it and the
# Mac is its only durable home). Keep the Mac's copy matching the server's OS paths — the
# tracked template is deploy/monitor/alert.env.example.
#
# SAFETY: --delete once wiped config.yaml off the server because that file lived ONLY there
# (it's gitignored, and this Mac never had a copy). Server-side state is now PROTECTED from
# deletion, and anything deleted/overwritten is kept in .rsync-backup/.
set -euo pipefail

HOST="${SMA_HOST:-mini}"
DEST="${SMA_DEST:-/Users/sharath/sm-adviser}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ssh "$HOST" "mkdir -p $DEST"

rsync -az --delete \
  --backup --backup-dir=".rsync-backup/$(date +%Y%m%d-%H%M%S)" \
  --filter='P config.yaml' \
  --filter='P .env' \
  --filter='P theses.yaml' \
  --filter='P kite_token.json' \
  --filter='P data/**' \
  --filter='P reports_out/**' \
  --filter='P .rsync-backup/**' \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache/' \
  --exclude 'portfolio_agent.egg-info/' \
  --exclude 'ios/' \
  --exclude 'share/' \
  --exclude '*.docx' \
  --exclude '.DS_Store' \
  --exclude 'data/*.db' \
  --exclude 'reports_out/*' \
  "$REPO/" "$HOST:$DEST/"

echo "synced $REPO -> $HOST:$DEST"

if [[ "${1:-}" == "--restart" ]]; then
  ssh "$HOST" "cd $DEST && docker compose up -d --build api"
  echo "API rebuilt + restarted on $HOST"
fi
