"""
Run DCF + Piotroski valuation for the CarmenPro watchlist without Prefect.

Usage:
    python scripts/run_valuation.py               # all tickers in trade_signals
    python scripts/run_valuation.py NVDA TSM META # specific tickers only

Populates trade_signals.intrinsic_value_usd / _eur, margin_of_safety_pct,
piotroski_score, dcf_wacc, dcf_fcf_growth_rate, valuation_updated_at.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer2_data.fx import get_eur_usd
from layers.layer3_storage.client import get_client
from layers.layer4_valuation.financial_puller import pull_financials, CRYPTO_TICKERS
from layers.layer4_valuation.dcf import compute_dcf
from layers.layer4_valuation.piotroski import compute_piotroski


def get_watchlist() -> list[str]:
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


def get_price(ticker: str) -> float | None:
    """Prefer openbb_snapshots (updated daily); fall back to trade_signals."""
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
        return snap.data[0]["price_usd"]
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


def update_signal(ticker: str, dcf: dict | None, piotroski: dict | None) -> None:
    client = get_client()
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
    try:
        client.table("trade_signals").update(update).eq("id", row.data[0]["id"]).execute()
    except Exception as exc:
        print(f"[run_valuation] {ticker}: signal update failed — {exc}")


def _piotroski_row(y: dict) -> dict:
    return {
        "roa":                y.get("roa"),
        "cfo":                y.get("_cfo"),
        "total_assets":       y.get("total_assets"),
        "total_debt":         y.get("total_debt"),
        "current_ratio":      y.get("current_ratio"),
        "shares_outstanding": y.get("shares_outstanding"),
        "gross_margin":       y.get("gross_margin"),
        "asset_turnover":     y.get("asset_turnover"),
        "net_income":         y.get("net_income"),
    }


def run(tickers: list[str], eur_usd: float) -> None:
    results = []

    for ticker in tickers:
        if ticker in CRYPTO_TICKERS:
            print(f"  {ticker}: crypto — skipping DCF")
            results.append({"ticker": ticker, "skip": "crypto"})
            continue

        price = get_price(ticker)
        if price is None:
            print(f"  {ticker}: no price in trade_signals — skipping")
            results.append({"ticker": ticker, "skip": "no_price"})
            continue

        financials = pull_financials(ticker)
        if not financials or not financials["years"]:
            print(f"  {ticker}: no financial data — skipping")
            results.append({"ticker": ticker, "skip": "no_data"})
            continue

        years = financials["years"]
        latest = years[0]
        prior  = years[1] if len(years) > 1 else None

        fcf_history = [y["_fcf"] for y in reversed(years) if y.get("_fcf") is not None]

        dcf = compute_dcf(
            fcf_history=fcf_history,
            net_debt=latest.get("_net_debt") or 0.0,
            shares_outstanding=financials["shares_outstanding"] or 0,
            current_price=price,
            beta=financials["beta"],
            eur_usd=eur_usd,
        )

        piotroski = None
        if prior:
            piotroski = compute_piotroski(_piotroski_row(latest), _piotroski_row(prior))

        update_signal(ticker, dcf, piotroski)

        iv    = f"${dcf['intrinsic_value_usd']:.2f} (€{dcf['intrinsic_value_eur']:.2f})" if dcf else "N/A"
        mos   = f"{dcf['margin_of_safety_pct']:+.1f}%" if dcf else "N/A"
        pf    = str(piotroski["piotroski_score"]) if piotroski else "N/A"
        wacc  = f"{dcf['dcf_wacc']:.1f}%" if dcf else "N/A"
        grow  = f"{dcf['dcf_fcf_growth_rate']:+.1f}%" if dcf else "N/A"

        print(f"  ✓ {ticker:6s}  IV {iv:30s}  MoS {mos:8s}  Piotroski {pf}  WACC {wacc}  FCF growth {grow}")
        results.append({"ticker": ticker, "dcf": dcf, "piotroski": piotroski})

    # Summary
    valued  = [r for r in results if r.get("dcf")]
    buy_zone = [r for r in valued if r["dcf"]["margin_of_safety_pct"] >= 30]
    overval  = [r for r in valued if r["dcf"]["margin_of_safety_pct"] < -10]
    skipped  = [r for r in results if r.get("skip")]

    print()
    print(f"  Valued: {len(valued)}  |  Buy zone (MoS ≥30%): {[r['ticker'] for r in buy_zone]}  "
          f"|  Overvalued (MoS <-10%): {[r['ticker'] for r in overval]}  "
          f"|  Skipped: {[r['ticker'] for r in skipped]}")


def main():
    tickers = [t.upper() for t in sys.argv[1:]] if len(sys.argv) > 1 else get_watchlist()

    print(f"CarmenPro Valuation — {date.today().isoformat()}")
    print(f"Tickers: {tickers}")
    print(f"EUR/USD: ", end="", flush=True)

    eur_usd = get_eur_usd(_date=date.today())
    print(f"{eur_usd:.4f}")
    print()

    run(tickers, eur_usd)


if __name__ == "__main__":
    main()
