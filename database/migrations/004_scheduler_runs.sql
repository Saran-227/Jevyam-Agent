-- ==============================================================================
-- Migration 004: Persistent Daily Scheduler Runs Table
-- Ensures idempotent daily post generation across ephemeral GitHub Actions runners
-- ==============================================================================

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_key TEXT UNIQUE NOT NULL,                   -- e.g. DAILY-RUN-20261112
    date TEXT NOT NULL,                                   -- e.g. 2026-11-12
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'SKIPPED', 'FAILED')),
    post_id TEXT REFERENCES posts(post_id) ON DELETE SET NULL,
    revision INTEGER,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    is_missed_run_recovery BOOLEAN NOT NULL DEFAULT false,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE scheduler_runs IS 'Tracks daily marketing agent generation executions for idempotency and disaster recovery';
COMMENT ON COLUMN scheduler_runs.execution_key IS 'Unique key per Indian calendar date (DAILY-RUN-YYYYMMDD)';
COMMENT ON COLUMN scheduler_runs.status IS 'RUNNING, SUCCESS, SKIPPED, or FAILED';

-- Indexes for rapid lookup during scheduled triggers
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_date ON scheduler_runs(date);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_runs(status);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_execution_key ON scheduler_runs(execution_key);

-- Automatic updated_at trigger
DROP TRIGGER IF EXISTS trigger_scheduler_runs_updated_at ON scheduler_runs;
CREATE TRIGGER trigger_scheduler_runs_updated_at
    BEFORE UPDATE ON scheduler_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security
ALTER TABLE scheduler_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow full access to scheduler_runs" ON scheduler_runs;
CREATE POLICY "Allow full access to scheduler_runs" ON scheduler_runs FOR ALL USING (true) WITH CHECK (true);

-- Permissions
GRANT ALL ON TABLE scheduler_runs TO anon, authenticated, service_role;

