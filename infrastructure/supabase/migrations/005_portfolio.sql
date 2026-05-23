-- Portfolio ledger: every trade and position event, reconciled against IBKR Flex CSV.
-- All monetary values stored in both USD (as executed) and EUR (converted at trade time).
CREATE TABLE portfolio_ledger (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_date              DATE        NOT NULL,
    ticker                  TEXT        NOT NULL,
    action                  TEXT        NOT NULL
                                        CHECK (action IN (
                                            'BUY', 'SELL',
                                            'WRITE_PUT', 'CLOSE_PUT',
                                            'EXPIRE', 'ASSIGN',
                                            'DIVIDEND', 'INTEREST', 'FEE'
                                        )),
    quantity                NUMERIC     NOT NULL,
    price_usd               NUMERIC     NOT NULL,
    -- FX snapshot at exact order time — required by CLAUDE.md risk constraint
    fx_rate_usd_eur         NUMERIC     NOT NULL,
    price_eur               NUMERIC     NOT NULL,
    total_value_usd         NUMERIC     NOT NULL,
    total_value_eur         NUMERIC     NOT NULL,
    -- Execution guard: executor raises if order_type != 'LIMIT'
    order_type              TEXT        NOT NULL DEFAULT 'LIMIT'
                                        CHECK (order_type = 'LIMIT'),
    ibkr_order_id           TEXT,
    ibkr_exec_id            TEXT,
    -- Options fields (NULL for equity trades)
    option_type             TEXT        CHECK (option_type IN ('PUT', 'CALL')),
    strike_price            NUMERIC,
    expiry_date             DATE,
    -- Recorded at order time; executor aborts if < 100
    open_interest_at_trade  INTEGER,
    -- Reconciliation status
    status                  TEXT        NOT NULL DEFAULT 'CONFIRMED'
                                        CHECK (status IN (
                                            'PENDING', 'CONFIRMED', 'RECONCILED', 'MISMATCH'
                                        )),
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reconciled_at           TIMESTAMPTZ
);

CREATE INDEX idx_ledger_trade_date ON portfolio_ledger (trade_date DESC);
CREATE INDEX idx_ledger_ticker     ON portfolio_ledger (ticker);
CREATE INDEX idx_ledger_status     ON portfolio_ledger (status);
CREATE INDEX idx_ledger_ibkr_exec  ON portfolio_ledger (ibkr_exec_id) WHERE ibkr_exec_id IS NOT NULL;
