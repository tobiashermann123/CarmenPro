-- Signal layer tables: CarmenAnalyst scores, OpenBB snapshots, Brian's portfolio.
-- All USD prices carry an EUR equivalent at the rate recorded at snapshot time.

-- ── Brian's portfolio (Tier 1 source) ────────────────────────────────────────
-- Populated by the Discord listener. Each row = one ticker Brian actively mentions.
CREATE TABLE IF NOT EXISTS brian_portfolio (
    id              BIGSERIAL   PRIMARY KEY,
    ticker          TEXT        NOT NULL,
    mentioned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT        NOT NULL DEFAULT 'discord',
    context         TEXT,                           -- raw message excerpt
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    UNIQUE (ticker, mentioned_at)
);

CREATE INDEX idx_brian_portfolio_ticker  ON brian_portfolio (ticker);
CREATE INDEX idx_brian_portfolio_active  ON brian_portfolio (is_active) WHERE is_active = TRUE;

-- ── OpenBB numeric snapshots (Tier 1 + Tier 3, daily) ────────────────────────
CREATE TABLE IF NOT EXISTS openbb_snapshots (
    id                  BIGSERIAL   PRIMARY KEY,
    ticker              TEXT        NOT NULL,
    snapped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- FX
    eur_usd             NUMERIC     NOT NULL,
    -- Price
    price_usd           NUMERIC,
    price_eur           NUMERIC,
    change_pct_1d       NUMERIC,
    -- Range
    week52_high_usd     NUMERIC,
    week52_low_usd      NUMERIC,
    week52_high_eur     NUMERIC,
    week52_low_eur      NUMERIC,
    -- Volume
    volume              BIGINT,
    avg_volume_20d      BIGINT,
    -- Technicals
    ema_20              NUMERIC,
    ema_50              NUMERIC,
    ema_200             NUMERIC,
    rsi_14              NUMERIC,
    macd_value          NUMERIC,
    macd_signal         NUMERIC,
    atr_14              NUMERIC,
    -- Fundamentals
    pe_ttm              NUMERIC,
    pe_forward          NUMERIC,
    revenue_ttm         NUMERIC,
    revenue_growth_yoy  NUMERIC,
    gross_margin        NUMERIC,
    operating_margin    NUMERIC,
    net_margin          NUMERIC,
    fcf_ttm             NUMERIC,
    debt_equity         NUMERIC,
    -- Risk
    beta                NUMERIC,
    short_interest_pct  NUMERIC,
    iv_30d              NUMERIC
);

CREATE INDEX idx_openbb_ticker_date ON openbb_snapshots (ticker, snapped_at DESC);

-- ── News snapshots (from WebSearch, structured on extraction) ─────────────────
CREATE TABLE IF NOT EXISTS news_snapshots (
    id          BIGSERIAL   PRIMARY KEY,
    ticker      TEXT        NOT NULL,
    snapped_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    headline    TEXT        NOT NULL,
    sentiment   TEXT        NOT NULL CHECK (sentiment IN ('positive', 'negative', 'neutral')),
    source      TEXT,
    published   DATE,
    raw_text    TEXT
);

CREATE INDEX idx_news_ticker_date ON news_snapshots (ticker, snapped_at DESC);

-- ── Analyst ratings (structured from WebSearch) ───────────────────────────────
CREATE TABLE IF NOT EXISTS analyst_ratings (
    id              BIGSERIAL   PRIMARY KEY,
    ticker          TEXT        NOT NULL,
    snapped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    firm            TEXT,
    analyst         TEXT,
    rating          TEXT,
    target_usd      NUMERIC,
    target_eur      NUMERIC,
    prior_target_usd NUMERIC,
    action          TEXT CHECK (action IN ('upgrade', 'downgrade', 'maintain', 'initiate', 'resume')),
    eur_usd         NUMERIC
);

CREATE INDEX idx_analyst_ticker ON analyst_ratings (ticker, snapped_at DESC);

-- ── Trade signals (composite scores + actionable levels) ─────────────────────
CREATE TABLE IF NOT EXISTS trade_signals (
    id                  BIGSERIAL   PRIMARY KEY,
    ticker              TEXT        NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Scores
    composite_score     SMALLINT    CHECK (composite_score BETWEEN 0 AND 100),
    grade               TEXT        CHECK (grade IN ('A+', 'A', 'B', 'C', 'D', 'F')),
    signal              TEXT        CHECK (signal IN ('Strong Buy', 'Buy', 'Hold/Accumulate', 'Neutral', 'Caution', 'Avoid')),
    technical_score     SMALLINT,
    fundamental_score   SMALLINT,
    sentiment_score     SMALLINT,
    risk_score          SMALLINT,
    thesis_score        SMALLINT,
    -- Action state derived from score + price
    action_state        TEXT        CHECK (action_state IN ('BUY_NOW', 'LIMIT_QUEUED', 'WAIT', 'HOLD', 'AVOID')),
    -- Price levels (USD and EUR)
    eur_usd             NUMERIC     NOT NULL,
    price_usd           NUMERIC,
    price_eur           NUMERIC,
    entry_low_usd       NUMERIC,
    entry_high_usd      NUMERIC,
    entry_low_eur       NUMERIC,
    entry_high_eur      NUMERIC,
    stop_usd            NUMERIC,
    stop_eur            NUMERIC,
    target1_usd         NUMERIC,
    target1_eur         NUMERIC,
    target2_usd         NUMERIC,
    target2_eur         NUMERIC,
    risk_reward         NUMERIC,
    -- Position sizing against fund
    position_size_pct   NUMERIC,
    position_size_eur   NUMERIC,
    -- Flags
    rescore_required    BOOLEAN     NOT NULL DEFAULT FALSE,
    rescore_reason      TEXT,
    -- Source markdown file path (written by CarmenAnalyst)
    analysis_file_path  TEXT,
    -- Tier tracking
    tier                SMALLINT    CHECK (tier IN (1, 3))
);

CREATE INDEX idx_signals_ticker      ON trade_signals (ticker, generated_at DESC);
CREATE INDEX idx_signals_action      ON trade_signals (action_state);
CREATE INDEX idx_signals_rescore     ON trade_signals (rescore_required) WHERE rescore_required = TRUE;
CREATE INDEX idx_signals_score       ON trade_signals (composite_score DESC);
