-- ==============================================================================
-- Jevyam Technologies AI Marketing Agent: PostgreSQL / Supabase Schema
-- Phase 2 Database Setup: Companies, Posts, Revisions, and Approvals
-- ==============================================================================

-- 1. EXTENSIONS & UTILITIES
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Reusable trigger function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ==============================================================================
-- 2. COMPANIES TABLE
-- Stores organizational entities (default: Jevyam Technologies)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Comments
COMMENT ON TABLE companies IS 'Organizational entities owning marketing agents and content';
COMMENT ON COLUMN companies.slug IS 'Unique URL-safe company identifier';

-- Automatically maintain updated_at on companies
DROP TRIGGER IF EXISTS trigger_companies_updated_at ON companies;
CREATE TRIGGER trigger_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Seed Default Company
INSERT INTO companies (name, slug)
VALUES ('Jevyam Technologies', 'jevyam')
ON CONFLICT (slug) DO NOTHING;


-- ==============================================================================
-- 3. POSTS TABLE
-- Master record of each generated post representing its current state
-- ==============================================================================
CREATE TABLE IF NOT EXISTS posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id TEXT UNIQUE NOT NULL,                         -- Human-readable ID, e.g. JVY-20260929-001
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
        'DRAFT',
        'PENDING_APPROVAL',
        'REJECTED',
        'REGENERATING',
        'APPROVED',
        'PUBLISHED',
        'FAILED'
    )),
    current_revision INTEGER NOT NULL DEFAULT 1 CHECK (current_revision >= 1),
    content_type TEXT NOT NULL,
    topic TEXT NOT NULL,
    angle TEXT NOT NULL,
    target_audience TEXT NOT NULL,
    hook TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT[] NOT NULL DEFAULT '{}',
    call_to_action TEXT NOT NULL,
    visual_concept TEXT NOT NULL,
    image_brief JSONB NOT NULL DEFAULT '{}',
    image_url TEXT,
    linkedin_post_id TEXT,
    linkedin_target TEXT NOT NULL DEFAULT 'COMPANY_PAGE' CHECK (linkedin_target IN ('FOUNDER', 'COMPANY_PAGE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ
);

COMMENT ON TABLE posts IS 'Master records of LinkedIn posts and their current workflow states';
COMMENT ON COLUMN posts.post_id IS 'Business post identifier (e.g. JVY-YYYYMMDD-XXX)';
COMMENT ON COLUMN posts.status IS 'Lifecycle status (DRAFT, PENDING_APPROVAL, REJECTED, REGENERATING, APPROVED, PUBLISHED, FAILED)';
COMMENT ON COLUMN posts.current_revision IS 'Current active revision number';
COMMENT ON COLUMN posts.hashtags IS 'Array of hashtags formatted with leading #';
COMMENT ON COLUMN posts.image_brief IS 'Structured design specification as JSON';
COMMENT ON COLUMN posts.linkedin_target IS 'Destination target: FOUNDER profile or COMPANY_PAGE';

-- Automatically maintain updated_at on posts
DROP TRIGGER IF EXISTS trigger_posts_updated_at ON posts;
CREATE TRIGGER trigger_posts_updated_at
    BEFORE UPDATE ON posts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ==============================================================================
-- 4. POST REVISIONS TABLE
-- Preserves complete history of all draft iterations across regenerations
-- ==============================================================================
CREATE TABLE IF NOT EXISTS post_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
    topic TEXT NOT NULL,
    angle TEXT NOT NULL,
    content_type TEXT NOT NULL,
    target_audience TEXT NOT NULL,
    hook TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT[] NOT NULL DEFAULT '{}',
    call_to_action TEXT NOT NULL,
    visual_concept TEXT NOT NULL,
    image_brief JSONB NOT NULL DEFAULT '{}',
    image_url TEXT,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_post_revision UNIQUE (post_id, revision_number)
);

COMMENT ON TABLE post_revisions IS 'Immutable historical snapshot of each revision iteration of a post';
COMMENT ON COLUMN post_revisions.revision_number IS 'Sequential revision counter starting at 1';
COMMENT ON COLUMN post_revisions.rejection_reason IS 'Feedback from founder explaining rejection if applicable';


-- ==============================================================================
-- 5. APPROVALS TABLE
-- Prepares approval workflow tokens and verification records for Phase 3
-- ==============================================================================
CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    approval_token TEXT UNIQUE NOT NULL,                  -- Secure random token (e.g. appr_...)
    expires_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE approvals IS 'Approval tokens and audit trail for founder verification via WhatsApp or Webhook';
COMMENT ON COLUMN approvals.approval_token IS 'Cryptographically secure random token for approval/rejection actions';


-- ==============================================================================
-- 6. PUBLICATIONS TABLE
-- Audit log of external social media publication dispatches and results (Phase 5)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS publications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    platform TEXT NOT NULL DEFAULT 'LINKEDIN',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PUBLISHED', 'FAILED')),
    external_post_id TEXT,
    target_urn TEXT,
    error_message TEXT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE publications IS 'Audit log of external social media publication dispatches and results';
COMMENT ON COLUMN publications.external_post_id IS 'External platform post ID / URN (e.g. urn:li:share:12345678)';
COMMENT ON COLUMN publications.target_urn IS 'Destination entity URN (e.g. urn:li:organization:12345)';


-- ==============================================================================
-- 7. SCHEDULER RUNS TABLE
-- Tracks daily automated execution cycles to guarantee strict idempotency
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

DROP TRIGGER IF EXISTS trigger_scheduler_runs_updated_at ON scheduler_runs;
CREATE TRIGGER trigger_scheduler_runs_updated_at
    BEFORE UPDATE ON scheduler_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ==============================================================================
-- 8. INDEXES
-- Optimize querying by post_id, status, dates, and approval tokens
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_posts_post_id ON posts(post_id);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_company_id ON posts(company_id);

CREATE INDEX IF NOT EXISTS idx_post_revisions_post_id ON post_revisions(post_id);
CREATE INDEX IF NOT EXISTS idx_post_revisions_created_at ON post_revisions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_approvals_token ON approvals(approval_token);
CREATE INDEX IF NOT EXISTS idx_approvals_post_id ON approvals(post_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE INDEX IF NOT EXISTS idx_publications_post_id ON publications(post_id);
CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status);
CREATE INDEX IF NOT EXISTS idx_publications_created_at ON publications(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_date ON scheduler_runs(date);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_runs(status);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_execution_key ON scheduler_runs(execution_key);

-- ==============================================================================
-- 9. ROW LEVEL SECURITY (RLS) POLICIES
-- Enable strict RLS: access restricted solely to backend service_role
-- ==============================================================================
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduler_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow full access to companies" ON companies;
DROP POLICY IF EXISTS "Service Role full access on companies" ON companies;
CREATE POLICY "Service Role full access on companies" ON companies FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to posts" ON posts;
DROP POLICY IF EXISTS "Service Role full access on posts" ON posts;
CREATE POLICY "Service Role full access on posts" ON posts FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to post_revisions" ON post_revisions;
DROP POLICY IF EXISTS "Service Role full access on post_revisions" ON post_revisions;
CREATE POLICY "Service Role full access on post_revisions" ON post_revisions FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to approvals" ON approvals;
DROP POLICY IF EXISTS "Service Role full access on approvals" ON approvals;
CREATE POLICY "Service Role full access on approvals" ON approvals FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to publications" ON publications;
DROP POLICY IF EXISTS "Service Role full access on publications" ON publications;
CREATE POLICY "Service Role full access on publications" ON publications FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to scheduler_runs" ON scheduler_runs;
DROP POLICY IF EXISTS "Service Role full access on scheduler_runs" ON scheduler_runs;
CREATE POLICY "Service Role full access on scheduler_runs" ON scheduler_runs FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ==============================================================================
-- 10. PERMISSIONS / GRANTS
-- Strictly grant table privileges to service_role; revoke from anon and authenticated
-- ==============================================================================
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM anon, authenticated;

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;


