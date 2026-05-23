"""
Syncs the CarmenPro master dashboard tab in the CarmenBot Google Sheet.

Pulls from Supabase:
  - trade_signals  (latest per ticker, with valuation columns)
  - system_state   (daily_brief)

Then calls hands.update_carmenpro() to write the CarmenPro tab.

Run manually or add to your daily workflow after /trade score:
    python scripts/sync_carmenpro_dashboard.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "CarmenBot"))

from layers.layer3_storage.client import get_client


def get_latest_signals() -> list[dict]:
    """One row per ticker — the most recent signal with valuation overlay."""
    client = get_client()
    result = (
        client.table("trade_signals")
        .select("*")
        .order("generated_at", desc=True)
        .execute()
    )
    seen: dict[str, dict] = {}
    for row in result.data:
        t = row.get("ticker", "")
        if t and t not in seen:
            seen[t] = row
    return list(seen.values())


def get_daily_brief() -> dict | None:
    client = get_client()
    result = (
        client.table("system_state")
        .select("value")
        .eq("key", "daily_brief")
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0].get("value")
    return None


def main():
    dashboard_url = os.environ.get("DASHBOARD_URL", "http://localhost:8501")

    signals = get_latest_signals()
    brief   = get_daily_brief()

    print(f"Syncing {len(signals)} signals to CarmenPro tab...")
    if brief:
        print(f"Daily brief: {brief.get('date')} — "
              f"{len(brief.get('buy_now', []))} BUY_NOW | "
              f"{len(brief.get('limit_queued', []))} LIMIT_QUEUED")

    try:
        import hands
        hands.update_carmenpro(signals, brief=brief, dashboard_url=dashboard_url)
    except ImportError:
        print("Could not import CarmenBot/hands.py — is CarmenBot at ../CarmenBot/?")
        sys.exit(1)


if __name__ == "__main__":
    main()
