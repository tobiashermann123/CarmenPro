#!/usr/bin/env bash
# Installs CarmenPro launchd agents for daily and weekly flows.
# Run once: bash scripts/setup_schedules.sh
set -euo pipefail

PLIST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../infrastructure/launchd" && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs"

mkdir -p "$LAUNCH_DIR" "$LOG_DIR"

for plist in "$PLIST_DIR"/*.plist; do
    label=$(basename "$plist" .plist)
    dest="$LAUNCH_DIR/$label.plist"

    # Unload if already loaded
    launchctl unload "$dest" 2>/dev/null || true

    cp "$plist" "$dest"
    launchctl load "$dest"
    echo "✓ Loaded: $label"
done

echo ""
echo "Schedules active:"
echo "  Daily market open    — weekdays 14:35 IST (09:35 ET)"
echo "  Weekly Tier 3 screen — Sunday 18:00 IST"
echo "  Nightly valuation    — daily 02:30 IST (after US market close)"
echo ""
echo "Logs: $LOG_DIR"
echo "To uninstall: bash scripts/uninstall_schedules.sh"
