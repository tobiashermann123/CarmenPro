"""
Standalone CPSignals tab writer — no CarmenBot dependency.

Reads trade_signals + system_state from Supabase and writes the CPSignals
tab in the CarmenBot Google Sheet.  Auth: Google service account.

Usage:
    python scripts/sync_to_gsheet.py

Env vars required (or in .env):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    GOOGLE_SERVICE_ACCOUNT_JSON   — full JSON string of service account key
    CARMENBOT_SPREADSHEET_ID      — Google Sheet ID (has hardcoded default)
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from layers.layer3_storage.client import get_client

SPREADSHEET_ID = os.environ.get(
    "CARMENBOT_SPREADSHEET_ID",
    "1yrTE1yxw0h_9yU2h7nbwXzrQq4V2yJg6MlKIeN7SdBk",
)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            info = json.loads(sa_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}. "
                "Make sure the secret is a minified single-line JSON string."
            ) from e
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        sa_path = Path(ROOT / "credentials" / "service_account.json")
        if not sa_path.exists():
            sa_path = Path(ROOT.parent / "CarmenBot" / "service_account.json")
        if not sa_path.exists():
            raise FileNotFoundError(
                "No service account found. Set GOOGLE_SERVICE_ACCOUNT_JSON env var "
                "or place service_account.json in credentials/."
            )
        creds = Credentials.from_service_account_file(str(sa_path), scopes=SCOPES)

    return gspread.authorize(creds)


def _safe(val, decimals: int | None = None) -> str:
    if val is None:
        return "—"
    try:
        f = float(val)
        return f"{f:.{decimals}f}" if decimals is not None else f"{f:.2f}"
    except (TypeError, ValueError):
        return str(val)


def get_latest_signals() -> list[dict]:
    client = get_client()
    result = (
        client.table("trade_signals")
        .select("*")
        .order("generated_at", desc=True)
        .execute()
    )
    seen: dict[str, dict] = {}
    for row in result.data:
        t = row.get("ticker", "")
        if t and t not in seen:
            seen[t] = row
    return list(seen.values())


def write_cpsignals(signals: list[dict]) -> None:
    gc = _gspread_client()
    ss = gc.open_by_key(SPREADSHEET_ID)

    try:
        ws = ss.worksheet("CPSignals")
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title="CPSignals", rows=200, cols=14)

    header = [
        "TICKER", "SCORE", "GRADE", "SIGNAL", "PRICE_EUR",
        "ENTRY_EUR", "STOP_EUR", "T1_EUR", "T2_EUR",
        "MOS_PCT", "PIOTROSKI", "IV_EUR", "SOURCE", "UPDATED",
    ]
    rows: list[list] = [header]
    for s in sorted(signals, key=lambda x: float(x.get("composite_score") or 0), reverse=True):
        rows.append([
            s.get("ticker", ""),
            _safe(s.get("composite_score"), 0),
            s.get("grade", "—"),
            s.get("signal", "—"),
            _safe(s.get("price_eur")),
            _safe(s.get("entry_low_eur")),
            _safe(s.get("stop_eur")),
            _safe(s.get("target1_eur")),
            _safe(s.get("target2_eur")),
            _safe(s.get("margin_of_safety_pct"), 1),
            _safe(s.get("piotroski_score"), 0) if s.get("piotroski_score") is not None else "—",
            _safe(s.get("intrinsic_value_eur")),
            s.get("source", "—"),
            (s.get("generated_at") or "")[:10],
        ])

    try:
        ws.clear()
        ws.update(range_name="A1", values=rows)
    except Exception as exc:
        raise RuntimeError(f"Google Sheets write failed — {exc}") from exc
    print(f"  ✓ CPSignals updated — {len(signals)} tickers")


def main():
    signals = get_latest_signals()
    print(f"Syncing {len(signals)} signals to CPSignals tab…")
    write_cpsignals(signals)
    print("Done.")


if __name__ == "__main__":
    main()
