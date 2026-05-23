"""End-to-end foresight pipeline for a single document.

Sequence: ingest → chunk+embed → LLM score.
Each step is independently retryable. document.processing_status tracks progress
so a failed run can be resumed without re-ingesting.
"""

from datetime import date
from pathlib import Path
from typing import Optional

from layers.layer1_foresight.chunker import embed_document
from layers.layer1_foresight.ingestion import ingest_pdf, ingest_sec_filing
from layers.layer1_foresight.scorer import score_document
from layers.layer3_storage.client import get_client


def _mark_failed(document_id: str, error: str) -> None:
    get_client().table("documents").update(
        {"processing_status": "failed", "error_message": error[:2000]}
    ).eq("id", document_id).execute()


def run_for_pdf(
    file_path: str | Path,
    ticker: str,
    document_type: str = "other",
    filing_date: Optional[date] = None,
) -> dict:
    """Full pipeline for a local PDF or HTML file.

    Returns dict: document_id, score_id, n_chunks, sentiment_score,
    sub_sector, flagged_themes."""
    document_id: Optional[str] = None
    try:
        document_id, text = ingest_pdf(file_path, ticker, document_type, filing_date)
        n_chunks, chunks = embed_document(document_id, text)
        report_date = filing_date.isoformat() if filing_date else None
        score_id = score_document(document_id, ticker, chunks, report_date)
    except Exception as exc:
        if document_id:
            _mark_failed(document_id, str(exc))
        raise

    score_row = (
        get_client()
        .table("foresight_scores")
        .select("sentiment_score,flagged_themes,sub_sector")
        .eq("id", score_id)
        .single()
        .execute()
        .data
    )
    return {
        "document_id": document_id,
        "score_id": score_id,
        "n_chunks": n_chunks,
        "sentiment_score": score_row["sentiment_score"],
        "sub_sector": score_row["sub_sector"],
        "flagged_themes": score_row["flagged_themes"],
    }


def run_for_sec_filing(ticker: str, form_type: str = "10-K") -> dict:
    """Full pipeline for a SEC EDGAR filing.

    Returns dict: document_id, score_id, n_chunks, sentiment_score,
    sub_sector, flagged_themes, report_date."""
    document_id: Optional[str] = None
    try:
        document_id, text = ingest_sec_filing(ticker, form_type)
        n_chunks, chunks = embed_document(document_id, text)
        score_id = score_document(document_id, ticker, chunks)
    except Exception as exc:
        if document_id:
            _mark_failed(document_id, str(exc))
        raise

    score_row = (
        get_client()
        .table("foresight_scores")
        .select("sentiment_score,flagged_themes,sub_sector,report_date")
        .eq("id", score_id)
        .single()
        .execute()
        .data
    )
    return {
        "document_id": document_id,
        "score_id": score_id,
        "n_chunks": n_chunks,
        "sentiment_score": score_row["sentiment_score"],
        "sub_sector": score_row["sub_sector"],
        "flagged_themes": score_row["flagged_themes"],
        "report_date": score_row.get("report_date"),
    }
