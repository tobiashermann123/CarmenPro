-- Correct vector dimension from 1536 to 1024 to match BAAI/bge-large-en-v1.5.
-- 1536 is OpenAI text-embedding-ada-002 — a paid API, which violates the open-source constraint.
-- BAAI/bge-large-en-v1.5 is the highest-quality open-source English embedding model at this
-- dimension and runs locally via sentence-transformers on the Hetzner server.
ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding;
ALTER TABLE document_chunks ADD COLUMN embedding vector(1024);

DROP INDEX IF EXISTS idx_document_chunks_embedding;
CREATE INDEX idx_document_chunks_embedding
    ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
