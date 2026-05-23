-- Alter system_state.value from TEXT to JSONB so Prefect flows
-- can upsert structured dicts (daily_brief, tier3_weekly_brief) directly.
-- Existing rows (execution_halted = 'false') are cast to JSON booleans.

ALTER TABLE system_state
    ALTER COLUMN value TYPE JSONB USING value::jsonb;

-- Re-seed execution_halted as a proper JSON boolean
UPDATE system_state
SET value = 'false'::jsonb
WHERE key = 'execution_halted';
