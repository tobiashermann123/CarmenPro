-- Adds structured notes storage and source tracking to trade_signals.
-- notes_json: per-dimension brief rationale from /trade score (replaces full markdown prose)
-- source: distinguishes deep /trade analyze runs from lean /trade score refreshes

ALTER TABLE trade_signals
ADD COLUMN IF NOT EXISTS notes_json  JSONB,
ADD COLUMN IF NOT EXISTS source      TEXT DEFAULT 'analyze'
    CHECK (source IN ('analyze', 'score'));
