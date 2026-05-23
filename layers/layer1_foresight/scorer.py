"""Layer 1 scorer: run vllm LLM inference to produce foresight scores."""

import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from layers.layer1_foresight.prompts import FORESIGHT_SYSTEM, FORESIGHT_USER
from layers.layer3_storage.client import get_client

_MAX_SCORE_CHARS = 14_000

_THEME_KEYWORDS = frozenset({
    "liquid cooling", "photonics", "grid capacity", "grid_capacity",
    "hbm", "high bandwidth memory", "advanced packaging", "data center",
    "gpu", "artificial intelligence", "supply chain", "bottleneck",
    "shortage", "capacity", "demand", "revenue", "guidance", "outlook",
    "power consumption", "cooling", "networking",
})


def _select_chunks_for_scoring(chunks: list[str]) -> str:
    """Select representative chunks up to _MAX_SCORE_CHARS.

    Always includes the first chunk (company overview), then greedily adds
    theme-relevant chunks until the budget is exhausted."""
    selected: list[str] = []
    total = 0

    def add(chunk: str) -> bool:
        nonlocal total
        if total + len(chunk) > _MAX_SCORE_CHARS:
            return False
        selected.append(chunk)
        total += len(chunk)
        return True

    if chunks:
        add(chunks[0])

    for chunk in chunks[1:]:
        if total >= _MAX_SCORE_CHARS:
            break
        chunk_lower = chunk.lower()
        if any(kw in chunk_lower for kw in _THEME_KEYWORDS):
            if not add(chunk):
                break

    return "\n\n---\n\n".join(selected)


def _parse_llm_output(raw: str) -> dict:
    """Parse and validate LLM JSON response. Raises loudly on bad format."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1].lstrip("json").strip() if len(parts) > 1 else cleaned

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON output: {raw!r}") from exc

    score = float(data.get("sentiment_score", 0))
    if not -1.0 <= score <= 1.0:
        raise ValueError(f"sentiment_score {score} out of [-1.0, 1.0]")

    return {
        "sentiment_score": round(score, 4),
        "sub_sector": str(data.get("sub_sector", "other")),
        "flagged_themes": [str(t) for t in data.get("flagged_themes", [])],
        "raw_output": raw,
    }


def _llm_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ["VLLM_BASE_URL"],
        api_key="not-needed",
    )


def score_document(
    document_id: str,
    ticker: str,
    chunks: list[str],
    report_date: Optional[str] = None,
) -> str:
    """Run LLM foresight scoring on document chunks.

    Returns the foresight_score_id. Raises loudly if LLM output is malformed."""
    if not chunks:
        raise ValueError(f"No chunks provided for document {document_id!r}")

    scoring_text = _select_chunks_for_scoring(chunks)
    model_name = os.environ["VLLM_MODEL"]

    response = _llm_client().chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": FORESIGHT_SYSTEM},
            {"role": "user", "content": FORESIGHT_USER.format(ticker=ticker, text=scoring_text)},
        ],
        temperature=0.1,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    raw_output = response.choices[0].message.content
    parsed = _parse_llm_output(raw_output)

    row = {
        "ticker": ticker,
        "document_id": document_id,
        "report_date": report_date,
        "sentiment_score": parsed["sentiment_score"],
        "sub_sector": parsed["sub_sector"],
        "flagged_themes": parsed["flagged_themes"],
        "model_name": model_name,
        "model_version": response.model,
        "raw_output": parsed["raw_output"],
    }
    result = get_client().table("foresight_scores").insert(row).execute()
    return result.data[0]["id"]
