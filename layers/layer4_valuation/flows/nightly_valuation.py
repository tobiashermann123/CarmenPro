"""
Prefect flow: runs nightly at 02:30 IST (after US market close).

For each Tier 1 ticker:
  1. Pull annual financial statements (yfinance → raw_fundamentals)
  2. Compute DCF intrinsic value + margin of safety
  3. Compute Piotroski F-Score
  4. Update the most recent trade_signal row with valuation results
  5. Write daily brief to system_state

Skips crypto tickers (no FCF-based valuation applicable).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from datetime import date, datetime, timezone

from prefect import flow, task, get_run_logger

from layers.layer2_data.fx import get_eur_usd
from layers.layer2_data.tier1_source import get_tier1_tickers
from layers.layer3_storage.client import get_client
from layers.layer4_valuation.financial_puller import pull_financials, CRYPTO_TICKERS
from layers.layer4_valuation.dcf import compute_dcf
from layers.layer4_valuation.piotroski import compute_piotroski


@task(retries=2, retry_delay_seconds=60, name="pull-and-value-ticker")
def value_ticker(ticker: str, eur_usd: float) -> dict:
    log = get_run_logger()

    if ticker.upper() in CRYPTO_TICKERS:
        log.info(f"{ticker}: crypto — skipping DCF")
        return {"ticker": ticker, "skipped": True, "reason": "crypto"}

    financials = pull_financials(ticker)
    if not financials or not financials["years"]:
        log.warning(f"{ticker}: no financial data — skipping")
        return {"ticker": ticker, "skipped": True, "reason": "no_data"}

    years = financials["years"]        # newest → oldest
    latest = years[0]
    prior  = years[1] if len(years) > 1 else None

    # Current price from Supabase (latest openbb snapshot)
    current_price = _get_latest_price(ticker)
    if current_price is None:
        log.warning(f"{ticker}: no price snapshot — skipping DCF")
        return {"ticker": ticker, "skipped": True, "reason": "no_price"}

    # Build FCF history oldest → newest for DCF
    fcf_history = [y["_fcf"] for y in reversed(years) if y.get("_fcf") is not None]

    # DCF
    dcf_result = compute_dcf(
        fcf_history=fcf_history,
        net_debt=latest.get("_net_debt") or 0.0,
        shares_outstanding=financials["shares_outstanding"] or 0,
        current_price=current_price,
        beta=financials["beta"],
        eur_usd=eur_usd,
    )

    # Piotroski (requires current + prior year)
    # Normalise keys: piotroski.py expects cfo/total_assets/total_debt/current_ratio
    piotroski_result = None
    if prior:
        piotroski_result = compute_piotroski(
            _piotroski_row(latest),
            _piotroski_row(prior),
        )

    result = {
        "ticker":          ticker,
        "skipped":         False,
        "current_price":   current_price,
        "dcf":             dcf_result,
        "piotroski":       piotroski_result,
    }

    # Persist to trade_signals (update most recent row)
    _update_trade_signal(ticker, dcf_result, piotroski_result, eur_usd)

    log.info(
        f"{ticker}: IV=${dcf_result['intrinsic_value_usd'] if dcf_result else 'N/A'} "
        f"MoS={dcf_result['margin_of_safety_pct'] if dcf_result else 'N/A'}% "
        f"Piotroski={piotroski_result['piotroski_score'] if piotroski_result else 'N/A'}"
    )
    return result


@task(name="write-valuation-brief")
def write_valuation_brief(results: list[dict]) -> None:
    valued   = [r for r in results if not r.get("skipped")]
    skipped  = [r for r in results if r.get("skipped")]
    buy_zone = [
        r for r in valued
        if r.get("dcf") and r["dcf"]["margin_of_safety_pct"] >= 30
    ]
    overval  = [
        r for r in valued
        if r.get("dcf") and r["dcf"]["margin_of_safety_pct"] < -10
    ]

    client = get_client()
    client.table("system_state").upsert({
        "key":   "valuation_brief",
        "value": {
            "date":                   date.today().isoformat(),
            "total_valued":           len(valued),
            "skipped":                [r["ticker"] for r in skipped],
            "in_buy_zone":            [r["ticker"] for r in buy_zone],
            "overvalued":             [r["ticker"] for r in overval],
            "detail": {
                r["ticker"]: {
                    "intrinsic_value_usd":  r["dcf"]["intrinsic_value_usd"] if r.get("dcf") else None,
                    "margin_of_safety_pct": r["dcf"]["margin_of_safety_pct"] if r.get("dcf") else None,
                    "piotroski_score":      r["piotroski"]["piotroski_score"] if r.get("piotroski") else None,
                }
                for r in valued
            },
        },
        "updated_at": date.today().isoformat(),
    }, on_conflict="key").execute()


@flow(
    name="nightly-valuation",
    description="Nightly DCF + Piotroski scoring for all CarmenPro watchlist tickers. Runs after US market close.",
)
def nightly_valuation_flow(tickers: list[str] | None = None):
    eur_usd = get_eur_usd(_date=date.today())
    if tickers is None:
        tickers = get_carmenpro_tickers()
    results = [value_ticker(t, eur_usd) for t in tickers]
    write_valuation_brief(results)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _piotroski_row(y: dict) -> dict:
    """Map financial_puller dict keys to the names piotroski.py expects."""
    return {
        "roa":                 y.get("roa"),
        "cfo":                 y.get("_cfo"),
        "total_assets":        y.get("total_assets"),
        "total_debt":          y.get("total_debt"),
        "current_ratio":       y.get("current_ratio"),
        "shares_outstanding":  y.get("shares_outstanding"),
        "gross_margin":        y.get("gross_margin"),
        "asset_turnover":      y.get("asset_turnover"),
        "net_income":          y.get("net_income"),
    }

def _get_latest_price(ticker: str) -> float | None:
    """Fetch most recent price from trade_signals (populated by /trade score)."""
    client = get_client()
    rows = (
        client.table("trade_signals")
        .select("price_usd")
        .eq("ticker", ticker)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    if rows.data:
        return rows.data[0].get("price_usd")
    return None


def get_carmenpro_tickers() -> list[str]:
    """Distinct tickers from trade_signals — our active watchlist."""
    client = get_client()
    rows = (
        client.table("trade_signals")
        .select("ticker")
        .order("generated_at", desc=True)
        .execute()
    )
    seen: set[str] = set()
    result = []
    for r in rows.data:
        t = r.get("ticker", "").upper()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _update_trade_signal(
    ticker: str,
    dcf: dict | None,
    piotroski: dict | None,
    eur_usd: float,
) -> None:
    """Update the most recent trade_signal row for this ticker with valuation data."""
    client = get_client()

    # Get the latest row id
    row = (
        client.table("trade_signals")
        .select("id")
        .eq("ticker", ticker)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not row.data:
        return

    row_id = row.data[0]["id"]
    update = {"valuation_updated_at": datetime.now(timezone.utc).isoformat()}

    if dcf:
        update.update({
            "intrinsic_value_usd":  dcf["intrinsic_value_usd"],
            "intrinsic_value_eur":  dcf.get("intrinsic_value_eur"),
            "margin_of_safety_pct": dcf["margin_of_safety_pct"],
            "dcf_wacc":             dcf["dcf_wacc"],
            "dcf_fcf_growth_rate":  dcf["dcf_fcf_growth_rate"],
        })
    if piotroski:
        update["piotroski_score"] = piotroski["piotroski_score"]

    client.table("trade_signals").update(update).eq("id", row_id).execute()


if __name__ == "__main__":
    nightly_valuation_flow()
