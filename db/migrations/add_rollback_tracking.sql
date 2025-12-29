-- Migration: Add rollback tracking fields to incidents table
-- Date: 2025-12-29
-- Description: Adds columns for tracking rollback execution in production environments

-- Add rollback tracking columns to incidents table
ALTER TABLE incidents 
ADD COLUMN IF NOT EXISTS rollback_initiated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS rollback_completed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS rollback_status TEXT,
ADD COLUMN IF NOT EXISTS rollback_trigger TEXT,
ADD COLUMN IF NOT EXISTS rollback_notes TEXT;

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS incidents_rollback_status_idx ON incidents(rollback_status);
CREATE INDEX IF NOT EXISTS incidents_rollback_initiated_at_idx ON incidents(rollback_initiated_at);

-- Add check constraint for valid rollback_status values
ALTER TABLE incidents 
DROP CONSTRAINT IF EXISTS incidents_rollback_status_check;

ALTER TABLE incidents 
ADD CONSTRAINT incidents_rollback_status_check 
CHECK (rollback_status IS NULL OR rollback_status IN (
    'not_required', 
    'initiated', 
    'in_progress', 
    'completed', 
    'failed', 
    'cancelled'
));

-- Set default rollback_status for existing records
UPDATE incidents 
SET rollback_status = 'not_required' 
WHERE rollback_status IS NULL 
  AND resolution_accepted_at IS NOT NULL;

COMMENT ON COLUMN incidents.rollback_initiated_at IS 'Timestamp when rollback was triggered';
COMMENT ON COLUMN incidents.rollback_completed_at IS 'Timestamp when rollback finished successfully';
COMMENT ON COLUMN incidents.rollback_status IS 'Current status of rollback: not_required, initiated, in_progress, completed, failed, cancelled';
COMMENT ON COLUMN incidents.rollback_trigger IS 'What triggered the rollback (e.g., manual, health_check_failed, error_threshold_exceeded)';
COMMENT ON COLUMN incidents.rollback_notes IS 'Human notes about rollback execution and outcomes';

