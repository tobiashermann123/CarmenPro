"""
Prefect flow: runs every Sunday at 18:00 local time.
- Reads Tier 3 universe from Google Sheet
- Pulls lightweight OpenBB snapshots for all tickers
- Writes snapshots to Supabase
- Flags tickers worth promoting to Tier 1 (price in entry zone of a prior signal)
- Does NOT run CarmenAnalyst — that is done manually in Claude Code

No LLM calls. Pure data refresh.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from datetime import date

from prefect import flow, task, get_run_logger

from layers.layer2_data.fx import get_eur_usd
from layers.layer2_data.tier3_source import get_tier3_tickers
from layers.layer2_data.openbb_puller import pull_snapshot
from layers.layer2_data.price_monitor import check_action_state
from layers.layer3_storage.client import get_client


@task(retries=2, name="fetch-tier3-tickers")
def fetch_tier3() -> list[str]:
    tickers = get_tier3_tickers()
    get_run_logger().info(f"Tier 3 universe: {len(tickers)} tickers")
    return tickers


@task(retries=2, retry_delay_seconds=60, name="snapshot-tier3-ticker")
def snapshot_tier3_ticker(ticker: str, eur_usd: float) -> dict:
    try:
        return pull_snapshot(ticker, eur_usd=eur_usd)
    except Exception as exc:
        get_run_logger().warning(f"{ticker}: {exc}")
        return {}


@task(name="identify-tier1-candidates")
def identify_candidates(snapshots: list[dict]) -> list[str]:
    """
    Flags Tier 3 tickers whose current price is inside or near
    an entry zone from a prior trade_signals row.
    These are worth running /trade analyze on next session.
    """
    candidates = []
    for snap in snapshots:
        ticker = snap.get("ticker")
        price  = snap.get("price_usd")
        if not ticker or not price:
            continue
        state = check_action_state(ticker, price)
        if state in ("BUY_NOW", "LIMIT_QUEUED"):
            candidates.append(ticker)

    log = get_run_logger()
    log.info(f"Tier 1 candidates from Tier 3 screen: {candidates}")
    return candidates


@task(name="write-tier3-brief")
def write_tier3_brief(candidates: list[str], total: int) -> None:
    client = get_client()
    client.table("system_state").upsert({
        "key":   "tier3_weekly_brief",
        "value": {
            "date":            date.today().isoformat(),
            "total_screened":  total,
            "tier1_candidates": candidates,
            "action":          "Run /trade analyze on candidates in Claude Code",
        },
        "updated_at": date.today().isoformat(),
    }, on_conflict="key").execute()


@flow(
    name="weekly-tier3-screen",
    description="Sunday refresh of Tier 3 Google Sheet universe. No LLM.",
)
def weekly_tier3_screen_flow():
    eur_usd    = get_eur_usd(_date=date.today())
    tickers    = fetch_tier3()
    snapshots  = [snapshot_tier3_ticker(t, eur_usd) for t in tickers]
    candidates = identify_candidates(snapshots)
    write_tier3_brief(candidates, total=len(tickers))


if __name__ == "__main__":
    weekly_tier3_screen_flow()
