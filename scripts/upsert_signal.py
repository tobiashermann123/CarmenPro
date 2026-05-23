"""
Upserts a trade signal row to Supabase from a JSON payload.
Used by /trade score skill to write directly to DB without a markdown file.

Usage:
    echo '<json>' | python scripts/upsert_signal.py
    python scripts/upsert_signal.py --json '<json>'

Expected JSON schema:
{
  "ticker":             "NVDA",
  "composite_score":    73,
  "grade":              "A",
  "signal":             "Buy",
  "technical_score":    68,
  "fundamental_score":  87,
  "sentiment_score":    72,
  "risk_score":         52,
  "thesis_score":       81,
  "price_usd":          215.50,
  "entry_low_usd":      212.0,
  "entry_high_usd":     219.0,
  "stop_usd":           203.0,
  "target1_usd":        236.54,
  "target2_usd":        255.0,
  "risk_reward":        2.5,
  "position_size_pct":  18.5,
  "position_size_eur":  185.0,
  "tier":               1,
  "notes_json": {
    "technical":    "2-sentence summary",
    "fundamental":  "2-sentence summary",
    "sentiment":    "2-sentence summary",
    "risk":         "2-sentence summary",
    "thesis":       "2-sentence summary",
    "bull_catalyst":"1-sentence bull case",
    "bear_risk":    "1-sentence bear risk"
  },
  "sub_scores_json": {
    "technical":   {"trend": 14, "momentum": 14, "volume": 14, "pattern": 13, "rel_strength": 13},
    "fundamental": {"valuation": 16, "growth": 20, "profitability": 18, "health": 18, "moat": 15},
    "sentiment":   {"news": 16, "social": 14, "analysts": 16, "institutional": 14, "insider_short": 12},
    "risk":        {"volatility": 10, "downside": 10, "macro": 12, "liquidity": 12, "rr": 8},
    "thesis":      {"catalyst": 17, "timing": 16, "asymmetry": 16, "edge": 16, "conviction": 16}
  }
}

All EUR fields are computed automatically from the live EUR/USD rate.
action_state is derived from signal + price vs entry zone.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer2_data.fx import get_eur_usd, usd_to_eur
from layers.layer3_storage.client import get_client


SIGNAL_TO_ACTION = {
    "Strong Buy":      None,  # resolved by price check below
    "Buy":             None,
    "Hold/Accumulate": "WAIT",
    "Neutral":         "HOLD",
    "Caution":         "AVOID",
    "Avoid":           "AVOID",
}


def _derive_action_state(signal: str, price_usd: float | None, entry_low: float | None, entry_high: float | None) -> str:
    base = SIGNAL_TO_ACTION.get(signal)
    if base is not None:
        return base
    # Buy / Strong Buy — determine BUY_NOW vs LIMIT_QUEUED from price vs entry zone
    if price_usd and entry_high:
        if price_usd <= entry_high:
            return "BUY_NOW"
        return "LIMIT_QUEUED"
    return "LIMIT_QUEUED"


def build_row(payload: dict, eur_usd: float) -> dict:
    def eur(usd_val):
        return usd_to_eur(usd_val, eur_usd) if usd_val is not None else None

    price_usd = payload.get("price_usd")
    entry_low  = payload.get("entry_low_usd")
    entry_high = payload.get("entry_high_usd")

    row = {
        "ticker":             payload["ticker"].upper(),
        "generated_at":       datetime.now(timezone.utc).isoformat(),
        "source":             "score",
        "eur_usd":            eur_usd,
        "tier":               payload.get("tier", 1),
        "rescore_required":   False,
        # Scores
        "composite_score":    payload.get("composite_score"),
        "grade":              payload.get("grade"),
        "signal":             payload.get("signal"),
        "technical_score":    payload.get("technical_score"),
        "fundamental_score":  payload.get("fundamental_score"),
        "sentiment_score":    payload.get("sentiment_score"),
        "risk_score":         payload.get("risk_score"),
        "thesis_score":       payload.get("thesis_score"),
        # Price levels USD
        "price_usd":          price_usd,
        "entry_low_usd":      entry_low,
        "entry_high_usd":     entry_high,
        "stop_usd":           payload.get("stop_usd"),
        "target1_usd":        payload.get("target1_usd"),
        "target2_usd":        payload.get("target2_usd"),
        # Price levels EUR (auto-computed)
        "price_eur":          eur(price_usd),
        "entry_low_eur":      eur(entry_low),
        "entry_high_eur":     eur(entry_high),
        "stop_eur":           eur(payload.get("stop_usd")),
        "target1_eur":        eur(payload.get("target1_usd")),
        "target2_eur":        eur(payload.get("target2_usd")),
        # Sizing
        "risk_reward":        payload.get("risk_reward"),
        "position_size_pct":  payload.get("position_size_pct"),
        "position_size_eur":  payload.get("position_size_eur"),
        # Notes and sub-scores
        "notes_json":         payload.get("notes_json"),
        "sub_scores_json":    payload.get("sub_scores_json"),
    }

    row["action_state"] = _derive_action_state(
        row.get("signal", ""),
        price_usd,
        entry_low,
        entry_high,
    )

    # Remove None values so Supabase uses column defaults
    return {k: v for k, v in row.items() if v is not None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_str", help="JSON payload string")
    args = parser.parse_args()

    if args.json_str:
        raw = args.json_str
    else:
        raw = sys.stdin.read().strip()

    if not raw:
        print("ERROR: no JSON payload provided", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    eur_usd = get_eur_usd()
    row     = build_row(payload, eur_usd)

    client = get_client()
    client.table("trade_signals").insert(row).execute()

    ticker = row["ticker"]
    score  = row.get("composite_score", "?")
    signal = row.get("signal", "?")
    action = row.get("action_state", "?")
    print(f"  ✓ {ticker}: {signal} ({score}/100) → {action} | EUR/USD {eur_usd:.4f}")


if __name__ == "__main__":
    main()
