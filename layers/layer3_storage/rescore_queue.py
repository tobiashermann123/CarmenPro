"""
Rescore queue helpers — enqueue and dequeue tickers for scoring.

Priority scale:
  1  Urgent   — no signal yet, price moved >5%, earnings <7d
  2  Soon     — score is >1.5× staleness threshold for its grade
  3  Normal   — score crossed the staleness threshold for its grade

Staleness thresholds by grade:
  A+/A  →  7 days
  B     → 10 days
  C     → 14 days
  D/F   → 21 days
"""
from __future__ import annotations
from datetime import datetime, timezone

from layers.layer3_storage.client import get_client

STALE_DAYS: dict[str, int] = {
    "A+": 7, "A": 7, "B": 10, "C": 14, "D": 21, "F": 21,
}


def enqueue(ticker: str, priority: int, reason: str) -> None:
    """Add ticker to queue. Upgrades priority if already pending with lower urgency."""
    client = get_client()
    ticker = ticker.upper()

    existing = (
        client.table("rescore_queue")
        .select("id,priority")
        .eq("ticker", ticker)
        .is_("processed_at", "null")
        .limit(1)
        .execute()
    )

    if existing.data:
        row = existing.data[0]
        if priority < row["priority"]:  # lower number = higher urgency
            client.table("rescore_queue").update(
                {"priority": priority, "reason": reason}
            ).eq("id", row["id"]).execute()
    else:
        client.table("rescore_queue").insert(
            {"ticker": ticker, "priority": priority, "reason": reason}
        ).execute()


def dequeue(limit: int = 5) -> list[str]:
    """Return up to `limit` tickers from the queue, ordered by priority then age."""
    client = get_client()
    result = (
        client.table("rescore_queue")
        .select("id,ticker")
        .is_("processed_at", "null")
        .order("priority", desc=False)
        .order("queued_at", desc=False)
        .limit(limit)
        .execute()
    )
    return [row["ticker"] for row in (result.data or [])]


def mark_processed(ticker: str) -> None:
    """Mark the oldest pending entry for this ticker as done."""
    client = get_client()
    existing = (
        client.table("rescore_queue")
        .select("id")
        .eq("ticker", ticker.upper())
        .is_("processed_at", "null")
        .order("queued_at", desc=False)
        .limit(1)
        .execute()
    )
    if existing.data:
        client.table("rescore_queue").update(
            {"processed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", existing.data[0]["id"]).execute()


def staleness_priority(grade: str | None, generated_at: str | None) -> tuple[int, str] | tuple[None, None]:
    """
    Returns (priority, reason) if the signal is stale enough to queue, else (None, None).
    Uses 1.5× threshold for priority 2 (overdue), threshold for priority 3 (due).
    """
    if not generated_at:
        return 3, "no_generated_at"

    threshold = STALE_DAYS.get(str(grade or "B").upper().strip(), 14)
    try:
        scored = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return 3, "invalid_date"

    days_old = (datetime.now(timezone.utc) - scored).days

    if days_old >= int(threshold * 1.5):
        return 2, f"overdue_{days_old}d_grade_{grade}"
    if days_old >= threshold:
        return 3, f"stale_{days_old}d_grade_{grade}"

    return None, None
