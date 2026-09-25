#!/usr/bin/env bash
# Install (or remove) the SM-Adviser launchd jobs — the macOS counterpart of
#   sudo cp deploy/*.{service,timer} /etc/systemd/system/ && systemctl enable --now ...
#
#   ./deploy/macos/install-launchd.sh              # install + start all four jobs
#   ./deploy/macos/install-launchd.sh --uninstall   # stop + remove them
#
# These are LaunchAgents (~/Library/LaunchAgents), so they run in your login session — which is
# what Colima needs anyway. On this host FileVault is on, so that session is reached by unlocking
# at the preboot screen (which macOS passes through to a login). A reboot therefore needs a human
# unless you use `sudo fdesetup authrestart`; see deploy/macos/README.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/sm-adviser"
DOMAIN="gui/$(id -u)"

JOBS=(morning intraday weekly watchdog)

if [[ "${1:-}" == "--uninstall" ]]; then
  for j in "${JOBS[@]}"; do
    label="com.sharath.sm-adviser.$j"
    launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
    rm -f "$AGENTS/$label.plist"
    echo "removed $label"
  done
  echo "done — logs left in $LOGS"
  exit 0
fi

mkdir -p "$AGENTS" "$LOGS"

for j in "${JOBS[@]}"; do
  label="com.sharath.sm-adviser.$j"
  src="$HERE/$label.plist"
  dst="$AGENTS/$label.plist"

  # Templated paths -> this machine's real ones.
  sed -e "s|__SMA_REPO__|$REPO|g" -e "s|__SMA_HOME__|$HOME|g" "$src" >"$dst"
  plutil -lint "$dst" >/dev/null

  # bootout first so re-running this script is idempotent (bootstrap fails if loaded).
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$dst"
  launchctl enable "$DOMAIN/$label"
  echo "installed $label"
done

echo
echo "loaded jobs:"
launchctl list | grep 'sm-adviser' || echo "  (none — check $LOGS)"
echo
echo "next scheduled fire times are not introspectable in launchd; verify by log:"
echo "  tail -f $LOGS/morning-run.log"
echo "run one now, out of schedule:"
echo "  launchctl kickstart -p $DOMAIN/com.sharath.sm-adviser.morning"
