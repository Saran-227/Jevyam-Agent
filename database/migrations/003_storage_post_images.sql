-- ==============================================================================
-- Migration 003: Storage Bucket RLS Policies for 'post-images'
-- ==============================================================================

-- 1. Ensure the 'post-images' bucket exists and is marked public
INSERT INTO storage.buckets (id, name, public)
VALUES ('post-images', 'post-images', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- 2. Allow public read access to images stored in post-images bucket
DROP POLICY IF EXISTS "Public Read Access on post-images" ON storage.objects;
CREATE POLICY "Public Read Access on post-images"
ON storage.objects FOR SELECT
USING (bucket_id = 'post-images');

-- 3. Allow anon and service_role uploads (INSERT) into post-images bucket
DROP POLICY IF EXISTS "Allow Upload to post-images" ON storage.objects;
CREATE POLICY "Allow Upload to post-images"
ON storage.objects FOR INSERT
TO anon, authenticated, service_role
WITH CHECK (bucket_id = 'post-images');

-- 4. Allow anon and service_role updates/upserts into post-images bucket
DROP POLICY IF EXISTS "Allow Update in post-images" ON storage.objects;
CREATE POLICY "Allow Update in post-images"
ON storage.objects FOR UPDATE
TO anon, authenticated, service_role
USING (bucket_id = 'post-images')
WITH CHECK (bucket_id = 'post-images');
