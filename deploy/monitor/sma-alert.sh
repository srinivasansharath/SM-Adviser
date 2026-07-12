#!/usr/bin/env bash
# Compose and send one alert email via msmtp.
#   printf 'body...' | sma-alert.sh "Subject line"
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/alert.env"

SUBJECT="${1:?usage: sma-alert.sh SUBJECT  (body on stdin)}"
BODY="$(cat)"

{
  printf 'To: %s\n' "$ALERT_TO"
  printf 'From: SM Adviser <%s>\n' "$ALERT_FROM"
  printf 'Subject: %s\n' "$SUBJECT"
  printf 'Content-Type: text/plain; charset=UTF-8\n'
  printf '\n'
  printf '%s\n' "$BODY"
  printf '\n-- \nSM Adviser monitor · %s · %s\n' "$HOST_LABEL" "$(date '+%F %T %Z')"
} | msmtp -C "$MSMTP_CONFIG" "$ALERT_TO"
