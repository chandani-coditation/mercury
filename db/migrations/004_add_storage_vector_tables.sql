-- ============================================================================
-- Migration: Add Storage & Vector Schema Tables
-- Migration ID: 004
-- Date: 2025-01-XX
-- Description: Creates dedicated tables for runbook_steps, incident_signatures,
--              triage_results, and resolution_outputs with vector embeddings
-- ============================================================================
-- This migration adds the new storage and vector schema tables as designed
-- in schema_storage_vector_design.sql
--
-- IMPORTANT: This migration is idempotent (uses IF NOT EXISTS)
-- It can be run multiple times safely
-- ============================================================================

-- Enable required extensions (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. RUNBOOK_STEPS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS runbook_steps (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id TEXT NOT NULL UNIQUE,
    runbook_id TEXT NOT NULL,
    
    -- Step content (what gets embedded)
    condition TEXT NOT NULL,
    action TEXT NOT NULL,
    expected_outcome TEXT,
    rollback TEXT,
    
    -- Classification metadata
    risk_level TEXT,
    service TEXT,
    component TEXT,
    
    -- Vector embedding for semantic search
    embedding vector(1536),
    
    -- Full-text search support
    tsv tsvector,
    
    -- Provenance and metadata
    runbook_title TEXT,
    runbook_document_id UUID,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_reviewed_at TIMESTAMPTZ,
    
    -- Constraints
    CONSTRAINT runbook_steps_risk_level_check 
        CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high'))
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

-- Comments
COMMENT ON TABLE runbook_steps IS 
    'Atomic runbook steps stored independently for semantic retrieval by Resolution Agent';
COMMENT ON COLUMN runbook_steps.step_id IS 
    'Human-readable step identifier (e.g., RB123-S3)';
COMMENT ON COLUMN runbook_steps.embedding IS 
    'Vector embedding of condition + action + expected_outcome for semantic search';

-- ============================================================================
-- 2. INCIDENT_SIGNATURES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS incident_signatures (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_signature_id TEXT NOT NULL UNIQUE,
    
    -- Classification (what gets embedded)
    failure_type TEXT NOT NULL,
    error_class TEXT NOT NULL,
    symptoms TEXT[] NOT NULL,
    
    -- Context metadata
    affected_service TEXT,
    service TEXT,
    component TEXT,
    assignment_group TEXT, -- Team/group that handles this type of incident (e.g., "SE DBA SQL", "NOC")
    impact TEXT, -- Typical impact value from historical incidents (e.g., "3 - Low", "1 - High")
    urgency TEXT, -- Typical urgency value from historical incidents (e.g., "3 - Low", "1 - High")
    
    -- Resolution references (provenance)
    resolution_refs TEXT[],
    
    -- Vector embedding for semantic search
    embedding vector(1536),
    
    -- Full-text search support
    tsv tsvector,
    
    -- Provenance
    source_incident_ids TEXT[],
    source_document_id UUID,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ,
    
    -- Statistics (for ranking)
    match_count INTEGER DEFAULT 0,
    resolution_success_count INTEGER DEFAULT 0,
    
    -- Constraints
    CONSTRAINT incident_signatures_symptoms_not_empty 
        CHECK (array_length(symptoms, 1) > 0)
);

-- Add assignment_group, impact, urgency columns if table already exists without them
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'incident_signatures') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'incident_signatures' AND column_name = 'assignment_group') THEN
            ALTER TABLE incident_signatures ADD COLUMN assignment_group TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'incident_signatures' AND column_name = 'impact') THEN
            ALTER TABLE incident_signatures ADD COLUMN impact TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'incident_signatures' AND column_name = 'urgency') THEN
            ALTER TABLE incident_signatures ADD COLUMN urgency TEXT;
        END IF;
    END IF;
END $$;

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

-- Comments
COMMENT ON TABLE incident_signatures IS 
    'Failure patterns extracted from historical incidents, used by Triage Agent for classification';
COMMENT ON COLUMN incident_signatures.incident_signature_id IS 
    'Human-readable signature identifier (e.g., SIG-DB-001)';
COMMENT ON COLUMN incident_signatures.embedding IS 
    'Vector embedding of failure_type + error_class + symptoms for semantic pattern matching';

-- ============================================================================
-- 3. TRIAGE_RESULTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS triage_results (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL,
    
    -- Classification output (from Triage Agent)
    failure_type TEXT NOT NULL,
    error_class TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    
    -- Policy decision (derived from classification)
    policy_band TEXT NOT NULL,
    assignment_group TEXT, -- Team/group assigned to handle this incident (e.g., "SE DBA SQL", "NOC")
    impact TEXT, -- Original impact value from alert (e.g., "3 - Low", "1 - High")
    urgency TEXT, -- Original urgency value from alert (e.g., "3 - Low", "1 - High")
    
    -- Matched evidence (provenance)
    matched_signature_ids TEXT[],
    matched_runbook_refs TEXT[],
    
    -- Evidence metadata (for audit trail)
    evidence_chunks JSONB,
    retrieval_method TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    
    -- Constraints
    CONSTRAINT triage_results_confidence_range 
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT triage_results_severity_check 
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT triage_results_policy_band_check 
        CHECK (policy_band IN ('AUTO', 'PROPOSE', 'REVIEW'))
);

-- Add assignment_group, impact, urgency columns if table already exists without them
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'triage_results') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'triage_results' AND column_name = 'assignment_group') THEN
            ALTER TABLE triage_results ADD COLUMN assignment_group TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'triage_results' AND column_name = 'impact') THEN
            ALTER TABLE triage_results ADD COLUMN impact TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'triage_results' AND column_name = 'urgency') THEN
            ALTER TABLE triage_results ADD COLUMN urgency TEXT;
        END IF;
    END IF;
END $$;

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

-- Foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'triage_results_incident_id_fkey'
    ) THEN
        ALTER TABLE triage_results 
            ADD CONSTRAINT triage_results_incident_id_fkey 
            FOREIGN KEY (incident_id) 
            REFERENCES incidents(id) 
            ON DELETE CASCADE;
    END IF;
END $$;

-- Comments
COMMENT ON TABLE triage_results IS 
    'Classification outputs from Triage Agent, stored separately from incidents for clear provenance';
COMMENT ON COLUMN triage_results.matched_signature_ids IS 
    'Array of incident_signatures.incident_signature_id that matched during triage';

-- ============================================================================
-- 4. RESOLUTION_OUTPUTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS resolution_outputs (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL,
    triage_result_id UUID NOT NULL,
    
    -- Overall assessment
    overall_confidence NUMERIC(5,4) NOT NULL,
    risk_level TEXT NOT NULL,
    
    -- Recommendations (ordered list)
    recommendations JSONB NOT NULL,
    
    -- Provenance metadata
    retrieved_step_ids TEXT[],
    used_signature_ids TEXT[],
    
    -- Evidence metadata (for audit trail)
    evidence_chunks JSONB,
    retrieval_method TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    proposed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    
    -- Execution tracking
    execution_status TEXT,
    execution_notes TEXT,
    
    -- Constraints
    CONSTRAINT resolution_outputs_overall_confidence_range 
        CHECK (overall_confidence >= 0.0 AND overall_confidence <= 1.0),
    CONSTRAINT resolution_outputs_risk_level_check 
        CHECK (risk_level IN ('low', 'medium', 'high')),
    CONSTRAINT resolution_outputs_execution_status_check 
        CHECK (execution_status IS NULL OR execution_status IN 
            ('pending', 'accepted', 'executed', 'rejected', 'cancelled'))
);

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

-- Foreign key constraints
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'resolution_outputs_incident_id_fkey'
    ) THEN
        ALTER TABLE resolution_outputs 
            ADD CONSTRAINT resolution_outputs_incident_id_fkey 
            FOREIGN KEY (incident_id) 
            REFERENCES incidents(id) 
            ON DELETE CASCADE;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'resolution_outputs_triage_result_id_fkey'
    ) THEN
        ALTER TABLE resolution_outputs 
            ADD CONSTRAINT resolution_outputs_triage_result_id_fkey 
            FOREIGN KEY (triage_result_id) 
            REFERENCES triage_results(id) 
            ON DELETE CASCADE;
    END IF;
END $$;

-- Comments
COMMENT ON TABLE resolution_outputs IS 
    'Recommendations from Resolution Agent, with clear provenance to triage_results and runbook_steps';
COMMENT ON COLUMN resolution_outputs.recommendations IS 
    'JSONB array of recommendation objects, each with step_id, action, confidence, and provenance';

-- ============================================================================
-- TRIGGERS AND FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for runbook_steps
DROP TRIGGER IF EXISTS runbook_steps_updated_at_trigger ON runbook_steps;
CREATE TRIGGER runbook_steps_updated_at_trigger
    BEFORE UPDATE ON runbook_steps
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Trigger for incident_signatures
DROP TRIGGER IF EXISTS incident_signatures_updated_at_trigger ON incident_signatures;
CREATE TRIGGER incident_signatures_updated_at_trigger
    BEFORE UPDATE ON incident_signatures
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Function to update tsvector for runbook_steps
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

-- Trigger to auto-update tsvector for runbook_steps
DROP TRIGGER IF EXISTS runbook_steps_tsv_trigger ON runbook_steps;
CREATE TRIGGER runbook_steps_tsv_trigger
    BEFORE INSERT OR UPDATE ON runbook_steps
    FOR EACH ROW
    EXECUTE FUNCTION update_runbook_steps_tsv();

-- Function to update tsvector for incident_signatures
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

-- Trigger to auto-update tsvector for incident_signatures
DROP TRIGGER IF EXISTS incident_signatures_tsv_trigger ON incident_signatures;
CREATE TRIGGER incident_signatures_tsv_trigger
    BEFORE INSERT OR UPDATE ON incident_signatures
    FOR EACH ROW
    EXECUTE FUNCTION update_incident_signatures_tsv();

-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View: runbook_steps_with_metadata
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

-- View: triage_to_resolution_chain
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

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Verify tables were created
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('runbook_steps', 'incident_signatures', 'triage_results', 'resolution_outputs');
    
    IF table_count = 4 THEN
        RAISE NOTICE 'Migration 004 completed successfully: All 4 tables created';
    ELSE
        RAISE WARNING 'Migration 004: Expected 4 tables, found %', table_count;
    END IF;
END $$;

