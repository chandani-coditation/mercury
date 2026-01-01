-- ============================================================================
-- Storage & Vector Schema Design for NOC Triage & Resolution System
-- ============================================================================
-- This schema implements dedicated tables for:
--   - runbook_steps: Atomic operational knowledge with semantic embeddings
--   - incident_signatures: Failure patterns with semantic embeddings
--   - triage_results: Classification outputs with provenance
--   - resolution_outputs: Recommendations with clear provenance
--
-- Design Principles:
--   - No mixed-purpose tables
--   - No raw logs in resolution tables
--   - Clear foreign keys and provenance
--   - Vector embeddings aligned with semantic purpose
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. RUNBOOK_STEPS TABLE
-- ============================================================================
-- Purpose: Store atomic runbook steps as independent, embeddable units
-- Semantic Purpose: Enable semantic search for "what action to take" queries
-- Each step is embedded independently for retrieval by Resolution Agent
--
-- Architecture Alignment:
--   - Per ARCHITECTURE_LOCK.md Section 3.1: "Each step is embedded independently"
--   - Resolution Agent retrieves only relevant steps (Section 7.3)
-- ============================================================================

CREATE TABLE IF NOT EXISTS runbook_steps (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id TEXT NOT NULL UNIQUE,  -- e.g., "RB123-S3" (human-readable identifier)
    runbook_id TEXT NOT NULL,      -- e.g., "RB123" (parent runbook reference)
    
    -- Step content (what gets embedded)
    condition TEXT NOT NULL,       -- When this step applies
    action TEXT NOT NULL,          -- What to do (primary semantic content)
    expected_outcome TEXT,         -- Expected result
    rollback TEXT,                 -- Rollback procedure if needed
    
    -- Classification metadata
    risk_level TEXT,               -- "low", "medium", "high"
    service TEXT,                  -- Affected service
    component TEXT,                -- Affected component
    
    -- Vector embedding for semantic search
    -- Embedding represents: condition + action + expected_outcome
    -- Purpose: Find steps semantically similar to current incident
    embedding vector(1536),        -- OpenAI text-embedding-3-small (1536 dims)
    
    -- Full-text search support
    tsv tsvector,                  -- For keyword search on condition/action
    
    -- Provenance and metadata
    runbook_title TEXT,            -- Parent runbook title (for display)
    runbook_document_id UUID,      -- Foreign key to documents table (if exists)
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_reviewed_at TIMESTAMPTZ,  -- When step was last reviewed/validated
    
    -- Constraints
    CONSTRAINT runbook_steps_risk_level_check 
        CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high'))
);

-- Indexes for runbook_steps
-- Vector similarity search (primary retrieval method for Resolution Agent)
CREATE INDEX IF NOT EXISTS runbook_steps_embedding_idx 
    ON runbook_steps 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

-- Full-text search index
CREATE INDEX IF NOT EXISTS runbook_steps_tsv_idx 
    ON runbook_steps 
    USING GIN (tsv);

-- Foreign key lookup
CREATE INDEX IF NOT EXISTS runbook_steps_runbook_document_id_idx 
    ON runbook_steps(runbook_document_id);

-- Filtering indexes (for hybrid retrieval)
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

-- Unique constraint on step_id for data integrity
CREATE UNIQUE INDEX IF NOT EXISTS runbook_steps_step_id_unique_idx 
    ON runbook_steps(step_id);

-- Comments for documentation
COMMENT ON TABLE runbook_steps IS 
    'Atomic runbook steps stored independently for semantic retrieval by Resolution Agent';
COMMENT ON COLUMN runbook_steps.step_id IS 
    'Human-readable step identifier (e.g., RB123-S3)';
COMMENT ON COLUMN runbook_steps.embedding IS 
    'Vector embedding of condition + action + expected_outcome for semantic search';
COMMENT ON COLUMN runbook_steps.runbook_document_id IS 
    'Optional foreign key to documents table for runbook metadata';


-- ============================================================================
-- 2. INCIDENT_SIGNATURES TABLE
-- ============================================================================
-- Purpose: Store failure patterns (not raw incident text)
-- Semantic Purpose: Enable semantic search for "what kind of incident is this" queries
-- Each signature represents a pattern, not a story
--
-- Architecture Alignment:
--   - Per ARCHITECTURE_LOCK.md Section 3.2: "Signatures represent patterns, not stories"
--   - Triage Agent retrieves incident signatures (Section 4.2)
--   - Raw ticket text is NOT embedded directly
-- ============================================================================

CREATE TABLE IF NOT EXISTS incident_signatures (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_signature_id TEXT NOT NULL UNIQUE,  -- e.g., "SIG-DB-001"
    
    -- Classification (what gets embedded)
    failure_type TEXT NOT NULL,   -- e.g., "SQL_AGENT_JOB_FAILURE"
    error_class TEXT NOT NULL,     -- e.g., "SERVICE_ACCOUNT_DISABLED"
    symptoms TEXT[] NOT NULL,      -- Array of symptom strings
    
    -- Context metadata
    affected_service TEXT,         -- Affected service
    service TEXT,                  -- Service classification
    component TEXT,                -- Component classification
    
    -- Resolution references (provenance)
    -- Links to runbook_steps that resolved similar incidents
    resolution_refs TEXT[],        -- Array of step_ids (e.g., ["RB123-S3"])
    
    -- Vector embedding for semantic search
    -- Embedding represents: failure_type + error_class + symptoms
    -- Purpose: Find signatures semantically similar to current alert
    embedding vector(1536),        -- OpenAI text-embedding-3-small (1536 dims)
    
    -- Full-text search support
    tsv tsvector,                  -- For keyword search on failure_type/error_class/symptoms
    
    -- Provenance
    source_incident_ids TEXT[],    -- Original incident IDs that contributed to this signature
    source_document_id UUID,       -- Foreign key to documents table (if exists)
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ,      -- When this pattern was last observed
    
    -- Statistics (for ranking)
    match_count INTEGER DEFAULT 0, -- How many times this signature matched
    resolution_success_count INTEGER DEFAULT 0, -- Successful resolutions using this signature
    
    -- Constraints
    CONSTRAINT incident_signatures_symptoms_not_empty 
        CHECK (array_length(symptoms, 1) > 0)
);

-- Indexes for incident_signatures
-- Vector similarity search (primary retrieval method for Triage Agent)
CREATE INDEX IF NOT EXISTS incident_signatures_embedding_idx 
    ON incident_signatures 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

-- Full-text search index
CREATE INDEX IF NOT EXISTS incident_signatures_tsv_idx 
    ON incident_signatures 
    USING GIN (tsv);

-- Foreign key lookup
CREATE INDEX IF NOT EXISTS incident_signatures_source_document_id_idx 
    ON incident_signatures(source_document_id);

-- Filtering indexes (for hybrid retrieval by Triage Agent)
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

-- GIN index for array searches (symptoms, resolution_refs)
CREATE INDEX IF NOT EXISTS incident_signatures_symptoms_idx 
    ON incident_signatures 
    USING GIN (symptoms);
CREATE INDEX IF NOT EXISTS incident_signatures_resolution_refs_idx 
    ON incident_signatures 
    USING GIN (resolution_refs);

-- Unique constraint on incident_signature_id
CREATE UNIQUE INDEX IF NOT EXISTS incident_signatures_signature_id_unique_idx 
    ON incident_signatures(incident_signature_id);

-- Comments for documentation
COMMENT ON TABLE incident_signatures IS 
    'Failure patterns extracted from historical incidents, used by Triage Agent for classification';
COMMENT ON COLUMN incident_signatures.incident_signature_id IS 
    'Human-readable signature identifier (e.g., SIG-DB-001)';
COMMENT ON COLUMN incident_signatures.embedding IS 
    'Vector embedding of failure_type + error_class + symptoms for semantic pattern matching';
COMMENT ON COLUMN incident_signatures.resolution_refs IS 
    'Array of runbook_steps.step_id that resolved incidents matching this signature';
COMMENT ON COLUMN incident_signatures.symptoms IS 
    'Array of symptom strings describing the failure pattern';


-- ============================================================================
-- 3. TRIAGE_RESULTS TABLE
-- ============================================================================
-- Purpose: Store classification outputs from Triage Agent
-- No raw logs, only structured classification data
-- Clear foreign keys and provenance
--
-- Architecture Alignment:
--   - Per ARCHITECTURE_LOCK.md Section 5: Triage Agent outputs classification
--   - Section 5.5: Triage Output Contract
--   - Section 5.4: Triage Agent MUST NOT generate resolution steps
-- ============================================================================

CREATE TABLE IF NOT EXISTS triage_results (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL,     -- Foreign key to incidents table
    
    -- Classification output (from Triage Agent)
    failure_type TEXT NOT NULL,    -- Identified failure type
    error_class TEXT NOT NULL,      -- Identified error class
    severity TEXT NOT NULL,        -- "low", "medium", "high", "critical"
    confidence NUMERIC(5,4) NOT NULL, -- Confidence score (0.0000 to 1.0000)
    
    -- Policy decision (derived from classification)
    policy_band TEXT NOT NULL,     -- "AUTO", "PROPOSE", or "REVIEW"
    
    -- Matched evidence (provenance)
    -- References to incident_signatures that matched
    matched_signature_ids TEXT[],   -- Array of incident_signature_id values
    matched_runbook_refs TEXT[],    -- Array of runbook_id values (metadata only, not steps)
    
    -- Evidence metadata (for audit trail)
    evidence_chunks JSONB,         -- Chunks used during retrieval (for debugging)
    retrieval_method TEXT,          -- How evidence was retrieved (e.g., "hybrid", "vector_only")
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,      -- When triage completed
    
    -- Constraints
    CONSTRAINT triage_results_confidence_range 
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT triage_results_severity_check 
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT triage_results_policy_band_check 
        CHECK (policy_band IN ('AUTO', 'PROPOSE', 'REVIEW'))
);

-- Indexes for triage_results
-- Foreign key to incidents
CREATE INDEX IF NOT EXISTS triage_results_incident_id_idx 
    ON triage_results(incident_id);

-- Filtering indexes
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

-- GIN index for array searches (matched_signature_ids)
CREATE INDEX IF NOT EXISTS triage_results_matched_signature_ids_idx 
    ON triage_results 
    USING GIN (matched_signature_ids);

-- Time-based queries
CREATE INDEX IF NOT EXISTS triage_results_created_at_idx 
    ON triage_results(created_at);
CREATE INDEX IF NOT EXISTS triage_results_completed_at_idx 
    ON triage_results(completed_at) 
    WHERE completed_at IS NOT NULL;

-- Foreign key constraint
ALTER TABLE triage_results 
    ADD CONSTRAINT triage_results_incident_id_fkey 
    FOREIGN KEY (incident_id) 
    REFERENCES incidents(id) 
    ON DELETE CASCADE;

-- Comments for documentation
COMMENT ON TABLE triage_results IS 
    'Classification outputs from Triage Agent, stored separately from incidents for clear provenance';
COMMENT ON COLUMN triage_results.matched_signature_ids IS 
    'Array of incident_signatures.incident_signature_id that matched during triage';
COMMENT ON COLUMN triage_results.matched_runbook_refs IS 
    'Array of runbook_id values (metadata only, Resolution Agent retrieves actual steps)';
COMMENT ON COLUMN triage_results.evidence_chunks IS 
    'JSONB containing retrieval evidence for audit/debugging (not used for resolution)';


-- ============================================================================
-- 4. RESOLUTION_OUTPUTS TABLE
-- ============================================================================
-- Purpose: Store recommendations from Resolution Agent
-- No raw logs, only structured recommendations with provenance
-- Clear foreign keys linking to triage_results and runbook_steps
--
-- Architecture Alignment:
--   - Per ARCHITECTURE_LOCK.md Section 7: Resolution Agent outputs recommendations
--   - Section 7.5: Resolution Output Contract
--   - Section 7.4: Resolution Agent MUST NOT re-classify or invent steps
--   - Every recommendation has provenance (Section 11)
-- ============================================================================

CREATE TABLE IF NOT EXISTS resolution_outputs (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL,     -- Foreign key to incidents table
    triage_result_id UUID NOT NULL, -- Foreign key to triage_results table
    
    -- Overall assessment
    overall_confidence NUMERIC(5,4) NOT NULL, -- Overall confidence (0.0000 to 1.0000)
    risk_level TEXT NOT NULL,      -- "low", "medium", "high"
    
    -- Recommendations (ordered list)
    -- Each recommendation references a runbook step
    recommendations JSONB NOT NULL, -- Array of recommendation objects
    
    -- Provenance metadata
    retrieved_step_ids TEXT[],     -- Array of runbook_steps.step_id that were retrieved
    used_signature_ids TEXT[],      -- Array of incident_signatures.incident_signature_id used
    
    -- Evidence metadata (for audit trail)
    evidence_chunks JSONB,         -- Chunks used during retrieval (for debugging)
    retrieval_method TEXT,          -- How evidence was retrieved (e.g., "hybrid", "vector_only")
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    proposed_at TIMESTAMPTZ,       -- When resolution was proposed
    accepted_at TIMESTAMPTZ,       -- When resolution was accepted by human
    executed_at TIMESTAMPTZ,       -- When resolution was executed
    
    -- Execution tracking
    execution_status TEXT,         -- "pending", "accepted", "executed", "rejected", "cancelled"
    execution_notes TEXT,           -- Human notes about execution
    
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
-- Foreign keys
CREATE INDEX IF NOT EXISTS resolution_outputs_incident_id_idx 
    ON resolution_outputs(incident_id);
CREATE INDEX IF NOT EXISTS resolution_outputs_triage_result_id_idx 
    ON resolution_outputs(triage_result_id);

-- Filtering indexes
CREATE INDEX IF NOT EXISTS resolution_outputs_risk_level_idx 
    ON resolution_outputs(risk_level);
CREATE INDEX IF NOT EXISTS resolution_outputs_overall_confidence_idx 
    ON resolution_outputs(overall_confidence);
CREATE INDEX IF NOT EXISTS resolution_outputs_execution_status_idx 
    ON resolution_outputs(execution_status) 
    WHERE execution_status IS NOT NULL;

-- GIN indexes for array searches
CREATE INDEX IF NOT EXISTS resolution_outputs_retrieved_step_ids_idx 
    ON resolution_outputs 
    USING GIN (retrieved_step_ids);
CREATE INDEX IF NOT EXISTS resolution_outputs_used_signature_ids_idx 
    ON resolution_outputs 
    USING GIN (used_signature_ids);

-- GIN index for JSONB recommendations
CREATE INDEX IF NOT EXISTS resolution_outputs_recommendations_idx 
    ON resolution_outputs 
    USING GIN (recommendations);

-- Time-based queries
CREATE INDEX IF NOT EXISTS resolution_outputs_created_at_idx 
    ON resolution_outputs(created_at);
CREATE INDEX IF NOT EXISTS resolution_outputs_proposed_at_idx 
    ON resolution_outputs(proposed_at) 
    WHERE proposed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS resolution_outputs_accepted_at_idx 
    ON resolution_outputs(accepted_at) 
    WHERE accepted_at IS NOT NULL;

-- Foreign key constraints
ALTER TABLE resolution_outputs 
    ADD CONSTRAINT resolution_outputs_incident_id_fkey 
    FOREIGN KEY (incident_id) 
    REFERENCES incidents(id) 
    ON DELETE CASCADE;

ALTER TABLE resolution_outputs 
    ADD CONSTRAINT resolution_outputs_triage_result_id_fkey 
    FOREIGN KEY (triage_result_id) 
    REFERENCES triage_results(id) 
    ON DELETE CASCADE;

-- Comments for documentation
COMMENT ON TABLE resolution_outputs IS 
    'Recommendations from Resolution Agent, with clear provenance to triage_results and runbook_steps';
COMMENT ON COLUMN resolution_outputs.recommendations IS 
    'JSONB array of recommendation objects, each with step_id, action, confidence, and provenance';
COMMENT ON COLUMN resolution_outputs.retrieved_step_ids IS 
    'Array of runbook_steps.step_id that were retrieved and considered';
COMMENT ON COLUMN resolution_outputs.used_signature_ids IS 
    'Array of incident_signatures.incident_signature_id that informed the recommendations';
COMMENT ON COLUMN resolution_outputs.evidence_chunks IS 
    'JSONB containing retrieval evidence for audit/debugging (not raw logs)';


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
CREATE TRIGGER runbook_steps_updated_at_trigger
    BEFORE UPDATE ON runbook_steps
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Trigger for incident_signatures
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
        COALESCE(array_to_string(NEW.symptoms, ' '), '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update tsvector for incident_signatures
CREATE TRIGGER incident_signatures_tsv_trigger
    BEFORE INSERT OR UPDATE ON incident_signatures
    FOR EACH ROW
    EXECUTE FUNCTION update_incident_signatures_tsv();


-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View: runbook_steps_with_metadata
-- Provides runbook step information with parent runbook context
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
-- Shows the complete chain from triage to resolution with provenance
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

