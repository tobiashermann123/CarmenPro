"""
Tier 1 source: tickers from Brian's portfolio in the CarmenBot Google Sheet.
Reads the "Brian's Portfolio" tab directly — same OAuth token as Tier 3.
Falls back to the brian_portfolio Supabase table if the sheet is unavailable.
"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CARMENBOT_SHEET_ID = os.environ.get(
    "CARMENBOT_SPREADSHEET_ID", "1yrTE1yxw0h_9yU2h7nbwXzrQq4V2yJg6MlKIeN7SdBk"
)
BRIANS_PORTFOLIO_TAB = "Brian's Portfolio"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _get_gspread_client():
    import gspread
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = os.environ.get(
        "GOOGLE_OAUTH_TOKEN_PATH", "credentials/google_oauth_token.json"
    )
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


def get_tier1_tickers() -> list[str]:
    """
    Returns all tickers from Brian's Portfolio tab in the CarmenBot sheet.
    Skips blank rows, header row, and non-ticker values.
    """
    try:
        gc    = _get_gspread_client()
        sheet = gc.open_by_key(CARMENBOT_SHEET_ID).worksheet(BRIANS_PORTFOLIO_TAB)
        rows  = sheet.get_all_values()

        if not rows:
            return []

        # Find TICKER column (header row)
        header = [h.strip().upper() for h in rows[0]]
        try:
            ticker_col = header.index("TICKER")
        except ValueError:
            ticker_col = 0  # fallback: assume first column

        tickers = []
        for row in rows[1:]:
            if not row or not row[ticker_col].strip():
                continue
            t = row[ticker_col].strip().upper()
            if t and t != "N/A" and len(t) <= 6:
                tickers.append(t)

        return sorted(set(tickers))

    except Exception as exc:
        print(f"[tier1_source] Sheet read failed ({exc}), falling back to Supabase")
        return _get_tier1_from_supabase()


def get_tier1_with_context() -> list[dict]:
    """
    Returns ticker + allocation from Brian's Portfolio tab.
    """
    try:
        gc    = _get_gspread_client()
        sheet = gc.open_by_key(CARMENBOT_SHEET_ID).worksheet(BRIANS_PORTFOLIO_TAB)
        rows  = sheet.get_all_values()

        if len(rows) < 2:
            return []

        header = [h.strip().upper() for h in rows[0]]
        idx = {col: i for i, col in enumerate(header)}

        result = []
        for row in rows[1:]:
            def get(col):
                i = idx.get(col)
                return row[i].strip() if i is not None and i < len(row) else ""

            ticker = get("TICKER")
            if not ticker or ticker == "N/A":
                continue
            result.append({
                "ticker":     ticker.upper(),
                "allocation": get("ALLOCATION"),
                "ytd":        get("YTD"),
                "one_year":   get("1 YR"),
                "five_year":  get("5 YR"),
            })
        return result

    except Exception as exc:
        print(f"[tier1_source] Sheet read failed ({exc})")
        return []


def _get_tier1_from_supabase() -> list[str]:
    """Fallback: reads from brian_portfolio Supabase table."""
    from layers.layer3_storage.client import get_client
    result = (
        get_client()
        .table("brian_portfolio")
        .select("ticker")
        .eq("is_active", True)
        .execute()
    )
    return sorted({row["ticker"].upper() for row in result.data})


def get_carmenpro_tickers() -> list[str]:
    """Distinct tickers from trade_signals — our active scored watchlist."""
    from layers.layer3_storage.client import get_client
    rows = (
        get_client()
        .table("trade_signals")
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


def mark_ticker_inactive(ticker: str) -> None:
    """Called when a thesis is invalidated — removes from active Tier 1."""
    from layers.layer3_storage.client import get_client
    get_client().table("brian_portfolio").update({"is_active": False}).eq("ticker", ticker.upper()).execute()
