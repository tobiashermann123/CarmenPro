"""
OpenBB snapshot puller — fetches numeric data for Agents 1, 2, 4.
Writes one row to openbb_snapshots per ticker per run.
Uses free providers only: Yahoo Finance (yfinance) for price/technicals,
and basic ratios from the same source.
"""
from __future__ import annotations
import math
import warnings
from datetime import date, datetime, timezone
from typing import Any

from layers.layer2_data.fx import get_eur_usd, usd_to_eur
from layers.layer3_storage.client import get_client


_CRYPTO_REMAP = {"BTC": "BTC-USD", "ETH": "ETH-USD", "XRP": "XRP-USD",
                 "SOL": "SOL-USD", "BNB": "BNB-USD", "ADA": "ADA-USD",
                 "DOGE": "DOGE-USD", "MATIC": "MATIC-USD", "AVAX": "AVAX-USD"}

_EXCHANGE_REMAP = {"LVMH": "MC.PA", "ASML": "ASML.AS", "SAP": "SAP.DE"}


def pull_snapshot(ticker: str, eur_usd: float | None = None) -> dict[str, Any]:
    """
    Pulls a full numeric snapshot for a ticker.
    Returns a dict matching the openbb_snapshots schema.
    Writes the row to Supabase and returns it.
    """
    rate = eur_usd or get_eur_usd(_date=date.today())

    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance not installed. Run: pip install yfinance")

    yf_ticker = _CRYPTO_REMAP.get(ticker.upper()) or _EXCHANGE_REMAP.get(ticker.upper()) or ticker
    stock = yf.Ticker(yf_ticker)
    info  = stock.info or {}
    hist  = stock.history(period="1y")

    price_usd = _safe(info, "currentPrice") or _safe(info, "regularMarketPrice")

    # EMAs from price history
    ema_20 = ema_50 = ema_200 = rsi_14 = None
    if not hist.empty:
        closes  = hist["Close"]
        ema_20  = round(float(closes.ewm(span=20).mean().iloc[-1]),  2)
        ema_50  = round(float(closes.ewm(span=50).mean().iloc[-1]),  2)
        ema_200 = round(float(closes.ewm(span=200).mean().iloc[-1]), 2)
        rsi_14  = _calc_rsi(closes)

    row = {
        "ticker":              ticker.upper(),
        "snapped_at":          datetime.now(timezone.utc).isoformat(),
        "eur_usd":             rate,
        "price_usd":           price_usd,
        "price_eur":           usd_to_eur(price_usd, rate) if price_usd else None,
        "change_pct_1d":       _safe(info, "regularMarketChangePercent"),
        "week52_high_usd":     _safe(info, "fiftyTwoWeekHigh"),
        "week52_low_usd":      _safe(info, "fiftyTwoWeekLow"),
        "week52_high_eur":     usd_to_eur(_safe(info, "fiftyTwoWeekHigh"), rate) if _safe(info, "fiftyTwoWeekHigh") else None,
        "week52_low_eur":      usd_to_eur(_safe(info, "fiftyTwoWeekLow"),  rate) if _safe(info, "fiftyTwoWeekLow")  else None,
        "volume":              _int(_safe(info, "volume")),
        "avg_volume_20d":      _int(_safe(info, "averageVolume")),
        "ema_20":              ema_20,
        "ema_50":              ema_50,
        "ema_200":             ema_200,
        "rsi_14":              rsi_14,
        "macd_value":          None,  # calculated separately if needed
        "macd_signal":         None,
        "atr_14":              _calc_atr(hist) if not hist.empty else None,
        "pe_ttm":              _safe(info, "trailingPE"),
        "pe_forward":          _safe(info, "forwardPE"),
        "revenue_ttm":         _safe(info, "totalRevenue"),
        "revenue_growth_yoy":  _safe(info, "revenueGrowth"),
        "gross_margin":        _safe(info, "grossMargins"),
        "operating_margin":    _safe(info, "operatingMargins"),
        "net_margin":          _safe(info, "profitMargins"),
        "fcf_ttm":             _safe(info, "freeCashflow"),
        "debt_equity":         _safe(info, "debtToEquity"),
        "beta":                _safe(info, "beta"),
        "short_interest_pct":  _safe(info, "shortPercentOfFloat"),
        "iv_30d":              None,  # options data requires separate pull
    }

    try:
        get_client().table("openbb_snapshots").insert(row).execute()
    except Exception as exc:
        print(f"[openbb_puller] {ticker}: Supabase insert failed — {exc}")

    return row


def _int(val: float | None) -> int | None:
    return int(val) if val is not None else None


def _safe(info: dict, key: str) -> float | int | None:
    val = info.get(key)
    if val in (None, "N/A", "None", float("inf"), float("-inf")):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _calc_rsi(closes, period: int = 14) -> float | None:
    try:
        delta  = closes.diff().dropna()
        gain   = delta.clip(lower=0).rolling(period).mean()
        loss   = (-delta.clip(upper=0)).rolling(period).mean()
        rs     = gain / loss
        rsi    = 100 - (100 / (1 + rs))
        val = float(rsi.iloc[-1])
        return None if math.isnan(val) else round(val, 2)
    except Exception:
        return None


def _calc_atr(hist, period: int = 14) -> float | None:
    try:
        high, low, close_prev = hist["High"], hist["Low"], hist["Close"].shift(1)
        tr = (
            (high - low)
            .combine(abs(high - close_prev), max)
            .combine(abs(low  - close_prev), max)
        )
        return round(float(tr.rolling(period).mean().iloc[-1]), 4)
    except Exception:
        return None
