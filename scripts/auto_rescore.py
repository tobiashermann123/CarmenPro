"""
Auto-rescore tickers flagged rescore_required in the daily brief.

Runs after run_daily_snapshot.py in GitHub Actions.
For each flagged ticker: 3 Tavily searches → Claude API scoring → Supabase upsert.

Env vars required:
    ANTHROPIC_API_KEY
    TAVILY_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Usage:
    python scripts/auto_rescore.py              # reads rescore_due from daily_brief
    python scripts/auto_rescore.py NVDA TSLA    # force-rescore specific tickers
"""
from __future__ import annotations
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from layers.layer2_data.fx import get_eur_usd
from layers.layer3_storage.client import get_client
from scripts.upsert_signal import build_row

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TICKERS  = 10   # safety cap per run

SCORING_PROMPT = """\
You are a quantitative stock analyst. Based on the research data below, produce a \
trade score for {ticker} (current price: ${price_usd:.2f}).

=== PRICE & METRICS ===
{search_a}

=== NEWS & ANALYSTS ===
{search_b}

=== TECHNICALS ===
{search_c}

Score each dimension 0-100 using these weights:
  Technical (25%):    trend, MAs, RSI, volume, chart pattern
  Fundamental (25%):  valuation vs peers, growth, margins, balance sheet
  Sentiment (20%):    analyst consensus, news tone, institutional activity
  Risk (15%):         beta/volatility, downside scenarios, macro sensitivity
  Thesis (15%):       catalyst clarity, timing, asymmetry, conviction

Composite = Technical×0.25 + Fundamental×0.25 + Sentiment×0.20 + Risk×0.15 + Thesis×0.15

Grades: A+(85-100) Strong Buy | A(70-84) Buy | B(55-69) Hold/Accumulate | \
C(40-54) Neutral | D(25-39) Caution | F(0-24) Avoid

Derive price levels:
  entry_low_usd:  key support or current price if already below entry
  entry_high_usd: entry zone top (resistance or current price)
  stop_usd:       4-8% below entry_low
  target1_usd:    nearest resistance
  target2_usd:    analyst consensus PT or next major resistance
  risk_reward:    (target1 - entry_mid) / (entry_mid - stop)

Return ONLY a valid JSON object, no markdown, no explanation:
{{
  "ticker": "{ticker}",
  "composite_score": <int>,
  "grade": <"A+"|"A"|"B"|"C"|"D"|"F">,
  "signal": <"Strong Buy"|"Buy"|"Hold/Accumulate"|"Neutral"|"Caution"|"Avoid">,
  "technical_score": <int>,
  "fundamental_score": <int>,
  "sentiment_score": <int>,
  "risk_score": <int>,
  "thesis_score": <int>,
  "price_usd": {price_usd},
  "entry_low_usd": <float>,
  "entry_high_usd": <float>,
  "stop_usd": <float>,
  "target1_usd": <float>,
  "target2_usd": <float>,
  "risk_reward": <float>,
  "notes_json": {{
    "technical":    "<2 sentences with at least 1 number each>",
    "fundamental":  "<2 sentences with at least 1 number each>",
    "sentiment":    "<2 sentences with at least 1 number each>",
    "risk":         "<2 sentences with at least 1 number each>",
    "thesis":       "<2 sentences with at least 1 number each>",
    "bull_catalyst":"<1 sentence>",
    "bear_risk":    "<1 sentence>"
  }}
}}
"""


def _get_rescore_tickers() -> list[str]:
    client = get_client()
    result = (
        client.table("system_state")
        .select("value")
        .eq("key", "daily_brief")
        .limit(1)
        .execute()
    )
    if not result.data:
        return []
    brief = result.data[0].get("value") or {}
    return [entry["ticker"] for entry in brief.get("rescore_due", [])]


def _tavily_search(query: str) -> str:
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    results = client.search(query=query, max_results=5, search_depth="basic")
    snippets = []
    for r in results.get("results", []):
        title   = r.get("title", "")
        content = r.get("content", "")[:400]
        snippets.append(f"• {title}: {content}")
    return "\n".join(snippets) or "No results."


def _call_claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text.strip())


def rescore_ticker(ticker: str, price_usd: float, eur_usd: float) -> dict | None:
    today = date.today().isoformat()
    print(f"  {ticker}: searching…", flush=True)

    try:
        search_a = _tavily_search(f'"{ticker}" stock price market cap PE ratio 52-week high low {today[:4]}')
        search_b = _tavily_search(f'"{ticker}" stock news analyst rating price target {today[:4]}')
        search_c = _tavily_search(f'"{ticker}" stock technical analysis moving average support resistance RSI {today[:4]}')
    except Exception as exc:
        print(f"  {ticker}: search failed — {exc}")
        return None

    prompt = SCORING_PROMPT.format(
        ticker=ticker,
        price_usd=price_usd,
        search_a=search_a,
        search_b=search_b,
        search_c=search_c,
    )

    print(f"  {ticker}: scoring…", flush=True)
    try:
        raw = _call_claude(prompt)
        payload = _extract_json(raw)
    except Exception as exc:
        print(f"  {ticker}: Claude parse failed — {exc}")
        return None

    payload["ticker"] = ticker
    payload["price_usd"] = price_usd
    payload.setdefault("tier", 1)

    row = build_row(payload, eur_usd)
    row["source"] = "score"

    try:
        get_client().table("trade_signals").insert(row).execute()
    except Exception as exc:
        print(f"  {ticker}: Supabase insert failed — {exc}")
        return None

    score  = row.get("composite_score", "?")
    signal = row.get("signal", "?")
    action = row.get("action_state", "?")
    print(f"  ✓ {ticker}: {signal} ({score}/100) → {action}")
    return row


def _get_current_price(ticker: str) -> float | None:
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


def main():
    if len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
    else:
        tickers = _get_rescore_tickers()

    if not tickers:
        print("No tickers flagged for rescore today.")
        return

    tickers = tickers[:MAX_TICKERS]
    eur_usd = get_eur_usd(_date=date.today())
    print(f"Auto-rescore — {date.today().isoformat()} | EUR/USD {eur_usd:.4f}")
    print(f"Tickers: {tickers}\n")

    results = []
    for ticker in tickers:
        price = _get_current_price(ticker)
        if price is None:
            print(f"  {ticker}: no price — skipping")
            continue
        row = rescore_ticker(ticker, price, eur_usd)
        if row:
            results.append(row)

    print(f"\n  Done. {len(results)}/{len(tickers)} tickers rescored.")


if __name__ == "__main__":
    main()
