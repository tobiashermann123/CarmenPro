"""
Price monitor — no LLM, no API cost.
Compares live price against stored trade_signals levels and:
  - Derives current action_state (BUY_NOW / LIMIT_QUEUED / WAIT / HOLD / AVOID)
  - Sets rescore_required=True if price moved >5% since last snapshot
  - Used by Prefect intraday flow to decide whether to queue IBKR orders
"""
from __future__ import annotations
from datetime import datetime, timezone

from layers.layer3_storage.client import get_client


def get_latest_signal(ticker: str) -> dict | None:
    client = get_client()
    result = (
        client.table("trade_signals")
        .select("*")
        .eq("ticker", ticker.upper())
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _state_from_signal(signal: dict, current_price_usd: float) -> str:
    """Derive action state from a pre-fetched signal dict."""
    if signal.get("signal") in ("Avoid", "Caution") or (signal.get("composite_score") or 0) < 40:
        return "AVOID"

    entry_low  = signal.get("entry_low_usd")
    entry_high = signal.get("entry_high_usd")

    if not entry_low or not entry_high:
        return "HOLD"

    if current_price_usd <= entry_high:
        if current_price_usd >= entry_low:
            return "BUY_NOW"
        return "WAIT"  # below zone — wait for it to come up, or reassess

    if entry_high == 0:
        return "WAIT"
    gap_pct = (current_price_usd - entry_high) / entry_high
    if gap_pct <= 0.05:
        return "LIMIT_QUEUED"
    return "WAIT"


def check_action_state(ticker: str, current_price_usd: float) -> str:
    """
    Returns the current action state for a ticker based on latest stored signal.

    BUY_NOW      — price is inside entry zone
    LIMIT_QUEUED — price is 0–5% above entry_high
    WAIT         — price is >5% above entry_high
    HOLD         — signal is Hold/Accumulate and no entry zone defined
    AVOID        — signal is Avoid or score < 40
    NO_SIGNAL    — no stored signal yet
    """
    signal = get_latest_signal(ticker)
    if not signal:
        return "NO_SIGNAL"
    return _state_from_signal(signal, current_price_usd)


def flag_rescore_if_needed(ticker: str, current_price_usd: float) -> bool:
    """
    Sets rescore_required=True on the latest trade_signal if price
    moved >5% since the snapshot was taken. Returns True if flag was set.
    """
    signal = get_latest_signal(ticker)
    if not signal:
        return False

    snapshot_price = signal.get("price_usd")
    if not snapshot_price:
        return False

    change_pct = abs(current_price_usd - snapshot_price) / snapshot_price
    if change_pct > 0.05:
        try:
            get_client().table("trade_signals").update({
                "rescore_required": True,
                "rescore_reason":   f"Price moved {change_pct:.1%} since last score (was ${snapshot_price:.2f}, now ${current_price_usd:.2f})",
            }).eq("id", signal["id"]).execute()
        except Exception as exc:
            print(f"[price_monitor] {ticker}: rescore flag write failed — {exc}")
        return True

    return False


def update_action_state(ticker: str, current_price_usd: float) -> str:
    """
    Convenience: checks state, updates the latest signal row, returns new state.
    Single DB read — reuses the fetched signal for both state check and rescore flag.
    """
    signal = get_latest_signal(ticker)
    state  = _state_from_signal(signal, current_price_usd) if signal else "NO_SIGNAL"

    if signal and signal.get("action_state") != state:
        try:
            get_client().table("trade_signals").update({
                "action_state": state,
            }).eq("id", signal["id"]).execute()
        except Exception as exc:
            print(f"[price_monitor] {ticker}: action_state update failed — {exc}")

    if signal:
        snapshot_price = signal.get("price_usd")
        if snapshot_price:
            change_pct = abs(current_price_usd - snapshot_price) / snapshot_price
            if change_pct > 0.05:
                try:
                    get_client().table("trade_signals").update({
                        "rescore_required": True,
                        "rescore_reason":   f"Price moved {change_pct:.1%} since last score (was ${snapshot_price:.2f}, now ${current_price_usd:.2f})",
                    }).eq("id", signal["id"]).execute()
                except Exception as exc:
                    print(f"[price_monitor] {ticker}: rescore flag write failed — {exc}")

    return state
