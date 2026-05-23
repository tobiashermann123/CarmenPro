#!/usr/bin/env bash
# Removes CarmenPro launchd agents.
set -euo pipefail

LAUNCH_DIR="$HOME/Library/LaunchAgents"

for label in com.carmenpro.daily com.carmenpro.weekly; do
    dest="$LAUNCH_DIR/$label.plist"
    launchctl unload "$dest" 2>/dev/null && echo "✓ Unloaded: $label" || echo "  Not loaded: $label"
    rm -f "$dest" && echo "  Removed: $dest"
done
