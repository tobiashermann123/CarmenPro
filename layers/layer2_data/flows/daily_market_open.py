"""
Prefect flow: runs every trading day at 09:35 ET.
- Fetches EUR/USD rate
- Pulls OpenBB snapshots for all Tier 1 tickers
- Updates action states and flags rescores
- Writes daily brief to Supabase

No LLM calls — pure data and arithmetic.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from datetime import date

from prefect import flow, task, get_run_logger

from layers.layer2_data.fx import get_eur_usd
from layers.layer2_data.tier1_source import get_carmenpro_tickers
from layers.layer2_data.openbb_puller import pull_snapshot
from layers.layer2_data.price_monitor import update_action_state, flag_rescore_if_needed
from layers.layer3_storage.client import get_client


@task(retries=2, retry_delay_seconds=30, name="fetch-eur-usd")
def fetch_fx_rate() -> float:
    rate = get_eur_usd(_date=date.today())
    get_run_logger().info(f"EUR/USD: {rate}")
    return rate


@task(retries=2, retry_delay_seconds=60, name="pull-openbb-snapshot")
def snapshot_ticker(ticker: str, eur_usd: float) -> dict:
    log = get_run_logger()
    try:
        row = pull_snapshot(ticker, eur_usd=eur_usd)
        log.info(f"{ticker}: ${row.get('price_usd')} / €{row.get('price_eur')}")
        return row
    except Exception as exc:
        log.warning(f"{ticker}: snapshot failed — {exc}")
        return {}


@task(name="update-action-states")
def update_states(snapshots: list[dict]) -> list[dict]:
    log     = get_run_logger()
    actions = []
    for snap in snapshots:
        ticker = snap.get("ticker")
        price  = snap.get("price_usd")
        if not ticker or not price:
            continue
        state = update_action_state(ticker, price)
        log.info(f"{ticker}: {state}")
        actions.append({"ticker": ticker, "state": state, "price_usd": price})
    return actions


@task(name="write-daily-brief")
def write_daily_brief(actions: list[dict]) -> None:
    buy_now      = [a for a in actions if a["state"] == "BUY_NOW"]
    limit_queued = [a for a in actions if a["state"] == "LIMIT_QUEUED"]
    rescore_due  = [a for a in actions if a.get("rescore_required")]

    client = get_client()
    client.table("system_state").upsert({
        "key":   "daily_brief",
        "value": {
            "date":           date.today().isoformat(),
            "buy_now":        buy_now,
            "limit_queued":   limit_queued,
            "rescore_due":    rescore_due,
            "total_tier1":    len(actions),
        },
        "updated_at": date.today().isoformat(),
    }, on_conflict="key").execute()

    get_run_logger().info(
        f"Daily brief: {len(buy_now)} BUY_NOW | "
        f"{len(limit_queued)} LIMIT_QUEUED | "
        f"{len(rescore_due)} RESCORE_DUE"
    )


@flow(
    name="daily-market-open",
    description="Morning data pull for all Tier 1 tickers. No LLM. Runs 09:35 ET daily.",
)
def daily_market_open_flow():
    eur_usd   = fetch_fx_rate()
    tickers   = get_carmenpro_tickers()

    snapshots = [snapshot_ticker(t, eur_usd) for t in tickers]
    actions   = update_states(snapshots)
    write_daily_brief(actions)


if __name__ == "__main__":
    daily_market_open_flow()
