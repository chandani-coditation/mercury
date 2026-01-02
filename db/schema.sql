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
-- For runbooks: each chunk represents an atomic runbook step
-- For incidents: each chunk represents an incident signature (not raw incident text)
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

-- Indexes for runbook steps and incident signatures
-- Index on metadata fields for efficient filtering
CREATE INDEX IF NOT EXISTS chunks_metadata_runbook_id_idx ON chunks USING GIN ((metadata->'runbook_id')) WHERE metadata->>'runbook_id' IS NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_metadata_step_id_idx ON chunks USING GIN ((metadata->'step_id')) WHERE metadata->>'step_id' IS NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_metadata_incident_signature_id_idx ON chunks USING GIN ((metadata->'incident_signature_id')) WHERE metadata->>'incident_signature_id' IS NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_metadata_failure_type_idx ON chunks USING GIN ((metadata->'failure_type')) WHERE metadata->>'failure_type' IS NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_metadata_error_class_idx ON chunks USING GIN ((metadata->'error_class')) WHERE metadata->>'error_class' IS NOT NULL;

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
  -- Rollback tracking fields
  rollback_initiated_at TIMESTAMPTZ, -- When rollback was triggered
  rollback_completed_at TIMESTAMPTZ, -- When rollback finished
  rollback_status TEXT, -- 'not_required', 'initiated', 'in_progress', 'completed', 'failed'
  rollback_trigger TEXT, -- What triggered the rollback (e.g., 'manual', 'health_check_failed', 'error_threshold_exceeded')
  rollback_notes TEXT, -- Human notes about rollback execution
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

-- agent_state: for state-based HITL persistence
CREATE TABLE IF NOT EXISTS agent_state (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  agent_type TEXT NOT NULL, -- 'triage' or 'resolution'
  current_step TEXT NOT NULL,
  state_data JSONB NOT NULL, -- Full AgentState as JSON
  pending_action JSONB, -- PendingAction as JSON if paused
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks(document_id);
CREATE INDEX IF NOT EXISTS incidents_alert_id_idx ON incidents(alert_id);
CREATE INDEX IF NOT EXISTS incidents_created_at_idx ON incidents(created_at);
CREATE INDEX IF NOT EXISTS incidents_policy_band_idx ON incidents(policy_band);
CREATE INDEX IF NOT EXISTS incidents_rollback_status_idx ON incidents(rollback_status);
CREATE INDEX IF NOT EXISTS incidents_rollback_initiated_at_idx ON incidents(rollback_initiated_at);
CREATE INDEX IF NOT EXISTS feedback_incident_id_idx ON feedback(incident_id);
CREATE INDEX IF NOT EXISTS feedback_feedback_type_idx ON feedback(feedback_type);
CREATE INDEX IF NOT EXISTS agent_state_incident_id_idx ON agent_state(incident_id);
CREATE INDEX IF NOT EXISTS agent_state_agent_type_idx ON agent_state(agent_type);
CREATE INDEX IF NOT EXISTS agent_state_current_step_idx ON agent_state(current_step);
CREATE INDEX IF NOT EXISTS agent_state_updated_at_idx ON agent_state(updated_at);
CREATE INDEX IF NOT EXISTS agent_state_pending_action_idx ON agent_state USING GIN (pending_action) WHERE pending_action IS NOT NULL;

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

-- Function to update updated_at timestamp for agent_state
CREATE OR REPLACE FUNCTION update_agent_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at for agent_state
CREATE TRIGGER agent_state_updated_at_trigger
  BEFORE UPDATE ON agent_state
  FOR EACH ROW
  EXECUTE FUNCTION update_agent_state_updated_at();

-- ============================================================================
-- Storage & Vector Schema Tables
-- ============================================================================
-- These tables support semantic search and structured storage for:
--   - runbook_steps: Atomic operational knowledge with vector embeddings
--   - incident_signatures: Failure patterns with vector embeddings
--   - triage_results: Classification outputs with provenance
--   - resolution_outputs: Recommendations with clear provenance
-- ============================================================================

-- runbook_steps: Atomic runbook steps for Resolution Agent retrieval
CREATE TABLE IF NOT EXISTS runbook_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id TEXT NOT NULL UNIQUE,
    runbook_id TEXT NOT NULL,
    condition TEXT NOT NULL,
    action TEXT NOT NULL,
    expected_outcome TEXT,
    rollback TEXT,
    risk_level TEXT,
    service TEXT,
    component TEXT,
    embedding vector(1536),
    tsv tsvector,
    runbook_title TEXT,
    runbook_document_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_reviewed_at TIMESTAMPTZ,
    CONSTRAINT runbook_steps_risk_level_check 
        CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high'))
);

-- incident_signatures: Failure patterns for Triage Agent classification
CREATE TABLE IF NOT EXISTS incident_signatures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_signature_id TEXT NOT NULL UNIQUE,
    failure_type TEXT NOT NULL,
    error_class TEXT NOT NULL,
    symptoms TEXT[] NOT NULL,
    affected_service TEXT,
    service TEXT,
    component TEXT,
    assignment_group TEXT, -- Team/group that handles this type of incident (e.g., "SE DBA SQL", "NOC")
    impact TEXT, -- Typical impact value from historical incidents (e.g., "3 - Low", "1 - High")
    urgency TEXT, -- Typical urgency value from historical incidents (e.g., "3 - Low", "1 - High")
    close_notes TEXT, -- Resolution notes/close notes from historical incidents (for resolution agent)
    resolution_refs TEXT[],
    embedding vector(1536),
    tsv tsvector,
    source_incident_ids TEXT[],
    source_document_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ,
    match_count INTEGER DEFAULT 0,
    resolution_success_count INTEGER DEFAULT 0,
    CONSTRAINT incident_signatures_symptoms_not_empty 
        CHECK (array_length(symptoms, 1) > 0)
);

-- triage_results: Classification outputs from Triage Agent
CREATE TABLE IF NOT EXISTS triage_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    failure_type TEXT NOT NULL,
    error_class TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    policy_band TEXT NOT NULL,
    assignment_group TEXT, -- Team/group assigned to handle this incident (e.g., "SE DBA SQL", "NOC")
    impact TEXT, -- Original impact value from alert (e.g., "3 - Low", "1 - High")
    urgency TEXT, -- Original urgency value from alert (e.g., "3 - Low", "1 - High")
    matched_signature_ids TEXT[],
    matched_runbook_refs TEXT[],
    evidence_chunks JSONB,
    retrieval_method TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT triage_results_confidence_range 
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT triage_results_severity_check 
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT triage_results_policy_band_check 
        CHECK (policy_band IN ('AUTO', 'PROPOSE', 'REVIEW'))
);

-- resolution_outputs: Recommendations from Resolution Agent
CREATE TABLE IF NOT EXISTS resolution_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    triage_result_id UUID NOT NULL REFERENCES triage_results(id) ON DELETE CASCADE,
    overall_confidence NUMERIC(5,4) NOT NULL,
    risk_level TEXT NOT NULL,
    recommendations JSONB NOT NULL,
    retrieved_step_ids TEXT[],
    used_signature_ids TEXT[],
    evidence_chunks JSONB,
    retrieval_method TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    proposed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    execution_status TEXT,
    execution_notes TEXT,
    CONSTRAINT resolution_outputs_overall_confidence_range 
        CHECK (overall_confidence >= 0.0 AND overall_confidence <= 1.0),
    CONSTRAINT resolution_outputs_risk_level_check 
        CHECK (risk_level IN ('low', 'medium', 'high')),
    CONSTRAINT resolution_outputs_execution_status_check 
        CHECK (execution_status IS NULL OR execution_status IN 
            ('pending', 'accepted', 'executed', 'rejected', 'cancelled'))
);

-- Indexes for runbook_steps
CREATE INDEX IF NOT EXISTS runbook_steps_embedding_idx 
    ON runbook_steps 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100)
    WHERE embedding IS NOT NULL;
CREATE INDEX IF NOT EXISTS runbook_steps_tsv_idx 
    ON runbook_steps 
    USING GIN (tsv)
    WHERE tsv IS NOT NULL;
CREATE INDEX IF NOT EXISTS runbook_steps_runbook_document_id_idx 
    ON runbook_steps(runbook_document_id)
    WHERE runbook_document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS runbook_steps_runbook_id_idx 
    ON runbook_steps(runbook_id);
CREATE INDEX IF NOT EXISTS runbook_steps_service_idx 
    ON runbook_steps(service) 
    WHERE service IS NOT NULL;
CREATE INDEX IF NOT EXISTS runbook_steps_component_idx 
    ON runbook_steps(component) 
    WHERE component IS NOT NULL;
CREATE INDEX IF NOT EXISTS runbook_steps_risk_level_idx 
    ON runbook_steps(risk_level) 
    WHERE risk_level IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS runbook_steps_step_id_unique_idx 
    ON runbook_steps(step_id);

-- Indexes for incident_signatures
CREATE INDEX IF NOT EXISTS incident_signatures_embedding_idx 
    ON incident_signatures 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100)
    WHERE embedding IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_tsv_idx 
    ON incident_signatures 
    USING GIN (tsv)
    WHERE tsv IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_source_document_id_idx 
    ON incident_signatures(source_document_id)
    WHERE source_document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_failure_type_idx 
    ON incident_signatures(failure_type);
CREATE INDEX IF NOT EXISTS incident_signatures_error_class_idx 
    ON incident_signatures(error_class);
CREATE INDEX IF NOT EXISTS incident_signatures_affected_service_idx 
    ON incident_signatures(affected_service) 
    WHERE affected_service IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_service_idx 
    ON incident_signatures(service) 
    WHERE service IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_component_idx 
    ON incident_signatures(component) 
    WHERE component IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_assignment_group_idx 
    ON incident_signatures(assignment_group) 
    WHERE assignment_group IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_impact_idx 
    ON incident_signatures(impact) 
    WHERE impact IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_urgency_idx 
    ON incident_signatures(urgency) 
    WHERE urgency IS NOT NULL;
CREATE INDEX IF NOT EXISTS incident_signatures_symptoms_idx 
    ON incident_signatures 
    USING GIN (symptoms);
CREATE INDEX IF NOT EXISTS incident_signatures_resolution_refs_idx 
    ON incident_signatures 
    USING GIN (resolution_refs);
CREATE UNIQUE INDEX IF NOT EXISTS incident_signatures_signature_id_unique_idx 
    ON incident_signatures(incident_signature_id);

-- Indexes for triage_results
CREATE INDEX IF NOT EXISTS triage_results_incident_id_idx 
    ON triage_results(incident_id);
CREATE INDEX IF NOT EXISTS triage_results_failure_type_idx 
    ON triage_results(failure_type);
CREATE INDEX IF NOT EXISTS triage_results_error_class_idx 
    ON triage_results(error_class);
CREATE INDEX IF NOT EXISTS triage_results_severity_idx 
    ON triage_results(severity);
CREATE INDEX IF NOT EXISTS triage_results_policy_band_idx 
    ON triage_results(policy_band);
CREATE INDEX IF NOT EXISTS triage_results_confidence_idx 
    ON triage_results(confidence);
CREATE INDEX IF NOT EXISTS triage_results_matched_signature_ids_idx 
    ON triage_results 
    USING GIN (matched_signature_ids);
CREATE INDEX IF NOT EXISTS triage_results_created_at_idx 
    ON triage_results(created_at);
CREATE INDEX IF NOT EXISTS triage_results_completed_at_idx 
    ON triage_results(completed_at) 
    WHERE completed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS triage_results_assignment_group_idx 
    ON triage_results(assignment_group) 
    WHERE assignment_group IS NOT NULL;
CREATE INDEX IF NOT EXISTS triage_results_impact_idx 
    ON triage_results(impact) 
    WHERE impact IS NOT NULL;
CREATE INDEX IF NOT EXISTS triage_results_urgency_idx 
    ON triage_results(urgency) 
    WHERE urgency IS NOT NULL;

-- Indexes for resolution_outputs
CREATE INDEX IF NOT EXISTS resolution_outputs_incident_id_idx 
    ON resolution_outputs(incident_id);
CREATE INDEX IF NOT EXISTS resolution_outputs_triage_result_id_idx 
    ON resolution_outputs(triage_result_id);
CREATE INDEX IF NOT EXISTS resolution_outputs_risk_level_idx 
    ON resolution_outputs(risk_level);
CREATE INDEX IF NOT EXISTS resolution_outputs_overall_confidence_idx 
    ON resolution_outputs(overall_confidence);
CREATE INDEX IF NOT EXISTS resolution_outputs_execution_status_idx 
    ON resolution_outputs(execution_status) 
    WHERE execution_status IS NOT NULL;
CREATE INDEX IF NOT EXISTS resolution_outputs_retrieved_step_ids_idx 
    ON resolution_outputs 
    USING GIN (retrieved_step_ids);
CREATE INDEX IF NOT EXISTS resolution_outputs_used_signature_ids_idx 
    ON resolution_outputs 
    USING GIN (used_signature_ids);
CREATE INDEX IF NOT EXISTS resolution_outputs_recommendations_idx 
    ON resolution_outputs 
    USING GIN (recommendations);
CREATE INDEX IF NOT EXISTS resolution_outputs_created_at_idx 
    ON resolution_outputs(created_at);
CREATE INDEX IF NOT EXISTS resolution_outputs_proposed_at_idx 
    ON resolution_outputs(proposed_at) 
    WHERE proposed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS resolution_outputs_accepted_at_idx 
    ON resolution_outputs(accepted_at) 
    WHERE accepted_at IS NOT NULL;

-- Functions for triggers
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_runbook_steps_tsv()
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv := to_tsvector('english', 
        COALESCE(NEW.condition, '') || ' ' || 
        COALESCE(NEW.action, '') || ' ' || 
        COALESCE(NEW.expected_outcome, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_incident_signatures_tsv()
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv := to_tsvector('english', 
        COALESCE(NEW.failure_type, '') || ' ' || 
        COALESCE(NEW.error_class, '') || ' ' || 
        COALESCE(NEW.assignment_group, '') || ' ' ||
        COALESCE(NEW.impact, '') || ' ' ||
        COALESCE(NEW.urgency, '') || ' ' ||
        COALESCE(array_to_string(NEW.symptoms, ' '), '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for runbook_steps
CREATE TRIGGER runbook_steps_updated_at_trigger
    BEFORE UPDATE ON runbook_steps
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER runbook_steps_tsv_trigger
    BEFORE INSERT OR UPDATE ON runbook_steps
    FOR EACH ROW
    EXECUTE FUNCTION update_runbook_steps_tsv();

-- Triggers for incident_signatures
CREATE TRIGGER incident_signatures_updated_at_trigger
    BEFORE UPDATE ON incident_signatures
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER incident_signatures_tsv_trigger
    BEFORE INSERT OR UPDATE ON incident_signatures
    FOR EACH ROW
    EXECUTE FUNCTION update_incident_signatures_tsv();

-- Helper views
CREATE OR REPLACE VIEW runbook_steps_with_metadata AS
SELECT 
    rs.id,
    rs.step_id,
    rs.runbook_id,
    rs.condition,
    rs.action,
    rs.expected_outcome,
    rs.rollback,
    rs.risk_level,
    rs.service,
    rs.component,
    rs.runbook_title,
    rs.created_at,
    rs.updated_at,
    rs.last_reviewed_at,
    d.title AS document_title,
    d.tags AS document_tags
FROM runbook_steps rs
LEFT JOIN documents d ON rs.runbook_document_id = d.id;

CREATE OR REPLACE VIEW triage_to_resolution_chain AS
SELECT 
    i.id AS incident_id,
    i.alert_id,
    tr.id AS triage_result_id,
    tr.failure_type,
    tr.error_class,
    tr.severity,
    tr.confidence AS triage_confidence,
    tr.policy_band,
    tr.matched_signature_ids,
    ro.id AS resolution_output_id,
    ro.overall_confidence AS resolution_confidence,
    ro.risk_level,
    ro.retrieved_step_ids,
    ro.execution_status,
    tr.completed_at AS triage_completed_at,
    ro.proposed_at AS resolution_proposed_at,
    ro.accepted_at AS resolution_accepted_at
FROM incidents i
LEFT JOIN triage_results tr ON i.id = tr.incident_id
LEFT JOIN resolution_outputs ro ON tr.id = ro.triage_result_id;

