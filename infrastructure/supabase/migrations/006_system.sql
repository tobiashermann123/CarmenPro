-- System state: key-value store for runtime flags.
-- The reconciliation engine writes execution_halted=true on any EUR-cent discrepancy.
-- The execution engine checks this flag before every order; manual override required to resume.
CREATE TABLE system_state (
    key        TEXT        PRIMARY KEY,
    value      TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

-- Seed the execution halt flag — default OFF
INSERT INTO system_state (key, value, updated_by)
VALUES ('execution_halted', 'false', 'migration_006');
