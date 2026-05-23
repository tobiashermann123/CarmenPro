"""
Tier 3 source: universe watchlist from the protected Google Sheet.
Uses OAuth2 with the user's own Google account — sheet owner sees no notifications.
Run scripts/google_auth.py once to generate the token.
"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _sheet_config() -> tuple[str, int, str]:
    sheet_id = os.environ.get("TIER3_SHEET_ID")
    if not sheet_id:
        raise EnvironmentError(
            "TIER3_SHEET_ID not set. Add it to .env — "
            "see .env.example for the value."
        )
    sheet_gid   = int(os.environ.get("TIER3_SHEET_GID", "0"))
    token_path  = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "credentials/google_oauth_token.json")
    return sheet_id, sheet_gid, token_path


def _get_gspread_client():
    import gspread
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    _, _, token_path = _sheet_config()
    token_file = Path(token_path)
    if not token_file.exists():
        raise FileNotFoundError(
            f"Google OAuth token not found at {token_path}. "
            "Run: python scripts/google_auth.py"
        )

    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())

    return gspread.authorize(creds)


def get_tier3_tickers() -> list[str]:
    """
    Returns all tickers from the Tier 3 Google Sheet.
    Assumes tickers are in the first column (column A), one per row, no header.
    Skips blank rows and rows that don't look like valid tickers.
    """
    sheet_id, sheet_gid, _ = _sheet_config()
    gc     = _get_gspread_client()
    sheet  = gc.open_by_key(sheet_id)

    target = next(
        (ws for ws in sheet.worksheets() if ws.id == sheet_gid),
        sheet.get_worksheet(0),
    )

    rows = target.col_values(1)  # column A only
    tickers = []
    for r in rows:
        t = r.strip().upper()
        if not t or t == "TICKER":  # skip blank and header
            continue
        # allow letters, dots, numbers — covers BRK.B, ADRs, etc.
        if len(t) <= 6 and all(c.isalnum() or c == "." for c in t):
            tickers.append(t)
    return sorted(set(tickers))


def get_tier3_with_metadata() -> list[dict]:
    """
    Returns all rows from the sheet as dicts.
    Assumes row 1 is a header row with column names.
    """
    sheet_id, sheet_gid, _ = _sheet_config()
    gc     = _get_gspread_client()
    sheet  = gc.open_by_key(sheet_id)

    target = next(
        (ws for ws in sheet.worksheets() if ws.id == sheet_gid),
        sheet.get_worksheet(0),
    )
    return target.get_all_records()
