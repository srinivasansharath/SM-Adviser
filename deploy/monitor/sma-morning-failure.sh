#!/usr/bin/env bash
# Failure handler for the daily/weekly job — emails the failure with recent logs.
#
#   Linux : invoked by systemd `OnFailure=sma-morning-alert.service` (no args).
#   macOS : invoked by deploy/macos/sma-job.sh as `sma-morning-failure.sh <job> <logfile>`
#           (launchd has no OnFailure=, so the wrapper calls this itself).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/alert.env"

JOB="${1:-morning-run}"
JOB_LOG="${2:-}"

# journalctl on Linux; the launchd wrapper's log file on macOS.
if command -v journalctl >/dev/null 2>&1; then
  LOGS="$(journalctl -u sm-adviser-morning.service -n 40 --no-pager 2>/dev/null | tail -40)"
elif [ -n "$JOB_LOG" ] && [ -f "$JOB_LOG" ]; then
  LOGS="$(tail -40 "$JOB_LOG")"
else
  LOGS="(no log source found — checked journalctl and '${JOB_LOG:-<none>}')"
fi

{
  echo "The SM Adviser '$JOB' job FAILED."
  echo
  if [ "$JOB" = "weekly-screen" ]; then
    echo "The weekly buy-candidate shortlist was NOT refreshed this run."
  else
    echo "The portfolio report + widget.json were NOT refreshed this run."
  fi
  echo
  echo "Last 40 log lines:"
  echo "--------------------------------------------------"
  echo "$LOGS"
  echo "--------------------------------------------------"
  echo
  echo "Re-run manually once fixed:"
  echo "  cd ~/sm-adviser && docker compose --profile job run --rm $JOB"
} | "$HERE/sma-alert.sh" "SM Adviser ALERT: $JOB failed"
