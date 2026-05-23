-- Raw fundamentals: OpenBB balance sheet, income statement, cash flow, EV multiples
-- One row per (ticker, period_date, period_type). All monetary values in reporting currency (USD).
CREATE TABLE raw_fundamentals (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker                 TEXT        NOT NULL,
    period_date            DATE        NOT NULL,
    period_type            TEXT        NOT NULL CHECK (period_type IN ('annual', 'quarterly')),
    -- Income statement
    revenue                NUMERIC,
    gross_profit           NUMERIC,
    operating_income       NUMERIC,
    net_income             NUMERIC,
    ebitda                 NUMERIC,
    -- Balance sheet
    total_assets           NUMERIC,
    total_liabilities      NUMERIC,
    total_equity           NUMERIC,
    cash_and_equivalents   NUMERIC,
    total_debt             NUMERIC,
    current_assets         NUMERIC,
    current_liabilities    NUMERIC,
    -- Cash flow
    operating_cash_flow    NUMERIC,
    capital_expenditures   NUMERIC,
    free_cash_flow         NUMERIC,
    -- Enterprise value multiples
    enterprise_value       NUMERIC,
    market_cap             NUMERIC,
    ev_ebitda              NUMERIC,
    ev_revenue             NUMERIC,
    pe_ratio               NUMERIC,
    -- Full OpenBB payload preserved for auditability
    raw_data               JSONB       NOT NULL DEFAULT '{}',
    source                 TEXT        NOT NULL DEFAULT 'openbb',
    fetched_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, period_date, period_type)
);

CREATE INDEX idx_raw_fundamentals_ticker      ON raw_fundamentals (ticker);
CREATE INDEX idx_raw_fundamentals_period_date ON raw_fundamentals (period_date DESC);

-- Price timeseries: daily OHLCV per ticker
CREATE TABLE price_timeseries (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker         TEXT        NOT NULL,
    date           DATE        NOT NULL,
    open           NUMERIC     NOT NULL,
    high           NUMERIC     NOT NULL,
    low            NUMERIC     NOT NULL,
    close          NUMERIC     NOT NULL,
    adjusted_close NUMERIC,
    volume         BIGINT,
    currency       TEXT        NOT NULL DEFAULT 'USD',
    source         TEXT        NOT NULL DEFAULT 'openbb',
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, date)
);

CREATE INDEX idx_price_timeseries_ticker ON price_timeseries (ticker);
CREATE INDEX idx_price_timeseries_date   ON price_timeseries (date DESC);
