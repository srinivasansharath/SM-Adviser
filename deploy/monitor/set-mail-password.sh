#!/usr/bin/env bash
# Interactively set the SMTP app password in ~/.msmtprc. Prompts silently; the password
# is never echoed, never stored in shell history, never in the repo. Run over SSH with -t:
#   ssh -t NUC-HadesCanyon-Linux '~/sm-adviser/deploy/monitor/set-mail-password.sh'
set -euo pipefail

CONF="$HOME/.msmtprc"
[ -f "$CONF" ] || { echo "ERROR: $CONF not found"; exit 1; }

read -rsp "Gmail/Workspace app password (input hidden): " P
echo
P="${P// /}"                       # strip the spaces Google shows in the 16-char code
[ -n "$P" ] || { echo "empty password — aborted, nothing changed"; exit 1; }

tmp="$(mktemp)"
# Replace the entire 'password' line, whatever it currently holds (placeholder or old value).
awk -v pw="$P" '/^password[[:space:]]/ {print "password       " pw; next} {print}' "$CONF" > "$tmp"
mv "$tmp" "$CONF"
chmod 600 "$CONF"

if grep -q "PASTE_16_CHAR" "$CONF"; then
  echo "WARN: placeholder still present — no 'password' line was matched. Check $CONF."
  exit 1
fi
echo "app password saved to $CONF (length: ${#P})"
