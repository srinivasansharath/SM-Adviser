#!/usr/bin/env bash
# OnFailure handler for sm-adviser-morning.service — emails the failure with recent logs.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/alert.env"

LOGS="$(journalctl -u sm-adviser-morning.service -n 40 --no-pager 2>/dev/null | tail -40)"
{
  echo "The daily SM Adviser morning run FAILED."
  echo
  echo "The portfolio report + widget.json were NOT refreshed this run."
  echo
  echo "Last 40 log lines (sm-adviser-morning.service):"
  echo "--------------------------------------------------"
  echo "$LOGS"
  echo "--------------------------------------------------"
  echo
  echo "Re-run manually once fixed:"
  echo "  cd ~/sm-adviser && docker compose --profile job run --rm morning-run"
} | "$HERE/sma-alert.sh" "SM Adviser ALERT: daily morning run failed"
