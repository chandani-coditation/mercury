-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- documents: runbooks, past incident reports, SOPs
CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_type TEXT NOT NULL,
  service TEXT,
  component TEXT,
  title TEXT,
  content TEXT,
  tags JSONB,
  last_reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- chunks: RAG-ready pieces
CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INT,
  content TEXT NOT NULL,
  metadata JSONB,
  embedding vector(1536), -- OpenAI text-embedding-3-small uses 1536 dimensions
  tsv tsvector,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- incidents: for storing AI triage info
CREATE TABLE IF NOT EXISTS incidents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id TEXT,
  source TEXT,
  raw_alert JSONB,
  triage_output JSONB,
  triage_evidence JSONB, -- Evidence chunks used by triager agent
  resolution_output JSONB,
  resolution_evidence JSONB, -- Evidence chunks used by resolution copilot agent
  policy_band TEXT, -- AUTO, PROPOSE, or REVIEW
  policy_decision JSONB, -- Full policy decision JSON
  alert_received_at TIMESTAMPTZ,
  triage_completed_at TIMESTAMPTZ,
  resolution_proposed_at TIMESTAMPTZ,
  resolution_accepted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- feedback: for human-in-the-loop edits
CREATE TABLE IF NOT EXISTS feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  feedback_type TEXT, -- 'triage' or 'resolution'
  system_output JSONB,
  user_edited JSONB,
  diff JSONB,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks(document_id);
CREATE INDEX IF NOT EXISTS incidents_alert_id_idx ON incidents(alert_id);
CREATE INDEX IF NOT EXISTS incidents_created_at_idx ON incidents(created_at);
CREATE INDEX IF NOT EXISTS incidents_policy_band_idx ON incidents(policy_band);
CREATE INDEX IF NOT EXISTS feedback_incident_id_idx ON feedback(incident_id);
CREATE INDEX IF NOT EXISTS feedback_feedback_type_idx ON feedback(feedback_type);

-- View for MTTR metrics
CREATE OR REPLACE VIEW incident_metrics AS
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



