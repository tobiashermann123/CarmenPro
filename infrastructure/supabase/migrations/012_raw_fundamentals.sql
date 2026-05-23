-- Layer 4: raw financial statement data (annual, pulled from yfinance).
-- One row per ticker per fiscal year.
-- Also extends trade_signals with DCF valuation outputs.

CREATE TABLE IF NOT EXISTS raw_fundamentals (
    id                  BIGSERIAL   PRIMARY KEY,
    ticker              TEXT        NOT NULL,
    pulled_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    period_end          DATE        NOT NULL,
    fiscal_year         SMALLINT,
    -- Income statement
    revenue             NUMERIC,
    gross_profit        NUMERIC,
    operating_income    NUMERIC,
    net_income          NUMERIC,
    ebitda              NUMERIC,
    eps_diluted         NUMERIC,
    -- Cash flow
    cfo                 NUMERIC,    -- cash from operations
    capex               NUMERIC,    -- capital expenditure (negative = outflow)
    fcf                 NUMERIC,    -- free cash flow = cfo + capex
    -- Balance sheet
    cash                NUMERIC,
    total_debt          NUMERIC,
    net_debt            NUMERIC,    -- total_debt - cash
    total_assets        NUMERIC,
    total_equity        NUMERIC,
    current_assets      NUMERIC,
    current_liabilities NUMERIC,
    shares_outstanding  NUMERIC,
    -- Derived ratios
    roa                 NUMERIC,    -- net_income / total_assets
    roe                 NUMERIC,    -- net_income / total_equity
    gross_margin        NUMERIC,    -- gross_profit / revenue
    asset_turnover      NUMERIC,    -- revenue / total_assets
    current_ratio       NUMERIC,    -- current_assets / current_liabilities
    fcf_margin          NUMERIC,    -- fcf / revenue
    UNIQUE (ticker, period_end)
);

CREATE INDEX idx_raw_fund_ticker ON raw_fundamentals (ticker, period_end DESC);

-- Extend trade_signals with DCF + Piotroski outputs
ALTER TABLE trade_signals
ADD COLUMN IF NOT EXISTS intrinsic_value_usd    NUMERIC,
ADD COLUMN IF NOT EXISTS intrinsic_value_eur    NUMERIC,
ADD COLUMN IF NOT EXISTS margin_of_safety_pct   NUMERIC,   -- positive = cheap, negative = expensive
ADD COLUMN IF NOT EXISTS piotroski_score        SMALLINT,  -- 0–9
ADD COLUMN IF NOT EXISTS dcf_wacc               NUMERIC,   -- % used in model
ADD COLUMN IF NOT EXISTS dcf_fcf_growth_rate    NUMERIC,   -- % used in model
ADD COLUMN IF NOT EXISTS valuation_updated_at   TIMESTAMPTZ;
