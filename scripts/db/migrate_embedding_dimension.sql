-- Migration script to update embedding dimension from 1536 to 3072
-- This is required when switching from text-embedding-3-small to text-embedding-3-large
--
-- WARNING: This migration will:
-- 1. Drop existing embeddings (they need to be regenerated with the new model)
-- 2. Change the vector column dimension
-- 3. Require re-ingestion of all documents
--
-- Usage:
--   psql -U postgres -d noc_agent_ai -f scripts/db/migrate_embedding_dimension.sql
--
-- Before running:
--   1. Backup your database
--   2. Update config/embeddings.json to use "text-embedding-3-large"
--   3. Ensure all services are stopped
--
-- After running:
--   1. Re-run ingestion scripts to regenerate embeddings with new dimension
--   2. Verify embeddings are generated correctly

BEGIN;

-- Step 1: Drop existing embeddings (they're incompatible with new dimension)
UPDATE chunks SET embedding = NULL;

-- Step 2: Drop the old vector column
ALTER TABLE chunks DROP COLUMN IF EXISTS embedding;

-- Step 3: Create new vector column with 3072 dimensions
ALTER TABLE chunks ADD COLUMN embedding vector(3072);

-- Step 4: Recreate the index with new dimension
DROP INDEX IF EXISTS chunks_embedding_idx;
CREATE INDEX chunks_embedding_idx ON chunks 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

COMMIT;

-- Verification query (run after migration):
-- SELECT COUNT(*) as total_chunks, 
--        COUNT(embedding) as chunks_with_embeddings
-- FROM chunks;

