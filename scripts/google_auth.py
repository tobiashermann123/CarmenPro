"""
Run once to authorise CarmenBot to read the Tier 3 Google Sheet.
Opens a browser window — log in with the Google account that has access to the sheet.
Token is saved to credentials/google_oauth_token.json and reused silently thereafter.

Usage:
    python scripts/google_auth.py
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET_PATH", "credentials/google_oauth_client.json")
TOKEN_PATH    = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH",          "credentials/google_oauth_token.json")
SHEET_ID      = os.environ.get("TIER3_SHEET_ID")
SHEET_GID     = int(os.environ.get("TIER3_SHEET_GID", "0"))

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def main():
    import gspread
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials

    token_file = Path(TOKEN_PATH)

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    client = gspread.authorize(creds)
    sheet  = client.open_by_key(SHEET_ID)

    worksheets = sheet.worksheets()
    print(f"\nConnected to sheet. Worksheets found:")
    for ws in worksheets:
        print(f"  [{ws.id}] {ws.title}  ({ws.row_count} rows)")

    target = next((ws for ws in worksheets if ws.id == SHEET_GID), None)
    if target:
        rows = target.get_all_values()
        print(f"\nFirst 5 rows of target tab '{target.title}':")
        for row in rows[:5]:
            print(" ", row)
    else:
        print(f"\nNo worksheet found with gid={SHEET_GID}. Check TIER3_SHEET_GID in .env")


if __name__ == "__main__":
    main()
