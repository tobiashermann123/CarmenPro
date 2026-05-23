-- Upgrade raw_fundamentals from migration 003 schema to migration 012 schema.
-- Migration 012 used CREATE TABLE IF NOT EXISTS so this table still has the old layout.
--
-- Run this once in the Supabase SQL editor.

-- Add missing columns from the new schema (idempotent)
ALTER TABLE raw_fundamentals
  ADD COLUMN IF NOT EXISTS fiscal_year         SMALLINT,
  ADD COLUMN IF NOT EXISTS eps_diluted         NUMERIC,
  ADD COLUMN IF NOT EXISTS cfo                 NUMERIC,
  ADD COLUMN IF NOT EXISTS capex               NUMERIC,
  ADD COLUMN IF NOT EXISTS fcf                 NUMERIC,
  ADD COLUMN IF NOT EXISTS cash                NUMERIC,
  ADD COLUMN IF NOT EXISTS net_debt            NUMERIC,
  ADD COLUMN IF NOT EXISTS shares_outstanding  NUMERIC,
  ADD COLUMN IF NOT EXISTS roa                 NUMERIC,
  ADD COLUMN IF NOT EXISTS roe                 NUMERIC,
  ADD COLUMN IF NOT EXISTS gross_margin        NUMERIC,
  ADD COLUMN IF NOT EXISTS asset_turnover      NUMERIC,
  ADD COLUMN IF NOT EXISTS current_ratio       NUMERIC,
  ADD COLUMN IF NOT EXISTS fcf_margin          NUMERIC;

-- Add period_end as alias for period_date (new rows use period_end)
ALTER TABLE raw_fundamentals
  ADD COLUMN IF NOT EXISTS period_end DATE;

-- Backfill period_end from period_date for existing rows
UPDATE raw_fundamentals SET period_end = period_date WHERE period_end IS NULL;

-- Add unique constraint on (ticker, period_end) if it doesn't exist
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'raw_fundamentals_ticker_period_end_key'
  ) THEN
    ALTER TABLE raw_fundamentals
      ADD CONSTRAINT raw_fundamentals_ticker_period_end_key UNIQUE (ticker, period_end);
  END IF;
END$$;

-- Index
CREATE INDEX IF NOT EXISTS idx_raw_fund_ticker ON raw_fundamentals (ticker, period_end DESC);
