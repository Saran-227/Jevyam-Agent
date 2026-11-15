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
TO public
USING (bucket_id = 'post-images');

-- 3. Allow ONLY service_role uploads (INSERT) into post-images bucket
DROP POLICY IF EXISTS "Allow Upload to post-images" ON storage.objects;
DROP POLICY IF EXISTS "Service Role Upload to post-images" ON storage.objects;
CREATE POLICY "Service Role Upload to post-images"
ON storage.objects FOR INSERT
TO service_role
WITH CHECK (bucket_id = 'post-images');

-- 4. Allow ONLY service_role updates/upserts into post-images bucket
DROP POLICY IF EXISTS "Allow Update in post-images" ON storage.objects;
DROP POLICY IF EXISTS "Service Role Update in post-images" ON storage.objects;
CREATE POLICY "Service Role Update in post-images"
ON storage.objects FOR UPDATE
TO service_role
USING (bucket_id = 'post-images')
WITH CHECK (bucket_id = 'post-images');

-- 5. Allow ONLY service_role deletions from post-images bucket
DROP POLICY IF EXISTS "Allow Delete from post-images" ON storage.objects;
DROP POLICY IF EXISTS "Service Role Delete from post-images" ON storage.objects;
CREATE POLICY "Service Role Delete from post-images"
ON storage.objects FOR DELETE
TO service_role
USING (bucket_id = 'post-images');
