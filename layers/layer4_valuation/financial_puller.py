"""
Fetches annual financial statements from yfinance and writes to raw_fundamentals.

Returns a structured dict consumed by dcf.py and piotroski.py.
Gracefully skips crypto tickers and handles missing/null data.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yfinance as yf
import pandas as pd

from layers.layer3_storage.client import get_client

CRYPTO_TICKERS = {"BTC", "ETH", "XRP", "SOL", "BNB", "ADA", "DOGE", "MATIC", "AVAX"}

# yfinance row name alternatives (different versions use different names)
_INCOME_ROWS = {
    "revenue":          ["Total Revenue"],
    "gross_profit":     ["Gross Profit"],
    "operating_income": ["Operating Income", "EBIT"],
    "net_income":       ["Net Income"],
    "ebitda":           ["EBITDA", "Normalized EBITDA"],
    "eps_diluted":      ["Diluted EPS"],
}
_CASHFLOW_ROWS = {
    "cfo":   ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "capex": ["Capital Expenditure", "Capital Expenditures",
              "Purchase Of Plant Property Equipment And Software"],
    "fcf":   ["Free Cash Flow"],
}
_BALANCE_ROWS = {
    "cash":                ["Cash And Cash Equivalents",
                            "Cash Cash Equivalents And Short Term Investments"],
    "total_debt":          ["Total Debt"],
    "total_assets":        ["Total Assets"],
    "total_equity":        ["Stockholders Equity", "Common Stock Equity",
                            "Total Stockholders Equity"],
    "current_assets":      ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "shares_outstanding":  ["Ordinary Shares Number", "Share Issued"],
}


def _get(df: pd.DataFrame, col: pd.Timestamp, *names: str) -> float | None:
    """Try multiple row names; return float or None."""
    for name in names:
        if name in df.index:
            val = df.loc[name, col]
            if pd.notna(val):
                return float(val)
    return None


def pull_financials(ticker: str) -> dict | None:
    """
    Fetch up to 3 years of annual financials from yfinance.
    Returns None for crypto or when data is unavailable.
    """
    if ticker.upper() in CRYPTO_TICKERS:
        return None

    try:
        stock  = yf.Ticker(ticker)
        income = stock.income_stmt       # yfinance 1.x
        cashflow = stock.cash_flow
        balance  = stock.balance_sheet
        info     = stock.info or {}
    except Exception as exc:
        print(f"[financial_puller] {ticker}: yfinance error — {exc}")
        return None

    if income is None or income.empty:
        print(f"[financial_puller] {ticker}: no income statement data")
        return None

    years_data = []
    dates = income.columns[:3]  # 3 most recent fiscal year ends

    for date in dates:
        try:
            row = _build_year_row(ticker, date, income, cashflow, balance, info)
            years_data.append(row)
        except Exception as exc:
            print(f"[financial_puller] {ticker} {date.date()}: {exc}")

    if not years_data:
        return None

    # Persist to Supabase (upsert on ticker + period_end)
    _write_to_supabase(years_data)

    beta = float(info.get("beta") or 1.0)
    shares = (
        years_data[0].get("shares_outstanding")
        or float(info.get("sharesOutstanding") or 0)
    )

    return {
        "ticker":             ticker.upper(),
        "years":              years_data,   # newest first
        "beta":               beta,
        "shares_outstanding": shares,
    }


def _build_year_row(
    ticker: str,
    date: pd.Timestamp,
    income: pd.DataFrame,
    cashflow: pd.DataFrame,
    balance: pd.DataFrame,
    info: dict,
) -> dict:
    g = lambda df, *names: _get(df, date, *names)

    # Income statement
    revenue    = g(income, *_INCOME_ROWS["revenue"])
    gross      = g(income, *_INCOME_ROWS["gross_profit"])
    op_income  = g(income, *_INCOME_ROWS["operating_income"])
    net_income = g(income, *_INCOME_ROWS["net_income"])
    ebitda     = g(income, *_INCOME_ROWS["ebitda"])
    eps        = g(income, *_INCOME_ROWS["eps_diluted"])

    # Cash flow
    cfo   = g(cashflow, *_CASHFLOW_ROWS["cfo"])
    capex = g(cashflow, *_CASHFLOW_ROWS["capex"])
    # Normalize capex to negative (outflow convention)
    if capex is not None and capex > 0:
        capex = -capex
    fcf = g(cashflow, *_CASHFLOW_ROWS["fcf"])
    if fcf is None and cfo is not None and capex is not None:
        fcf = cfo + capex

    # Balance sheet
    cash        = g(balance, *_BALANCE_ROWS["cash"])
    total_debt  = g(balance, *_BALANCE_ROWS["total_debt"]) or 0.0
    assets      = g(balance, *_BALANCE_ROWS["total_assets"])
    equity      = g(balance, *_BALANCE_ROWS["total_equity"])
    cur_assets  = g(balance, *_BALANCE_ROWS["current_assets"])
    cur_liab    = g(balance, *_BALANCE_ROWS["current_liabilities"])
    shares      = g(balance, *_BALANCE_ROWS["shares_outstanding"])
    if shares is None:
        shares = float(info.get("sharesOutstanding") or 0) or None

    net_debt = total_debt - (cash or 0.0)

    # Derived ratios (None-safe)
    def _ratio(a, b):
        return round(a / b, 6) if a is not None and b and b != 0 else None

    roa = _ratio(net_income, assets)
    roe = _ratio(net_income, equity)

    # DB row — column names match migration 012 raw_fundamentals schema
    db_row = {
        "ticker":               ticker.upper(),
        "period_end":           date.date().isoformat(),
        "fiscal_year":          date.year,
        "revenue":              revenue,
        "gross_profit":         gross,
        "operating_income":     op_income,
        "net_income":           net_income,
        "ebitda":               ebitda,
        "eps_diluted":          eps,
        "cfo":                  cfo,
        "capex":                capex,
        "fcf":                  fcf,
        "cash":                 cash,
        "total_debt":           total_debt,
        "net_debt":             net_debt,
        "total_assets":         assets,
        "total_equity":         equity,
        "current_assets":       cur_assets,
        "current_liabilities":  cur_liab,
        "shares_outstanding":   shares,
        "roa":                  roa,
        "roe":                  roe,
        "gross_margin":         _ratio(gross, revenue),
        "asset_turnover":       _ratio(revenue, assets),
        "current_ratio":        _ratio(cur_assets, cur_liab),
        "fcf_margin":           _ratio(fcf, revenue),
    }

    # Internal aliases used by DCF + Piotroski — not sent to DB
    db_row["_cfo"]      = cfo
    db_row["_fcf"]      = fcf
    db_row["_net_debt"] = net_debt

    return db_row


def _write_to_supabase(rows: list[dict]) -> None:
    client = get_client()
    db_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    try:
        client.table("raw_fundamentals").upsert(
            db_rows, on_conflict="ticker,period_end"
        ).execute()
    except Exception as exc:
        # Schema mismatch (old migration 003 schema still in place).
        # Run infrastructure/supabase/migrations/013_raw_fundamentals_v2.sql to fix.
        print(f"[financial_puller] raw_fundamentals write skipped — schema needs upgrade: {exc}")
