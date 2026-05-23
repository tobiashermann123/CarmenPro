"""
2-stage Discounted Cash Flow model.

Stage 1: Project FCF for `projection_years` using estimated growth rate.
Stage 2: Terminal value via Gordon Growth Model.

WACC = Rf + beta × ERP  (simplified equity-only; sufficient for Tier 1 screening)
  Rf  = 4.5%  (US 10-year Treasury, 2026)
  ERP = 5.5%  (Damodaran equity risk premium)

FCF growth rate = 3-year historical FCF CAGR, capped at [-30%, +30%] to prevent
nonsensical projections from volatile base years.

Returns None for crypto tickers or when FCF history is insufficient.
"""
from __future__ import annotations

RISK_FREE_RATE     = 0.045
EQUITY_RISK_PREM   = 0.055
TERMINAL_GROWTH    = 0.025
PROJECTION_YEARS   = 5
MAX_FCF_GROWTH     = 0.30
MIN_FCF_GROWTH     = -0.30
FALLBACK_FCF_GROWTH = 0.05   # used when history is too short or unreliable


def compute_dcf(
    fcf_history: list[float],          # FCF values, oldest → newest, at least 1 year
    net_debt: float,                   # total_debt - cash  (negative = net cash)
    shares_outstanding: float,
    current_price: float,
    beta: float = 1.0,
    eur_usd: float = 1.0,
) -> dict | None:
    """
    Returns a dict with intrinsic_value_usd, margin_of_safety_pct, and model params.
    Returns None if the model cannot run (insufficient data, negative FCF).
    """
    if not fcf_history or shares_outstanding <= 0:
        return None

    latest_fcf = fcf_history[-1]

    # Skip companies with negative FCF in the most recent year
    if latest_fcf <= 0:
        return None

    # FCF growth rate: CAGR of available history, capped
    growth = _estimate_growth(fcf_history)

    wacc = RISK_FREE_RATE + beta * EQUITY_RISK_PREM

    # Guard: WACC must exceed terminal growth
    if wacc <= TERMINAL_GROWTH:
        wacc = TERMINAL_GROWTH + 0.01

    # Stage 1 — projected FCF PV
    pv_stage1 = 0.0
    last_projected_fcf = latest_fcf
    for t in range(1, PROJECTION_YEARS + 1):
        projected = last_projected_fcf * (1 + growth)
        pv_stage1 += projected / (1 + wacc) ** t
        last_projected_fcf = projected

    # Stage 2 — terminal value
    terminal_fcf = last_projected_fcf * (1 + TERMINAL_GROWTH)
    tv = terminal_fcf / (wacc - TERMINAL_GROWTH)
    pv_terminal = tv / (1 + wacc) ** PROJECTION_YEARS

    enterprise_value = pv_stage1 + pv_terminal
    equity_value = enterprise_value - net_debt
    intrinsic_usd = equity_value / shares_outstanding

    if intrinsic_usd <= 0:
        return None

    mos = (intrinsic_usd - current_price) / intrinsic_usd * 100
    intrinsic_eur = intrinsic_usd / eur_usd if eur_usd and eur_usd > 0 else None

    return {
        "intrinsic_value_usd":   round(intrinsic_usd, 2),
        "intrinsic_value_eur":   round(intrinsic_eur, 2) if intrinsic_eur else None,
        "margin_of_safety_pct":  round(mos, 1),
        "dcf_wacc":              round(wacc * 100, 2),
        "dcf_fcf_growth_rate":   round(growth * 100, 2),
        "pv_stage1":             round(pv_stage1, 0),
        "pv_terminal":           round(pv_terminal, 0),
        "enterprise_value":      round(enterprise_value, 0),
    }


def _estimate_growth(fcf_history: list[float]) -> float:
    """CAGR of FCF history, capped at MAX/MIN bounds."""
    # Need at least 2 positive values for a meaningful CAGR
    positives = [v for v in fcf_history if v > 0]
    if len(positives) < 2:
        return FALLBACK_FCF_GROWTH

    oldest, newest = positives[0], positives[-1]
    years = len(positives) - 1
    if years == 0:
        return FALLBACK_FCF_GROWTH

    try:
        cagr = (newest / oldest) ** (1.0 / years) - 1
    except (ZeroDivisionError, ValueError):
        return FALLBACK_FCF_GROWTH

    return max(MIN_FCF_GROWTH, min(MAX_FCF_GROWTH, cagr))
