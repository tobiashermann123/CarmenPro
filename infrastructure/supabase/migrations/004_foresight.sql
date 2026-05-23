-- Foresight scores: LLM sentiment + bottleneck themes per ticker per document
CREATE TABLE foresight_scores (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT        NOT NULL,
    document_id     UUID        REFERENCES documents (id) ON DELETE SET NULL,
    report_date     DATE        NOT NULL,
    -- sentiment_score: -1.0 (strongly negative) to +1.0 (strongly positive)
    sentiment_score NUMERIC     NOT NULL CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0),
    -- sub-sector for MoS override logic (e.g. "liquid_cooling", "photonics")
    sub_sector      TEXT,
    -- free-form themes flagged by LLM (e.g. ARRAY['liquid_cooling','grid_capacity'])
    flagged_themes  TEXT[]      NOT NULL DEFAULT '{}',
    model_name      TEXT        NOT NULL,
    model_version   TEXT,
    raw_output      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_foresight_ticker      ON foresight_scores (ticker);
CREATE INDEX idx_foresight_report_date ON foresight_scores (report_date DESC);
-- Used by DCF engine: "foresight_score for sub_sector > 0.6 → lower MoS to 15%"
CREATE INDEX idx_foresight_sub_sector_score ON foresight_scores (sub_sector, sentiment_score DESC);
