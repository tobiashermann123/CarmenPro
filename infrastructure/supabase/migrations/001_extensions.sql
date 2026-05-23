-- Enable pgvector for 1536-dim embeddings (document_chunks)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm for future full-text search on documents
CREATE EXTENSION IF NOT EXISTS pg_trgm;
