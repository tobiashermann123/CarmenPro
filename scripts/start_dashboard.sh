#!/usr/bin/env bash
# Start the CarmenPro Streamlit dashboard
# Usage: bash scripts/start_dashboard.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
echo "Starting CarmenPro Dashboard at http://localhost:8501"
exec streamlit run dashboard/app.py \
    --server.port 8501 \
    --server.headless false \
    --browser.gatherUsageStats false
