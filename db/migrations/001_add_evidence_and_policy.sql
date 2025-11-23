-- Migration: Add evidence chunks and policy decision columns
-- This adds support for storing retrieval evidence and policy decisions

-- Add evidence and policy columns to incidents table
ALTER TABLE incidents 
  ADD COLUMN IF NOT EXISTS triage_evidence JSONB,
  ADD COLUMN IF NOT EXISTS resolution_evidence JSONB,
  ADD COLUMN IF NOT EXISTS policy_band TEXT,
  ADD COLUMN IF NOT EXISTS policy_decision JSONB;

-- Add feedback_type column to feedback table
ALTER TABLE feedback 
  ADD COLUMN IF NOT EXISTS feedback_type TEXT;

-- Add comments for documentation
COMMENT ON COLUMN incidents.triage_evidence IS 'Evidence chunks used by triager agent (chunks, sources, retrieval method)';
COMMENT ON COLUMN incidents.resolution_evidence IS 'Evidence chunks used by resolution copilot agent (chunks, sources, retrieval method)';
COMMENT ON COLUMN incidents.policy_band IS 'Policy decision band: AUTO, PROPOSE, or REVIEW';
COMMENT ON COLUMN incidents.policy_decision IS 'Full policy decision JSON including can_auto_apply, requires_approval, etc.';
COMMENT ON COLUMN feedback.feedback_type IS 'Type of feedback: triage or resolution';

-- Create index on policy_band for filtering
CREATE INDEX IF NOT EXISTS incidents_policy_band_idx ON incidents(policy_band);

-- Drop and recreate incident_metrics view to include policy_band
DROP VIEW IF EXISTS incident_metrics;

CREATE VIEW incident_metrics AS
SELECT
  id,
  alert_id,
  alert_received_at,
  triage_completed_at,
  resolution_proposed_at,
  resolution_accepted_at,
  policy_band,
  EXTRACT(EPOCH FROM (triage_completed_at - alert_received_at)) AS triage_secs,
  EXTRACT(EPOCH FROM (resolution_proposed_at - alert_received_at)) AS resolution_proposed_secs,
  CASE 
    WHEN resolution_accepted_at IS NOT NULL 
    THEN EXTRACT(EPOCH FROM (resolution_accepted_at - alert_received_at))
    ELSE NULL
  END AS mttr_secs
FROM incidents;

