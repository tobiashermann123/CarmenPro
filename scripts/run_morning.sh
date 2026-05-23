#!/usr/bin/env bash
# CarmenPro morning pipeline — runs daily at 09:45 ET via crontab.
# 1. Pull live prices + technicals → openbb_snapshots
# 2. Update action states + write daily brief
# 3. Sync to Google Sheet (CPSignals + CarmenPro tab)
#
# Logs to: /tmp/carmenpro_morning.log

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="/tmp/carmenpro_morning.log"
PYTHON="$(which python3)"

echo "========================================" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Morning pipeline start" >> "$LOG"

cd "$ROOT"

echo "--- Snapshot ---" >> "$LOG"
"$PYTHON" scripts/run_daily_snapshot.py >> "$LOG" 2>&1

echo "--- Sync ---" >> "$LOG"
"$PYTHON" scripts/sync_carmenpro_dashboard.py >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Done" >> "$LOG"
