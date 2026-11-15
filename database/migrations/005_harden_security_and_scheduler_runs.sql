-- ==============================================================================
-- Migration 005: Comprehensive Security Hardening & Scheduler Runs Migration
--
-- Safe, idempotent migration to:
-- 1. Ensure update_updated_at_column() trigger function exists.
-- 2. Revoke table privileges from PUBLIC, anon, and authenticated on agent tables.
-- 3. Grant full table privileges strictly to service_role.
-- 4. Drop insecure unrestricted policies and replace with service_role-only policies.
-- 5. Enable Row Level Security (RLS) on all agent tables.
-- 6. Harden 'post-images' storage bucket: public SELECT, service_role write only.
-- 7. Create 'scheduler_runs' table with unique execution_key and service_role RLS.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. ENSURE TRIGGER FUNCTION EXISTS
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.update_updated_at_column() TO service_role, postgres;


-- ------------------------------------------------------------------------------
-- 2. REVOKE ALL PRIVILEGES ON APPLICATION TABLES FROM PUBLIC, anon, AND authenticated
-- (Surgically scoped to application tables to avoid impacting extensions or routines)
-- ------------------------------------------------------------------------------
REVOKE ALL ON TABLE public.companies FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.posts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.post_revisions FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.approvals FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.publications FROM PUBLIC, anon, authenticated;

-- Ensure service_role has full table privileges
GRANT ALL ON TABLE public.companies TO service_role;
GRANT ALL ON TABLE public.posts TO service_role;
GRANT ALL ON TABLE public.post_revisions TO service_role;
GRANT ALL ON TABLE public.approvals TO service_role;
GRANT ALL ON TABLE public.publications TO service_role;


-- ------------------------------------------------------------------------------
-- 3. DROP INSECURE UNRESTRICTED POLICIES ON EXISTING TABLES (Idempotent)
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Allow full access to companies" ON public.companies;
DROP POLICY IF EXISTS "Allow full access to posts" ON public.posts;
DROP POLICY IF EXISTS "Allow full access to post_revisions" ON public.post_revisions;
DROP POLICY IF EXISTS "Allow full access to approvals" ON public.approvals;
DROP POLICY IF EXISTS "Allow full access to publications" ON public.publications;

DROP POLICY IF EXISTS "Service Role full access on companies" ON public.companies;
DROP POLICY IF EXISTS "Service Role full access on posts" ON public.posts;
DROP POLICY IF EXISTS "Service Role full access on post_revisions" ON public.post_revisions;
DROP POLICY IF EXISTS "Service Role full access on approvals" ON public.approvals;
DROP POLICY IF EXISTS "Service Role full access on publications" ON public.publications;


-- ------------------------------------------------------------------------------
-- 4. ENSURE ROW LEVEL SECURITY IS ACTIVE ON ALL EXISTING TABLES
-- ------------------------------------------------------------------------------
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.post_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.publications ENABLE ROW LEVEL SECURITY;


-- ------------------------------------------------------------------------------
-- 5. CREATE RESTRICTED SERVICE_ROLE ONLY POLICIES
-- With no policies granted to PUBLIC, anon, or authenticated, RLS defaults to DENY ALL.
-- ------------------------------------------------------------------------------
CREATE POLICY "Service Role full access on companies"
    ON public.companies
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service Role full access on posts"
    ON public.posts
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service Role full access on post_revisions"
    ON public.post_revisions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service Role full access on approvals"
    ON public.approvals
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service Role full access on publications"
    ON public.publications
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- ------------------------------------------------------------------------------
-- 6. HARDEN STORAGE BUCKET POLICIES (post-images)
-- Public users may read (SELECT). Only service_role can upload, update, or delete.
-- ------------------------------------------------------------------------------
DROP POLICY IF EXISTS "Allow Upload to post-images" ON storage.objects;
DROP POLICY IF EXISTS "Allow Update in post-images" ON storage.objects;
DROP POLICY IF EXISTS "Allow Delete from post-images" ON storage.objects;
DROP POLICY IF EXISTS "Public Read Access on post-images" ON storage.objects;
DROP POLICY IF EXISTS "Public read on post-images" ON storage.objects;
DROP POLICY IF EXISTS "Service Role Upload to post-images" ON storage.objects;
DROP POLICY IF EXISTS "Service Role Update in post-images" ON storage.objects;
DROP POLICY IF EXISTS "Service Role Delete from post-images" ON storage.objects;

-- Allow public read access to post visuals (needed for Telegram preview & LinkedIn fetch)
CREATE POLICY "Public Read Access on post-images"
    ON storage.objects
    FOR SELECT
    TO public
    USING (bucket_id = 'post-images');

-- Allow ONLY trusted service_role to upload images
CREATE POLICY "Service Role Upload to post-images"
    ON storage.objects
    FOR INSERT
    TO service_role
    WITH CHECK (bucket_id = 'post-images');

-- Allow ONLY trusted service_role to update/upsert images
CREATE POLICY "Service Role Update in post-images"
    ON storage.objects
    FOR UPDATE
    TO service_role
    USING (bucket_id = 'post-images')
    WITH CHECK (bucket_id = 'post-images');

-- Allow ONLY trusted service_role to delete images
CREATE POLICY "Service Role Delete from post-images"
    ON storage.objects
    FOR DELETE
    TO service_role
    USING (bucket_id = 'post-images');


-- ------------------------------------------------------------------------------
-- 7. SCHEDULER RUNS TABLE CREATION & SECURITY (Idempotent)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.scheduler_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_key TEXT UNIQUE NOT NULL,                   -- e.g. DAILY-RUN-20261112
    date TEXT NOT NULL,                                   -- e.g. 2026-11-12
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'SKIPPED', 'FAILED')),
    post_id TEXT REFERENCES public.posts(post_id) ON DELETE SET NULL,
    revision INTEGER,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    is_missed_run_recovery BOOLEAN NOT NULL DEFAULT false,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.scheduler_runs IS 'Tracks daily marketing agent generation executions for idempotency and disaster recovery';
COMMENT ON COLUMN public.scheduler_runs.execution_key IS 'Unique key per Indian calendar date (DAILY-RUN-YYYYMMDD)';
COMMENT ON COLUMN public.scheduler_runs.status IS 'RUNNING, SUCCESS, SKIPPED, or FAILED';

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_date ON public.scheduler_runs(date);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON public.scheduler_runs(status);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_execution_key ON public.scheduler_runs(execution_key);

-- Attach update_updated_at_column trigger
DROP TRIGGER IF EXISTS trigger_scheduler_runs_updated_at ON public.scheduler_runs;
CREATE TRIGGER trigger_scheduler_runs_updated_at
    BEFORE UPDATE ON public.scheduler_runs
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- Revoke all permissions on scheduler_runs from PUBLIC, anon, and authenticated
REVOKE ALL ON TABLE public.scheduler_runs FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.scheduler_runs TO service_role;

-- Enable RLS and restrict strictly to service_role
ALTER TABLE public.scheduler_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow full access to scheduler_runs" ON public.scheduler_runs;
DROP POLICY IF EXISTS "Service Role full access on scheduler_runs" ON public.scheduler_runs;

CREATE POLICY "Service Role full access on scheduler_runs"
    ON public.scheduler_runs
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
