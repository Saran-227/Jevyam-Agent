-- ==============================================================================
-- Migration 002: Publications Table (Phase 5 — LinkedIn Publishing Layer)
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_publications_post_id ON publications(post_id);
CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status);
CREATE INDEX IF NOT EXISTS idx_publications_created_at ON publications(created_at DESC);

-- Row Level Security
ALTER TABLE publications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow full access to publications" ON publications;
CREATE POLICY "Allow full access to publications" ON publications FOR ALL USING (true) WITH CHECK (true);

-- Table Grants for Supabase anon / authenticated / service_role
GRANT ALL ON TABLE publications TO anon, authenticated, service_role;
