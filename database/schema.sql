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
-- 7. INDEXES
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


-- ==============================================================================
-- 8. ROW LEVEL SECURITY (RLS) POLICIES
-- Enable RLS and establish backend service access policies
-- ==============================================================================
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE post_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE publications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow full access to companies" ON companies;
CREATE POLICY "Allow full access to companies" ON companies FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to posts" ON posts;
CREATE POLICY "Allow full access to posts" ON posts FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to post_revisions" ON post_revisions;
CREATE POLICY "Allow full access to post_revisions" ON post_revisions FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to approvals" ON approvals;
CREATE POLICY "Allow full access to approvals" ON approvals FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access to publications" ON publications;
CREATE POLICY "Allow full access to publications" ON publications FOR ALL USING (true) WITH CHECK (true);


