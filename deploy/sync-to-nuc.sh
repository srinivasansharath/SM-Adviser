#!/usr/bin/env bash
# Push the repo (code + gitignored config/secrets) from this Mac to the NUC.
# The gitignored files (.env, config.yaml, theses.yaml, kite_token.json) are NOT on
# GitHub, so rsync — not git — is how they reach the server.
#
#   ./deploy/sync-to-nuc.sh            # sync code + config
#   ./deploy/sync-to-nuc.sh --restart  # sync, then rebuild + restart the API on the NUC
set -euo pipefail

NUC="${NUC_HOST:-NUC-HadesCanyon-Linux}"
DEST="${NUC_DEST:-/home/sharath/sm-adviser}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ssh "$NUC" "mkdir -p $DEST"

rsync -az --delete \
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
  "$REPO/" "$NUC:$DEST/"

echo "synced $REPO -> $NUC:$DEST"

if [[ "${1:-}" == "--restart" ]]; then
  ssh "$NUC" "cd $DEST && docker compose up -d --build api"
  echo "API rebuilt + restarted on $NUC"
fi
