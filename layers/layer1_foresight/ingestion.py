"""Layer 1 ingestion: extract text from local PDFs or SEC EDGAR filings."""

import os
import time
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from unstructured.partition.auto import partition

load_dotenv()

from layers.layer3_storage.client import get_client

_EDGAR_BASE = "https://data.sec.gov"
_EDGAR_HEADERS = {
    "User-Agent": f"CarmenPro {os.getenv('CONTACT_EMAIL', 'tobias10176@gmail.com')}",
    "Accept-Encoding": "gzip, deflate",
}
_RATE_SLEEP = 0.15  # respect EDGAR's 10 req/s fair-use limit


def _get_cik(ticker: str) -> str:
    resp = httpx.get(
        f"{_EDGAR_BASE}/files/company_tickers.json",
        headers=_EDGAR_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"No EDGAR CIK found for ticker {ticker!r}")


def _latest_filing_url(cik: str, form_type: str) -> tuple[str, date]:
    time.sleep(_RATE_SLEEP)
    resp = httpx.get(
        f"{_EDGAR_BASE}/submissions/CIK{cik}.json",
        headers=_EDGAR_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == form_type:
            accession = recent["accessionNumber"][i].replace("-", "")
            primary = recent["primaryDocument"][i]
            filed = date.fromisoformat(recent["filingDate"][i])
            url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession}/{primary}"
            )
            return url, filed
    raise ValueError(f"No {form_type!r} filing found for CIK {cik}")


def _extract_text(source: str) -> str:
    strategy = "hi_res" if source.endswith(".pdf") else "fast"
    elements = partition(source, strategy=strategy)
    texts = [el.text for el in elements if getattr(el, "text", None)]
    combined = "\n\n".join(texts).strip()
    if not combined:
        raise ValueError(
            f"unstructured returned empty text for {source!r} — check file content"
        )
    return combined


def _create_document_row(
    ticker: str,
    document_type: str,
    title: str,
    source_url: Optional[str],
    file_path: Optional[str],
    filing_date: Optional[date],
) -> str:
    row = {
        "ticker": ticker,
        "document_type": document_type,
        "title": title,
        "source_url": source_url,
        "file_path": file_path,
        "filing_date": filing_date.isoformat() if filing_date else None,
        "processing_status": "processing",
    }
    result = get_client().table("documents").insert(row).execute()
    return result.data[0]["id"]


def ingest_pdf(
    file_path: str | Path,
    ticker: str,
    document_type: str = "other",
    filing_date: Optional[date] = None,
) -> tuple[str, str]:
    """Ingest a local PDF or HTML file.

    Returns (document_id, extracted_text). Raises loudly on empty content."""
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    text = _extract_text(str(path))
    document_id = _create_document_row(
        ticker=ticker,
        document_type=document_type,
        title=path.name,
        source_url=None,
        file_path=str(path),
        filing_date=filing_date,
    )
    return document_id, text


def ingest_sec_filing(ticker: str, form_type: str = "10-K") -> tuple[str, str]:
    """Download and ingest the latest SEC EDGAR filing for a ticker.

    Returns (document_id, extracted_text). Raises loudly on empty content."""
    cik = _get_cik(ticker)
    time.sleep(_RATE_SLEEP)
    filing_url, filing_date = _latest_filing_url(cik, form_type)

    time.sleep(_RATE_SLEEP)
    resp = httpx.get(
        filing_url, headers=_EDGAR_HEADERS, follow_redirects=True, timeout=90
    )
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    suffix = ".pdf" if "pdf" in content_type else ".htm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        text = _extract_text(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    document_id = _create_document_row(
        ticker=ticker,
        document_type=form_type,
        title=f"{ticker} {form_type} {filing_date}",
        source_url=filing_url,
        file_path=None,
        filing_date=filing_date,
    )
    return document_id, text
