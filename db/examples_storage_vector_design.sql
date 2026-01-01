-- ============================================================================
-- Example Records for Storage & Vector Schema Design
-- ============================================================================
-- This file contains example INSERT statements demonstrating:
--   - Proper data structure for each table
--   - Vector embeddings (placeholder format - actual embeddings would be 1536-dim vectors)
--   - Foreign key relationships
--   - Provenance chains
-- ============================================================================

-- ============================================================================
-- 1. RUNBOOK_STEPS EXAMPLES
-- ============================================================================
-- These examples show atomic runbook steps with semantic embeddings
-- Each step is independently embeddable for retrieval by Resolution Agent

-- Example 1: Database service account verification step
INSERT INTO runbook_steps (
    step_id,
    runbook_id,
    condition,
    action,
    expected_outcome,
    rollback,
    risk_level,
    service,
    component,
    runbook_title,
    embedding,
    created_at,
    last_reviewed_at
) VALUES (
    'RB123-S3',
    'RB123',
    'SQL Agent job fails due to authentication error',
    'Verify service account is enabled in Active Directory and has proper permissions',
    'Job can authenticate successfully and execute without errors',
    'Revert account changes and restore previous permissions',
    'low',
    'database',
    'sql_agent',
    'Runbook - Database Alerts',
    -- Note: Actual embedding would be a 1536-dimensional vector
    -- Format: '[0.123, -0.456, 0.789, ...]' (1536 values)
    '[0.0123, -0.0456, 0.0789]'::vector(1536),  -- Placeholder - replace with actual embedding
    now(),
    now() - INTERVAL '30 days'
);

-- Example 2: High CPU investigation step
INSERT INTO runbook_steps (
    step_id,
    runbook_id,
    condition,
    action,
    expected_outcome,
    rollback,
    risk_level,
    service,
    component,
    runbook_title,
    embedding,
    created_at,
    last_reviewed_at
) VALUES (
    'RB456-S1',
    'RB456',
    'CPU utilization exceeds 90% for more than 5 minutes',
    'Check top processes using CPU and identify resource-intensive queries or applications',
    'CPU utilization drops below 80% and system returns to normal operation',
    'No rollback needed - investigation step only',
    'medium',
    'compute',
    'cpu_monitoring',
    'Runbook - High CPU Alerts',
    '[0.0234, -0.0567, 0.0890]'::vector(1536),  -- Placeholder
    now(),
    now() - INTERVAL '15 days'
);

-- Example 3: Memory leak detection step
INSERT INTO runbook_steps (
    step_id,
    runbook_id,
    condition,
    action,
    expected_outcome,
    rollback,
    risk_level,
    service,
    component,
    runbook_title,
    embedding,
    created_at,
    last_reviewed_at
) VALUES (
    'RB789-S2',
    'RB789',
    'Memory usage continuously increases without corresponding load increase',
    'Identify process with memory leak using memory profiler and restart affected service',
    'Memory usage stabilizes and returns to baseline levels',
    'Restore previous service version if memory leak persists',
    'high',
    'application',
    'memory_management',
    'Runbook - High Memory Alerts',
    '[0.0345, -0.0678, 0.0901]'::vector(1536),  -- Placeholder
    now(),
    now() - INTERVAL '7 days'
);

-- Example 4: Disk space cleanup step
INSERT INTO runbook_steps (
    step_id,
    runbook_id,
    condition,
    action,
    expected_outcome,
    rollback,
    risk_level,
    service,
    component,
    runbook_title,
    embedding,
    created_at,
    last_reviewed_at
) VALUES (
    'RB321-S4',
    'RB321',
    'Disk utilization exceeds 85% on primary data volume',
    'Identify and remove old log files, temporary files, and unused backups older than 30 days',
    'Disk utilization drops below 75% with sufficient free space available',
    'Restore deleted files from backup if critical data was removed',
    'medium',
    'storage',
    'disk_management',
    'Runbook – High Volume or Disk Utilization',
    '[0.0456, -0.0789, 0.1012]'::vector(1536),  -- Placeholder
    now(),
    now() - INTERVAL '20 days'
);


-- ============================================================================
-- 2. INCIDENT_SIGNATURES EXAMPLES
-- ============================================================================
-- These examples show failure patterns extracted from historical incidents
-- Each signature represents a pattern, not raw incident text
-- Used by Triage Agent for classification

-- Example 1: SQL Agent authentication failure pattern
INSERT INTO incident_signatures (
    incident_signature_id,
    failure_type,
    error_class,
    symptoms,
    affected_service,
    service,
    component,
    resolution_refs,
    embedding,
    source_incident_ids,
    created_at,
    last_seen_at,
    match_count,
    resolution_success_count
) VALUES (
    'SIG-DB-001',
    'SQL_AGENT_JOB_FAILURE',
    'SERVICE_ACCOUNT_DISABLED',
    ARRAY[
        'job step failed',
        'authentication error',
        'account disabled',
        'login failed for user',
        'cannot connect to database'
    ],
    'database',
    'database',
    'sql_agent',
    ARRAY['RB123-S3'],  -- References runbook step that resolves this
    '[0.0567, -0.0890, 0.1123]'::vector(1536),  -- Placeholder
    ARRAY['INC-2024-001', 'INC-2024-015', 'INC-2024-028'],
    now() - INTERVAL '60 days',
    now() - INTERVAL '5 days',
    12,  -- Matched 12 times
    11   -- Successfully resolved 11 times
);

-- Example 2: High CPU pattern
INSERT INTO incident_signatures (
    incident_signature_id,
    failure_type,
    error_class,
    symptoms,
    affected_service,
    service,
    component,
    resolution_refs,
    embedding,
    source_incident_ids,
    created_at,
    last_seen_at,
    match_count,
    resolution_success_count
) VALUES (
    'SIG-CPU-002',
    'HIGH_CPU_UTILIZATION',
    'QUERY_PERFORMANCE_DEGRADATION',
    ARRAY[
        'cpu usage above 90%',
        'slow query execution',
        'application timeouts',
        'response time increased',
        'system unresponsive'
    ],
    'compute',
    'compute',
    'cpu_monitoring',
    ARRAY['RB456-S1', 'RB456-S2'],  -- Multiple steps may be needed
    '[0.0678, -0.0901, 0.1234]'::vector(1536),  -- Placeholder
    ARRAY['INC-2024-003', 'INC-2024-010', 'INC-2024-022'],
    now() - INTERVAL '45 days',
    now() - INTERVAL '2 days',
    8,
    7
);

-- Example 3: Memory leak pattern
INSERT INTO incident_signatures (
    incident_signature_id,
    failure_type,
    error_class,
    symptoms,
    affected_service,
    service,
    component,
    resolution_refs,
    embedding,
    source_incident_ids,
    created_at,
    last_seen_at,
    match_count,
    resolution_success_count
) VALUES (
    'SIG-MEM-003',
    'MEMORY_LEAK',
    'GRADUAL_MEMORY_INCREASE',
    ARRAY[
        'memory usage continuously increasing',
        'no corresponding load increase',
        'out of memory errors',
        'application crashes',
        'garbage collection ineffective'
    ],
    'application',
    'application',
    'memory_management',
    ARRAY['RB789-S2'],
    '[0.0789, -0.1012, 0.1345]'::vector(1536),  -- Placeholder
    ARRAY['INC-2024-005', 'INC-2024-018'],
    now() - INTERVAL '30 days',
    now() - INTERVAL '10 days',
    5,
    4
);

-- Example 4: Disk space exhaustion pattern
INSERT INTO incident_signatures (
    incident_signature_id,
    failure_type,
    error_class,
    symptoms,
    affected_service,
    service,
    component,
    resolution_refs,
    embedding,
    source_incident_ids,
    created_at,
    last_seen_at,
    match_count,
    resolution_success_count
) VALUES (
    'SIG-DISK-004',
    'DISK_SPACE_EXHAUSTION',
    'LOG_FILE_ACCUMULATION',
    ARRAY[
        'disk usage above 85%',
        'cannot write to disk',
        'application errors writing logs',
        'backup failures',
        'file system full'
    ],
    'storage',
    'storage',
    'disk_management',
    ARRAY['RB321-S4'],
    '[0.0890, -0.1123, 0.1456]'::vector(1536),  -- Placeholder
    ARRAY['INC-2024-007', 'INC-2024-012', 'INC-2024-025'],
    now() - INTERVAL '40 days',
    now() - INTERVAL '1 day',
    15,
    14
);


-- ============================================================================
-- 3. TRIAGE_RESULTS EXAMPLES
-- ============================================================================
-- These examples show classification outputs from Triage Agent
-- Each result links to an incident and references matched signatures
-- Note: Requires existing incidents in the incidents table

-- Example 1: Triage result for SQL Agent authentication failure
-- Assumes incident with id = '00000000-0000-0000-0000-000000000001'
INSERT INTO triage_results (
    incident_id,
    failure_type,
    error_class,
    severity,
    confidence,
    policy_band,
    matched_signature_ids,
    matched_runbook_refs,
    evidence_chunks,
    retrieval_method,
    created_at,
    completed_at
) VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,  -- Replace with actual incident_id
    'SQL_AGENT_JOB_FAILURE',
    'SERVICE_ACCOUNT_DISABLED',
    'medium',
    0.86,
    'AUTO',
    ARRAY['SIG-DB-001'],  -- Matched this signature
    ARRAY['RB123'],       -- Runbook metadata reference
    '{"chunks": [{"id": "chunk-001", "similarity": 0.92}], "sources": ["SIG-DB-001"]}'::jsonb,
    'hybrid',
    now() - INTERVAL '1 hour',
    now() - INTERVAL '1 hour'
);

-- Example 2: Triage result for high CPU
-- Assumes incident with id = '00000000-0000-0000-0000-000000000002'
INSERT INTO triage_results (
    incident_id,
    failure_type,
    error_class,
    severity,
    confidence,
    policy_band,
    matched_signature_ids,
    matched_runbook_refs,
    evidence_chunks,
    retrieval_method,
    created_at,
    completed_at
) VALUES (
    '00000000-0000-0000-0000-000000000002'::uuid,  -- Replace with actual incident_id
    'HIGH_CPU_UTILIZATION',
    'QUERY_PERFORMANCE_DEGRADATION',
    'high',
    0.91,
    'PROPOSE',  -- Requires approval due to high severity
    ARRAY['SIG-CPU-002'],
    ARRAY['RB456'],
    '{"chunks": [{"id": "chunk-002", "similarity": 0.89}], "sources": ["SIG-CPU-002"]}'::jsonb,
    'hybrid',
    now() - INTERVAL '30 minutes',
    now() - INTERVAL '30 minutes'
);

-- Example 3: Triage result for memory leak
-- Assumes incident with id = '00000000-0000-0000-0000-000000000003'
INSERT INTO triage_results (
    incident_id,
    failure_type,
    error_class,
    severity,
    confidence,
    policy_band,
    matched_signature_ids,
    matched_runbook_refs,
    evidence_chunks,
    retrieval_method,
    created_at,
    completed_at
) VALUES (
    '00000000-0000-0000-0000-000000000003'::uuid,  -- Replace with actual incident_id
    'MEMORY_LEAK',
    'GRADUAL_MEMORY_INCREASE',
    'high',
    0.78,
    'REVIEW',  -- High risk, requires human review
    ARRAY['SIG-MEM-003'],
    ARRAY['RB789'],
    '{"chunks": [{"id": "chunk-003", "similarity": 0.85}], "sources": ["SIG-MEM-003"]}'::jsonb,
    'vector_only',
    now() - INTERVAL '15 minutes',
    now() - INTERVAL '15 minutes'
);


-- ============================================================================
-- 4. RESOLUTION_OUTPUTS EXAMPLES
-- ============================================================================
-- These examples show recommendations from Resolution Agent
-- Each output links to a triage_result and references runbook_steps
-- No raw logs, only structured recommendations with provenance

-- Example 1: Resolution output for SQL Agent authentication failure
-- Assumes triage_result with id = '00000000-0000-0000-0000-000000000010'
INSERT INTO resolution_outputs (
    incident_id,
    triage_result_id,
    overall_confidence,
    risk_level,
    recommendations,
    retrieved_step_ids,
    used_signature_ids,
    evidence_chunks,
    retrieval_method,
    created_at,
    proposed_at,
    execution_status
) VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,  -- Same incident as triage
    '00000000-0000-0000-0000-000000000010'::uuid,  -- Replace with actual triage_result_id
    0.88,
    'low',
    '[
        {
            "step_id": "RB123-S3",
            "action": "Verify service account is enabled in Active Directory and has proper permissions",
            "confidence": 0.91,
            "provenance": {
                "runbook_id": "RB123",
                "incident_signatures": ["SIG-DB-001"],
                "historical_success_rate": 0.92
            },
            "order": 1
        }
    ]'::jsonb,
    ARRAY['RB123-S3'],  -- Retrieved this step
    ARRAY['SIG-DB-001'],  -- Used this signature
    '{"chunks": [{"id": "step-chunk-001", "similarity": 0.91}], "sources": ["RB123-S3"]}'::jsonb,
    'hybrid',
    now() - INTERVAL '55 minutes',
    now() - INTERVAL '55 minutes',
    'accepted'
);

-- Example 2: Resolution output for high CPU (multiple steps)
-- Assumes triage_result with id = '00000000-0000-0000-0000-000000000011'
INSERT INTO resolution_outputs (
    incident_id,
    triage_result_id,
    overall_confidence,
    risk_level,
    recommendations,
    retrieved_step_ids,
    used_signature_ids,
    evidence_chunks,
    retrieval_method,
    created_at,
    proposed_at,
    execution_status
) VALUES (
    '00000000-0000-0000-0000-000000000002'::uuid,
    '00000000-0000-0000-0000-000000000011'::uuid,  -- Replace with actual triage_result_id
    0.85,
    'medium',
    '[
        {
            "step_id": "RB456-S1",
            "action": "Check top processes using CPU and identify resource-intensive queries or applications",
            "confidence": 0.89,
            "provenance": {
                "runbook_id": "RB456",
                "incident_signatures": ["SIG-CPU-002"],
                "historical_success_rate": 0.88
            },
            "order": 1
        },
        {
            "step_id": "RB456-S2",
            "action": "Optimize or terminate identified resource-intensive processes",
            "confidence": 0.82,
            "provenance": {
                "runbook_id": "RB456",
                "incident_signatures": ["SIG-CPU-002"],
                "historical_success_rate": 0.85
            },
            "order": 2
        }
    ]'::jsonb,
    ARRAY['RB456-S1', 'RB456-S2'],
    ARRAY['SIG-CPU-002'],
    '{"chunks": [{"id": "step-chunk-002", "similarity": 0.89}, {"id": "step-chunk-003", "similarity": 0.82}], "sources": ["RB456-S1", "RB456-S2"]}'::jsonb,
    'hybrid',
    now() - INTERVAL '25 minutes',
    now() - INTERVAL '25 minutes',
    'pending'
);

-- Example 3: Resolution output for disk space (single step)
-- Assumes triage_result with id = '00000000-0000-0000-0000-000000000012'
INSERT INTO resolution_outputs (
    incident_id,
    triage_result_id,
    overall_confidence,
    risk_level,
    recommendations,
    retrieved_step_ids,
    used_signature_ids,
    evidence_chunks,
    retrieval_method,
    created_at,
    proposed_at,
    execution_status,
    accepted_at,
    executed_at,
    execution_notes
) VALUES (
    '00000000-0000-0000-0000-000000000004'::uuid,  -- Different incident
    '00000000-0000-0000-0000-000000000012'::uuid,  -- Replace with actual triage_result_id
    0.92,
    'low',
    '[
        {
            "step_id": "RB321-S4",
            "action": "Identify and remove old log files, temporary files, and unused backups older than 30 days",
            "confidence": 0.94,
            "provenance": {
                "runbook_id": "RB321",
                "incident_signatures": ["SIG-DISK-004"],
                "historical_success_rate": 0.93
            },
            "order": 1
        }
    ]'::jsonb,
    ARRAY['RB321-S4'],
    ARRAY['SIG-DISK-004'],
    '{"chunks": [{"id": "step-chunk-004", "similarity": 0.94}], "sources": ["RB321-S4"]}'::jsonb,
    'vector_only',
    now() - INTERVAL '2 hours',
    now() - INTERVAL '2 hours',
    'executed',
    now() - INTERVAL '1 hour',
    now() - INTERVAL '45 minutes',
    'Successfully freed 45GB of disk space by removing old log files. System returned to normal operation.'
);


-- ============================================================================
-- QUERY EXAMPLES
-- ============================================================================
-- These examples demonstrate how to query the tables for common use cases

-- Query 1: Find runbook steps semantically similar to a given condition
-- (Vector similarity search - primary retrieval method for Resolution Agent)
-- SELECT 
--     step_id,
--     action,
--     risk_level,
--     1 - (embedding <=> '[0.0123, -0.0456, 0.0789]'::vector(1536)) AS similarity
-- FROM runbook_steps
-- WHERE service = 'database'
-- ORDER BY embedding <=> '[0.0123, -0.0456, 0.0789]'::vector(1536)
-- LIMIT 10;

-- Query 2: Find incident signatures matching a failure pattern
-- (Vector similarity search - primary retrieval method for Triage Agent)
-- SELECT 
--     incident_signature_id,
--     failure_type,
--     error_class,
--     symptoms,
--     1 - (embedding <=> '[0.0567, -0.0890, 0.1123]'::vector(1536)) AS similarity
-- FROM incident_signatures
-- WHERE affected_service = 'database'
-- ORDER BY embedding <=> '[0.0567, -0.0890, 0.1123]'::vector(1536)
-- LIMIT 5;

-- Query 3: Get complete triage-to-resolution chain with provenance
-- SELECT 
--     i.alert_id,
--     tr.failure_type,
--     tr.error_class,
--     tr.confidence AS triage_confidence,
--     ro.overall_confidence AS resolution_confidence,
--     ro.retrieved_step_ids,
--     ro.execution_status
-- FROM triage_to_resolution_chain trc
-- JOIN incidents i ON trc.incident_id = i.id
-- JOIN triage_results tr ON trc.triage_result_id = tr.id
-- LEFT JOIN resolution_outputs ro ON trc.resolution_output_id = ro.id
-- WHERE i.alert_id = 'ALERT-2024-001';

-- Query 4: Find all runbook steps referenced by a resolution output
-- SELECT 
--     rs.step_id,
--     rs.action,
--     rs.risk_level,
--     ro.overall_confidence,
--     ro.execution_status
-- FROM resolution_outputs ro
-- JOIN runbook_steps rs ON rs.step_id = ANY(ro.retrieved_step_ids)
-- WHERE ro.incident_id = '00000000-0000-0000-0000-000000000001'::uuid;

-- Query 5: Get statistics on signature matching and resolution success
-- SELECT 
--     isig.incident_signature_id,
--     isig.failure_type,
--     isig.match_count,
--     isig.resolution_success_count,
--     CASE 
--         WHEN isig.match_count > 0 
--         THEN (isig.resolution_success_count::numeric / isig.match_count::numeric) * 100
--         ELSE 0
--     END AS success_rate_percent
-- FROM incident_signatures isig
-- ORDER BY isig.match_count DESC;

