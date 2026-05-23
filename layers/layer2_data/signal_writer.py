"""
Parses a TRADE-ANALYSIS-<TICKER>.md file written by CarmenAnalyst
and upserts a structured row into trade_signals.

Called manually after each /trade analyze session in Claude Code:
    python -c "from layers.layer2_data.signal_writer import ingest_analysis_file; ingest_analysis_file('TRADE-ANALYSIS-NVDA.md')"

Or batch:
    python scripts/ingest_all_analyses.py
"""
from __future__ import annotations
import re
import os
from pathlib import Path
from datetime import datetime, timezone

from layers.layer2_data.fx import get_eur_usd, usd_to_eur
from layers.layer3_storage.client import get_client


def ingest_analysis_file(filepath: str | Path, tier: int = 1) -> dict:
    """
    Parses a TRADE-ANALYSIS-*.md file and writes to trade_signals.
    Returns the inserted row dict.
    """
    path = Path(filepath)
    text = path.read_text()

    ticker       = _extract_ticker(path.name)
    eur_usd      = get_eur_usd()

    row = {
        "ticker":             ticker,
        "generated_at":       datetime.now(timezone.utc).isoformat(),
        "eur_usd":            eur_usd,
        "tier":               tier,
        "analysis_file_path": str(path.resolve()),
        "rescore_required":   False,
    }

    row.update(_extract_scores(text))
    row.update(_extract_price_levels(text, eur_usd))
    row["sub_scores_json"] = _extract_sub_scores(text)

    client = get_client()
    client.table("trade_signals").insert(row).execute()
    print(f"  ✓ {ticker}: {row.get('signal')} ({row.get('composite_score')}/100) → Supabase")
    return row


def _extract_ticker(filename: str) -> str:
    m = re.search(r"TRADE-ANALYSIS-([A-Z0-9\.]+)\.md", filename, re.IGNORECASE)
    return m.group(1).upper() if m else filename


def _extract_scores(text: str) -> dict:
    result = {}

    m = re.search(r"\*\*Composite Trade Score\*\*.*?\*\*(\d+)/100\*\*", text)
    if m:
        result["composite_score"] = int(m.group(1))

    m = re.search(r"\*\*Grade:\s*([A-F+]+)\*\*", text)
    if m:
        result["grade"] = m.group(1)

    m = re.search(r"\*\*Signal:\s*(.+?)\*\*", text)
    if m:
        result["signal"] = m.group(1).strip()

    for label, key in [
        ("Technical Strength", "technical_score"),
        ("Fundamental Quality", "fundamental_score"),
        ("Sentiment",          "sentiment_score"),
        ("Risk Profile",       "risk_score"),
        ("Thesis Conviction",  "thesis_score"),
    ]:
        m = re.search(rf"\|\s*{label}\s*\|\s*(\d+)/100", text)
        if m:
            result[key] = int(m.group(1))

    return result


def _extract_sub_scores(text: str) -> dict | None:
    """
    Parses sub-score lines like:
    **Technical** [68/100]: Trend 14/20 | Momentum 14/20 | Volume 14/20 | Pattern 13/20 | Rel Strength 13/20
    """
    def _parse_pairs(line: str) -> dict:
        result = {}
        for part in line.split("|"):
            m = re.search(r"(\w[\w /]+?)\s+(\d+)/20", part.strip())
            if m:
                key = m.group(1).strip().lower().replace(" ", "_").replace("/", "_")
                result[key] = int(m.group(2))
        return result

    patterns = {
        "technical":   r"\*\*Technical\*\*\s*\[\d+/100\]:\s*(.+)",
        "fundamental": r"\*\*Fundamental\*\*\s*\[\d+/100\]:\s*(.+)",
        "sentiment":   r"\*\*Sentiment\*\*\s*\[\d+/100\]:\s*(.+)",
        "risk":        r"\*\*Risk\*\*\s*\[\d+/100\]:\s*(.+)",
        "thesis":      r"\*\*Thesis\*\*\s*\[\d+/100\]:\s*(.+)",
    }

    result = {}
    for dim, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            parsed = _parse_pairs(m.group(1))
            if parsed:
                result[dim] = parsed

    return result if result else None


def _extract_price_levels(text: str, eur_usd: float) -> dict:
    result = {}

    def _usd(val_str: str | None) -> float | None:
        if not val_str:
            return None
        m = re.search(r"\$(\d[\d,]*\.?\d*)", val_str)
        if m:
            return float(m.group(1).replace(",", ""))
        m = re.search(r"€(\d[\d,]*\.?\d*)", val_str)
        if m:
            return float(m.group(1).replace(",", "")) * eur_usd
        return None

    # Entry zone: "| Entry Zone | $X – $X / €X – €X |"
    m = re.search(r"\|\s*Entry Zone\s*\|\s*\$?([\d,.]+)\s*[–-]\s*\$?([\d,.]+)", text)
    if m:
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        result["entry_low_usd"]  = lo
        result["entry_high_usd"] = hi
        result["entry_low_eur"]  = usd_to_eur(lo, eur_usd)
        result["entry_high_eur"] = usd_to_eur(hi, eur_usd)

    # Stop loss
    m = re.search(r"\|\s*Stop Loss\s*\|\s*\$?([\d,.]+)", text)
    if m:
        stop = float(m.group(1).replace(",", ""))
        result["stop_usd"] = stop
        result["stop_eur"] = usd_to_eur(stop, eur_usd)

    # Target 1
    m = re.search(r"\|\s*Target 1\s*\|\s*\$?([\d,.]+)", text)
    if m:
        t1 = float(m.group(1).replace(",", ""))
        result["target1_usd"] = t1
        result["target1_eur"] = usd_to_eur(t1, eur_usd)

    # Target 2
    m = re.search(r"\|\s*Target 2\s*\|\s*\$?([\d,.]+)", text)
    if m:
        t2 = float(m.group(1).replace(",", ""))
        result["target2_usd"] = t2
        result["target2_eur"] = usd_to_eur(t2, eur_usd)

    # Risk/Reward
    m = re.search(r"\|\s*Risk/Reward\s*\|\s*([\d.]+)\s*:", text)
    if m:
        result["risk_reward"] = float(m.group(1))

    # Position size %
    m = re.search(r"\|\s*Position Size\s*\|\s*([\d.]+)%", text)
    if m:
        result["position_size_pct"] = float(m.group(1))

    return result
