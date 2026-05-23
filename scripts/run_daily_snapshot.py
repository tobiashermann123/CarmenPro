"""
Daily snapshot pull for all CarmenPro watchlist tickers.
Prefect-free — designed to be called from cron or run_morning.sh.

What it does:
  1. Fetches EUR/USD rate
  2. Pulls price + technicals from yfinance for each ticker → openbb_snapshots
  3. Updates action_state on the latest trade_signal row
  4. Flags rescore_required if price moved >5% since last score
  5. Writes daily_brief to system_state

Usage:
    python scripts/run_daily_snapshot.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer2_data.fx import get_eur_usd
from layers.layer2_data.tier1_source import get_carmenpro_tickers
from layers.layer2_data.openbb_puller import pull_snapshot
from layers.layer2_data.price_monitor import update_action_state, flag_rescore_if_needed
from layers.layer3_storage.client import get_client


def write_daily_brief(actions: list[dict]) -> None:
    buy_now      = [a for a in actions if a["state"] == "BUY_NOW"]
    limit_queued = [a for a in actions if a["state"] == "LIMIT_QUEUED"]
    rescore_due  = [a for a in actions if a.get("rescore_required")]

    client = get_client()
    client.table("system_state").upsert({
        "key":   "daily_brief",
        "value": {
            "date":         date.today().isoformat(),
            "buy_now":      buy_now,
            "limit_queued": limit_queued,
            "rescore_due":  rescore_due,
            "total_scored": len(actions),
        },
        "updated_at": date.today().isoformat(),
    }, on_conflict="key").execute()


def main():
    print(f"CarmenPro Daily Snapshot — {date.today().isoformat()}")

    eur_usd = get_eur_usd(_date=date.today())
    print(f"EUR/USD: {eur_usd:.4f}")

    tickers = get_carmenpro_tickers()
    print(f"Tickers: {tickers}\n")

    actions = []
    for ticker in tickers:
        try:
            snap  = pull_snapshot(ticker, eur_usd=eur_usd)
            price = snap.get("price_usd")
            state = update_action_state(ticker, price) if price else "NO_PRICE"
            rescore = flag_rescore_if_needed(ticker, price) if price else False

            tag = ""
            if state == "BUY_NOW":
                tag = "  ← BUY_NOW"
            elif state == "LIMIT_QUEUED":
                tag = "  ← LIMIT_QUEUED"
            elif rescore:
                tag = "  ← RESCORE"

            price_str = f"${price:.2f}" if price else "N/A"
            print(f"  ✓ {ticker:6s}  {price_str:10s}  →  {state}{tag}")
            actions.append({"ticker": ticker, "state": state,
                            "price_usd": price, "rescore_required": rescore})
        except Exception as exc:
            print(f"  ✗ {ticker}: {exc}")

    write_daily_brief(actions)

    buy_now      = [a for a in actions if a["state"] == "BUY_NOW"]
    limit_queued = [a for a in actions if a["state"] == "LIMIT_QUEUED"]
    rescore_due  = [a for a in actions if a.get("rescore_required")]

    print(f"\n  Daily brief written.")
    print(f"  BUY_NOW: {[a['ticker'] for a in buy_now]}")
    print(f"  LIMIT_QUEUED: {[a['ticker'] for a in limit_queued]}")
    print(f"  RESCORE_DUE: {[a['ticker'] for a in rescore_due]}")


if __name__ == "__main__":
    main()
