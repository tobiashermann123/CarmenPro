"""
Pushes latest trade_signals from Supabase into the CarmenAnalyst tab
of the CarmenBot Google Sheet.

Run after ingesting new analyses:
    python scripts/sync_signals_to_sheet.py

Or add to ingest_all_analyses.py workflow (auto-syncs after each ingest).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "CarmenBot"))  # hands.py lives here

from layers.layer3_storage.client import get_client


def main():
    client = get_client()

    # Pull latest signal per ticker (highest score if multiple)
    result = (
        client.table("trade_signals")
        .select("*")
        .order("generated_at", desc=True)
        .execute()
    )

    # Deduplicate — keep most recent per ticker
    seen = {}
    for row in result.data:
        t = row["ticker"]
        if t not in seen:
            seen[t] = row

    signals = list(seen.values())
    print(f"Syncing {len(signals)} signals to CarmenAnalyst tab...")

    try:
        import hands
        hands.update_carmenanalyst(signals)
    except ImportError:
        print("Could not import CarmenBot/hands.py — is CarmenBot at ../CarmenBot/?")
        sys.exit(1)


if __name__ == "__main__":
    main()
