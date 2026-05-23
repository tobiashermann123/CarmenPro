"""
Piotroski F-Score (0–9).

Three pillars, each worth up to 3 points:
  Profitability (F1–F4): ROA, CFO, ΔROa, accruals quality
  Leverage / Liquidity (F5–F7): debt ratio, current ratio, dilution
  Operating Efficiency (F8–F9): gross margin, asset turnover

Score interpretation:
  0–2  Weak — likely to underperform; exclude from buy candidates
  3–5  Average
  6–9  Strong — high financial quality signal

Requires two consecutive annual periods (current and prior year).
Returns None when insufficient data.
"""
from __future__ import annotations


def compute_piotroski(current: dict, prior: dict) -> dict | None:
    """
    current / prior: dicts from raw_fundamentals rows.
    Required keys: roa, cfo, total_assets, total_debt, current_ratio,
                   shares_outstanding, gross_margin, asset_turnover, net_income.
    """
    required = ("roa", "cfo", "total_assets", "total_debt",
                "current_ratio", "shares_outstanding", "gross_margin", "asset_turnover")
    if any(current.get(k) is None or prior.get(k) is None for k in required):
        return None

    # ── Profitability ──────────────────────────────────────────────────────────
    f1 = int(current["roa"] > 0)
    f2 = int(current["cfo"] > 0)
    f3 = int(current["roa"] > prior["roa"])
    # Accruals: operating cash earnings quality (CFO/assets > ROA)
    f4 = int(
        current["total_assets"] > 0
        and (current["cfo"] / current["total_assets"]) > current["roa"]
    )

    # ── Leverage / Liquidity ───────────────────────────────────────────────────
    cur_lev  = current["total_debt"] / current["total_assets"] if current["total_assets"] else 1
    prior_lev = prior["total_debt"] / prior["total_assets"] if prior["total_assets"] else 1
    f5 = int(cur_lev < prior_lev)                                    # leverage improving
    f6 = int(current["current_ratio"] > prior["current_ratio"])      # liquidity improving
    f7 = int(current["shares_outstanding"] <= prior["shares_outstanding"] * 1.02)  # <2% dilution

    # ── Operating Efficiency ───────────────────────────────────────────────────
    f8 = int(current["gross_margin"] > prior["gross_margin"])
    f9 = int(current["asset_turnover"] > prior["asset_turnover"])

    score = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9

    return {
        "piotroski_score": score,
        "breakdown": {
            "f1_roa_positive":       f1,
            "f2_cfo_positive":       f2,
            "f3_roa_improving":      f3,
            "f4_accruals_quality":   f4,
            "f5_leverage_improving": f5,
            "f6_liquidity_improving":f6,
            "f7_no_dilution":        f7,
            "f8_margin_improving":   f8,
            "f9_turnover_improving": f9,
        },
    }
