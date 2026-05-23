"""
Daily snapshot pull for all CarmenPro watchlist tickers.
Prefect-free — designed to be called from cron or GitHub Actions.

What it does:
  1. Fetches EUR/USD rate
  2. Pulls price + technicals from yfinance for each ticker → openbb_snapshots
  3. Updates action_state on the latest trade_signal row
  4. Adds tickers to rescore_queue when: no signal, price moved >5%,
     earnings within 7 days, or score is stale for its grade
  5. Writes daily_brief to system_state

Usage:
    python scripts/run_daily_snapshot.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from layers.layer2_data.fx import get_eur_usd
from layers.layer2_data.tier1_source import get_carmenpro_tickers
from layers.layer2_data.openbb_puller import pull_snapshot
from layers.layer2_data.price_monitor import update_action_state, get_latest_signal
from layers.layer3_storage.client import get_client
from layers.layer3_storage.rescore_queue import enqueue, staleness_priority


def _check_earnings_soon(ticker: str) -> bool:
    """Returns True if ticker has earnings within 7 days."""
    try:
        result = (
            get_client().table("earnings_calendar")
            .select("days_away")
            .eq("ticker", ticker.upper())
            .limit(1)
            .execute()
        )
        if result.data:
            days = result.data[0].get("days_away")
            return days is not None and int(days) <= 7
    except Exception:
        pass
    return False


def _populate_queue(ticker: str, price: float | None, signal: dict | None) -> str:
    """
    Enqueues ticker for rescore if warranted. Returns a tag string for logging.
    Priority 1 = urgent, 2 = soon, 3 = normal staleness.
    """
    if signal is None:
        enqueue(ticker, 1, "no_signal")
        return "NO_SIGNAL→q(p1)"

    # Price moved >5% since last score
    snapshot_price = signal.get("price_usd")
    if price and snapshot_price:
        change_pct = abs(price - snapshot_price) / snapshot_price
        if change_pct > 0.05:
            enqueue(ticker, 1, f"price_move_{change_pct:.1%}")
            return f"PRICE_MOVE→q(p1)"

    # Earnings approaching
    if _check_earnings_soon(ticker):
        enqueue(ticker, 1, "earnings_7d")
        return "EARNINGS→q(p1)"

    # Grade-tiered staleness
    priority, reason = staleness_priority(signal.get("grade"), signal.get("generated_at"))
    if priority is not None:
        enqueue(ticker, priority, reason)
        return f"STALE→q(p{priority})"

    return ""


def write_daily_brief(actions: list[dict]) -> None:
    buy_now      = [a for a in actions if a["state"] == "BUY_NOW"]
    limit_queued = [a for a in actions if a["state"] == "LIMIT_QUEUED"]
    queued       = [a for a in actions if a.get("queued")]

    get_client().table("system_state").upsert({
        "key":   "daily_brief",
        "value": {
            "date":         date.today().isoformat(),
            "buy_now":      buy_now,
            "limit_queued": limit_queued,
            "rescore_due":  queued,
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
            snap      = pull_snapshot(ticker, eur_usd=eur_usd)
            price     = snap.get("price_usd")
            signal    = get_latest_signal(ticker)
            state     = update_action_state(ticker, price) if price else "NO_PRICE"
            queue_tag = _populate_queue(ticker, price, signal)

            tag = ""
            if state == "BUY_NOW":         tag = "  ← BUY_NOW"
            elif state == "LIMIT_QUEUED":  tag = "  ← LIMIT_QUEUED"
            elif queue_tag:                tag = f"  ← {queue_tag}"

            price_str = f"${price:.2f}" if price else "N/A"
            print(f"  ✓ {ticker:6s}  {price_str:10s}  →  {state}{tag}")
            actions.append({
                "ticker":    ticker,
                "state":     state,
                "price_usd": price,
                "queued":    bool(queue_tag),
            })
        except Exception as exc:
            print(f"  ✗ {ticker}: {exc}")

    write_daily_brief(actions)

    buy_now      = [a for a in actions if a["state"] == "BUY_NOW"]
    limit_queued = [a for a in actions if a["state"] == "LIMIT_QUEUED"]
    queued       = [a for a in actions if a.get("queued")]

    print(f"\n  Daily brief written.")
    print(f"  BUY_NOW:             {[a['ticker'] for a in buy_now]}")
    print(f"  LIMIT_QUEUED:        {[a['ticker'] for a in limit_queued]}")
    print(f"  QUEUED_FOR_RESCORE:  {[a['ticker'] for a in queued]}")


if __name__ == "__main__":
    main()
