-- Rescore queue: controls which tickers get rescored and when.
-- Priority 1=urgent, 2=soon, 3=normal staleness.
-- One pending row per ticker (enforced in code, not DB constraint).
CREATE TABLE IF NOT EXISTS rescore_queue (
    id           bigserial    PRIMARY KEY,
    ticker       text         NOT NULL,
    priority     int          NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 3),
    reason       text,
    queued_at    timestamptz  NOT NULL DEFAULT now(),
    processed_at timestamptz
);

-- Fast dequeue: top N pending by priority then age
CREATE INDEX IF NOT EXISTS idx_rescore_queue_pending
    ON rescore_queue (priority ASC, queued_at ASC)
    WHERE processed_at IS NULL;
