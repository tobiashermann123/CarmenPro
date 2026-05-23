"""
Auto-configures Metabase after first launch:
  1. Creates the admin account
  2. Connects to the CarmenPro Supabase database
  3. Creates 5 pre-built saved questions (dashboards)

Run once after `docker compose up -d`:
    python scripts/setup_metabase.py

Requires Metabase to be running on localhost:3000.
Reads SUPABASE_DB_URL from .env to extract connection details.
"""
from __future__ import annotations
import os
import sys
import time
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

METABASE_URL  = os.environ.get("METABASE_URL", "http://localhost:3000")
ADMIN_EMAIL   = os.environ.get("METABASE_ADMIN_EMAIL", "admin@carmenpro.io")
ADMIN_PASSWORD = os.environ.get("METABASE_ADMIN_PASSWORD", "Carmen2026!")

SAVED_QUESTIONS = [
    {
        "name": "Signal Overview",
        "description": "Latest signal per ticker — scores, valuation, action state",
        "display": "table",
        "sql": """
SELECT
    ticker,
    signal,
    grade,
    composite_score,
    ROUND(margin_of_safety_pct::numeric, 1) AS "MoS %",
    piotroski_score,
    action_state,
    ROUND(intrinsic_value_usd::numeric, 2)  AS "IV (USD)",
    ROUND(intrinsic_value_eur::numeric, 2)  AS "IV (EUR)",
    ROUND(entry_low_eur::numeric, 2)        AS "Entry Low (€)",
    ROUND(stop_eur::numeric, 2)             AS "Stop (€)",
    ROUND(target1_eur::numeric, 2)          AS "T1 (€)",
    source,
    generated_at::date                      AS date
FROM trade_signals
WHERE generated_at = (
    SELECT MAX(t2.generated_at)
    FROM trade_signals t2
    WHERE t2.ticker = trade_signals.ticker
)
ORDER BY composite_score DESC NULLS LAST;
""",
    },
    {
        "name": "Score History",
        "description": "Composite score over time per ticker — tracks drift",
        "display": "line",
        "sql": """
SELECT
    generated_at::date AS date,
    ticker,
    composite_score,
    source
FROM trade_signals
ORDER BY ticker, generated_at;
""",
    },
    {
        "name": "DCF Valuation Summary",
        "description": "Intrinsic value vs current price — margin of safety ranking",
        "display": "bar",
        "sql": """
SELECT
    ticker,
    ROUND(intrinsic_value_usd::numeric, 2)  AS "Intrinsic Value (USD)",
    ROUND(margin_of_safety_pct::numeric, 1) AS "Margin of Safety %",
    piotroski_score,
    ROUND(dcf_wacc::numeric, 2)             AS "WACC %",
    ROUND(dcf_fcf_growth_rate::numeric, 2)  AS "FCF Growth %"
FROM trade_signals
WHERE generated_at = (
    SELECT MAX(t2.generated_at)
    FROM trade_signals t2
    WHERE t2.ticker = trade_signals.ticker
)
  AND intrinsic_value_usd IS NOT NULL
ORDER BY margin_of_safety_pct DESC NULLS LAST;
""",
    },
    {
        "name": "Sub-Score Breakdown",
        "description": "Detailed sub-scores (Trend, Momentum, Valuation, etc.) per ticker",
        "display": "table",
        "sql": """
SELECT
    ticker,
    composite_score,
    sub_scores_json->'technical'->>'trend'         AS "Trend",
    sub_scores_json->'technical'->>'momentum'      AS "Momentum",
    sub_scores_json->'technical'->>'volume'        AS "Volume",
    sub_scores_json->'fundamental'->>'valuation'   AS "Valuation",
    sub_scores_json->'fundamental'->>'growth'      AS "Growth",
    sub_scores_json->'fundamental'->>'moat'        AS "Moat",
    sub_scores_json->'sentiment'->>'news'          AS "News",
    sub_scores_json->'sentiment'->>'analysts'      AS "Analysts",
    sub_scores_json->'risk'->>'volatility'         AS "Volatility",
    generated_at::date AS date
FROM trade_signals
WHERE generated_at = (
    SELECT MAX(t2.generated_at)
    FROM trade_signals t2
    WHERE t2.ticker = trade_signals.ticker
)
  AND sub_scores_json IS NOT NULL
ORDER BY composite_score DESC;
""",
    },
    {
        "name": "Daily Snapshots",
        "description": "Price and technical indicator history from OpenBB",
        "display": "table",
        "sql": """
SELECT
    ticker,
    snapped_at::date        AS date,
    ROUND(price_usd::numeric, 2)  AS "Price (USD)",
    ROUND(price_eur::numeric, 2)  AS "Price (EUR)",
    ROUND(change_pct_1d::numeric, 2) AS "1D Chg %",
    ROUND(rsi_14::numeric, 1) AS "RSI",
    ROUND(ema_50::numeric, 2)  AS "EMA 50",
    ROUND(ema_200::numeric, 2) AS "EMA 200",
    volume
FROM openbb_snapshots
ORDER BY ticker, snapped_at DESC;
""",
    },
]


def wait_for_metabase(timeout: int = 120) -> None:
    print(f"Waiting for Metabase at {METABASE_URL}...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{METABASE_URL}/api/health", timeout=5)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print(" ready.")
                return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(5)
    raise TimeoutError("Metabase did not start within timeout")


def get_setup_token() -> str:
    r = httpx.get(f"{METABASE_URL}/api/session/properties")
    r.raise_for_status()
    return r.json()["setup-token"]


def setup_admin_and_db(token: str) -> tuple[str, int]:
    """Returns (session_token, database_id)."""
    db_url  = os.environ["SUPABASE_DB_URL"]
    parsed  = urlparse(db_url)

    # Step 1: create admin user + prefs (v0.61 no longer returns db.id from /api/setup)
    setup_payload = {
        "token": token,
        "user": {
            "first_name": "CarmenPro",
            "last_name":  "Admin",
            "email":       ADMIN_EMAIL,
            "password":    ADMIN_PASSWORD,
            "site_name":   "CarmenPro",
        },
        "invite": None,
        "prefs": {"site_name": "CarmenPro", "allow_tracking": False},
    }

    r = httpx.post(f"{METABASE_URL}/api/setup", json=setup_payload, timeout=30)
    if not r.is_success:
        print(f"Setup API error {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
    session_token = r.json()["id"]
    print(f"Admin account created. Session: {session_token[:8]}...")

    # Step 2: add Supabase database
    headers  = {"X-Metabase-Session": session_token, "Content-Type": "application/json"}
    db_payload = {
        "name":    "CarmenPro — Supabase",
        "engine":  "postgres",
        "details": {
            "host":     parsed.hostname,
            "port":     parsed.port or 5432,
            "dbname":   (parsed.path or "/postgres").lstrip("/"),
            "user":     parsed.username,
            "password": parsed.password,
            "ssl":      True,
            "ssl-mode": "require",
        },
    }
    r2 = httpx.post(f"{METABASE_URL}/api/database", json=db_payload, headers=headers, timeout=30)
    if not r2.is_success:
        print(f"Database creation error {r2.status_code}: {r2.text[:400]}")
        r2.raise_for_status()
    db_id = r2.json()["id"]
    print(f"Supabase database connected. Database ID: {db_id}")
    return session_token, db_id


def create_questions(session_token: str, db_id: int) -> None:
    headers = {"X-Metabase-Session": session_token, "Content-Type": "application/json"}

    for q in SAVED_QUESTIONS:
        payload = {
            "name":          q["name"],
            "description":   q.get("description", ""),
            "display":       q["display"],
            "dataset_query": {
                "type":     "native",
                "native":   {"query": q["sql"].strip()},
                "database": db_id,
            },
            "visualization_settings": {},
        }
        r = httpx.post(
            f"{METABASE_URL}/api/card",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if r.status_code in (200, 202):
            print(f"  ✓ Created question: {q['name']}")
        else:
            print(f"  ✗ Failed: {q['name']} — {r.status_code} {r.text[:120]}")


def main():
    wait_for_metabase()

    print("Checking if Metabase is already configured...")
    props = httpx.get(f"{METABASE_URL}/api/session/properties").json()
    if not props.get("setup-token"):
        print("Metabase already set up. Skipping initial setup.")
        print(f"Open: {METABASE_URL}")
        return

    print("Running first-time setup...")
    token = props["setup-token"]
    session_token, db_id = setup_admin_and_db(token)

    print("Creating saved questions...")
    create_questions(session_token, db_id)

    print(f"""
Setup complete.
  URL:      {METABASE_URL}
  Email:    {ADMIN_EMAIL}
  Password: {ADMIN_PASSWORD}

Change your password after first login.
""")


if __name__ == "__main__":
    main()
