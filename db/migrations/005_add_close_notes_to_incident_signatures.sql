-- Migration: Add close_notes column to incident_signatures table
-- Purpose: Store resolution notes/close notes from historical incidents for resolution agent

-- Add close_notes column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'incident_signatures' 
        AND column_name = 'close_notes'
    ) THEN
        ALTER TABLE incident_signatures 
        ADD COLUMN close_notes TEXT;
        
        COMMENT ON COLUMN incident_signatures.close_notes IS 
            'Resolution notes/close notes from historical incidents (for resolution agent)';
    END IF;
END $$;

