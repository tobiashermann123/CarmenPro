"""
One-time backfill: score a list of tickers that have no CarmenPro signal yet.

Bypasses the MAX_TICKERS daily cap — use only for initial backfills, not
regular operation (the queue in auto_rescore.py handles that).

Processes in batches of BATCH_SIZE with a short pause between batches to
stay within Tavily rate limits (free tier: 1,000 searches/month).

Cost estimate per ticker: 3 Tavily searches + ~$0.001 Anthropic (Haiku).
46 tickers ≈ 138 Tavily searches, ~$0.05 total — effectively free.

Usage:
    python scripts/backfill_scores.py NVDA AAPL ASML ...   # explicit list
    python scripts/backfill_scores.py --all                # all REVIEW tickers
"""
from __future__ import annotations
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from layers.layer2_data.fx import get_eur_usd
from layers.layer3_storage.client import get_client
from scripts.auto_rescore import rescore_ticker

BATCH_SIZE  = 10   # tickers per batch
BATCH_PAUSE = 20   # seconds between batches (Tavily rate limit buffer)


def _get_review_tickers() -> list[str]:
    """Return tickers present in the watchlist but with no trade_signal row."""
    from layers.layer2_data.tier1_source import get_carmenpro_tickers
    watchlist = set(get_carmenpro_tickers())

    result = (
        get_client().table("trade_signals")
        .select("ticker")
        .execute()
    )
    scored = {r["ticker"].upper() for r in (result.data or [])}
    return sorted(watchlist - scored)


def _get_price(ticker: str, fallback: float = 100.0) -> float:
    """Best-effort price from openbb_snapshots, falls back to trade_signals, then 100."""
    client = get_client()

    snap = (
        client.table("openbb_snapshots")
        .select("price_usd")
        .eq("ticker", ticker)
        .order("snapped_at", desc=True)
        .limit(1)
        .execute()
    )
    if snap.data and snap.data[0].get("price_usd"):
        return float(snap.data[0]["price_usd"])

    sig = (
        client.table("trade_signals")
        .select("price_usd")
        .eq("ticker", ticker)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    if sig.data and sig.data[0].get("price_usd"):
        return float(sig.data[0]["price_usd"])

    return fallback


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        tickers = _get_review_tickers()
        if not tickers:
            print("No unscored tickers found — all watchlist tickers already have signals.")
            return
        print(f"Found {len(tickers)} unscored tickers: {tickers}")
    elif len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
    else:
        print("Usage: python scripts/backfill_scores.py NVDA AAPL ...  OR  --all")
        sys.exit(1)

    eur_usd = get_eur_usd(_date=date.today())
    total   = len(tickers)
    done    = 0
    failed  = []

    print(f"\nBackfill — {date.today().isoformat()} | EUR/USD {eur_usd:.4f}")
    print(f"Tickers ({total}): {tickers}")
    print(f"Batch size: {BATCH_SIZE} | Pause between batches: {BATCH_PAUSE}s\n")

    for i in range(0, total, BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"── Batch {batch_num}/{total_batches}: {batch} ──")

        for ticker in batch:
            price = _get_price(ticker)
            row = rescore_ticker(ticker, price, eur_usd)
            if row:
                done += 1
            else:
                failed.append(ticker)

        if i + BATCH_SIZE < total:
            print(f"  Pausing {BATCH_PAUSE}s before next batch…\n")
            time.sleep(BATCH_PAUSE)

    print(f"\n{'─' * 50}")
    print(f"Backfill complete: {done}/{total} scored.")
    if failed:
        print(f"Failed ({len(failed)}): {failed}")
        print("Re-run with: python scripts/backfill_scores.py " + " ".join(failed))


if __name__ == "__main__":
    main()
