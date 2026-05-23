-- Documents: metadata for ingested PDFs and SEC filings
CREATE TABLE documents (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker            TEXT,
    document_type     TEXT        NOT NULL
                                  CHECK (document_type IN (
                                      '10-K', '10-Q', '8-K',
                                      'earnings_call', 'analyst_report',
                                      'press_release', 'other'
                                  )),
    title             TEXT,
    source_url        TEXT,
    file_path         TEXT,
    filing_date       DATE,
    page_count        INTEGER,
    file_size_bytes   BIGINT,
    processing_status TEXT        NOT NULL DEFAULT 'pending'
                                  CHECK (processing_status IN (
                                      'pending', 'processing', 'completed', 'failed'
                                  )),
    error_message     TEXT,
    metadata          JSONB       NOT NULL DEFAULT '{}',
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_ticker       ON documents (ticker);
CREATE INDEX idx_documents_filing_date  ON documents (filing_date DESC);
CREATE INDEX idx_documents_type_status  ON documents (document_type, processing_status);

-- Document chunks: chunked text + pgvector embeddings
CREATE TABLE document_chunks (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    UUID        NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index    INTEGER     NOT NULL,
    text_content   TEXT        NOT NULL,
    embedding      vector(1536),
    token_count    INTEGER,
    metadata       JSONB       NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_document_chunks_document ON document_chunks (document_id);

-- IVFFlat index for approximate nearest-neighbour search on embeddings.
-- lists=100 is appropriate for datasets up to ~1M chunks; tune upward if needed.
CREATE INDEX idx_document_chunks_embedding
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
