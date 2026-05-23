"""Layer 1 chunker: split text, compute embeddings, persist to document_chunks."""

import os

from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

load_dotenv()

from layers.layer3_storage.client import get_client

_EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-large-en-v1.5")
_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
_EMBED_BATCH = 64    # embeddings per batch — tune down if OOM on 4 GB server
_INSERT_BATCH = 100  # rows per Supabase insert


def _splitter() -> SentenceSplitter:
    return SentenceSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)


def _embed_model() -> HuggingFaceEmbedding:
    return HuggingFaceEmbedding(model_name=_EMBED_MODEL_NAME)


def split_text(text: str) -> list[str]:
    chunks = _splitter().split_text(text)
    if not chunks:
        raise ValueError("SentenceSplitter produced zero chunks — check input text")
    return chunks


def embed_document(document_id: str, text: str) -> tuple[int, list[str]]:
    """Chunk text, compute BAAI/bge-large-en-v1.5 embeddings, persist to document_chunks.

    Returns (n_chunks, chunks). Marks document processing_status='completed' on success."""
    chunks = split_text(text)
    model = _embed_model()

    all_embeddings: list[list[float]] = []
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start : start + _EMBED_BATCH]
        all_embeddings.extend(model.get_text_embedding_batch(batch, show_progress=True))

    if len(all_embeddings) != len(chunks):
        raise RuntimeError(
            f"Embedding count mismatch: {len(all_embeddings)} vs {len(chunks)} chunks"
        )

    rows = [
        {
            "document_id": document_id,
            "chunk_index": i,
            "text_content": chunk,
            "embedding": embedding,
            "token_count": len(chunk.split()),
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, all_embeddings))
    ]

    client = get_client()
    for start in range(0, len(rows), _INSERT_BATCH):
        client.table("document_chunks").insert(rows[start : start + _INSERT_BATCH]).execute()

    client.table("documents").update({"processing_status": "completed"}).eq(
        "id", document_id
    ).execute()

    return len(chunks), chunks
