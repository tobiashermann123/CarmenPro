"""EUR/USD rate — fetched once per session, cached for the day."""
import httpx
from functools import lru_cache
from datetime import date


@lru_cache(maxsize=1)
def get_eur_usd(_date: date = None) -> float:
    """
    Returns today's EUR/USD mid rate.
    Pass _date=date.today() to bust the daily cache.
    Falls back to 1.10 and logs a warning if the fetch fails.
    """
    _date = _date or date.today()
    try:
        r = httpx.get(
            "https://open.er-api.com/v6/latest/EUR",
            timeout=5,
        )
        r.raise_for_status()
        rate = r.json()["rates"]["USD"]
        return float(rate)
    except Exception as exc:
        import warnings
        warnings.warn(f"EUR/USD fetch failed ({exc}), using fallback 1.10")
        return 1.10


def usd_to_eur(usd: float, rate: float | None = None) -> float:
    rate = rate or get_eur_usd()
    return round(usd / rate, 4)


def eur_to_usd(eur: float, rate: float | None = None) -> float:
    rate = rate or get_eur_usd()
    return round(eur * rate, 4)
