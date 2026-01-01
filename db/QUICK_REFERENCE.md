# Quick Reference: Storage & Vector Schema

## Files Overview

| File | Purpose |
|------|---------|
| `schema_storage_vector_design.sql` | Complete SQL schema (tables, indexes, triggers, views) |
| `examples_storage_vector_design.sql` | Example INSERT statements and query patterns |
| `INDEX_STRATEGY.md` | Comprehensive index documentation |
| `STORAGE_VECTOR_DESIGN_SUMMARY.md` | Design summary and architecture compliance |
| `QUICK_REFERENCE.md` | This file - quick lookup guide |

## Table Quick Reference

### runbook_steps
**Purpose**: Atomic runbook steps for Resolution Agent retrieval

**Key Columns**:
- `step_id` (TEXT, UNIQUE): e.g., "RB123-S3"
- `runbook_id` (TEXT): Parent runbook reference
- `condition` (TEXT): When step applies
- `action` (TEXT): What to do (primary semantic content)
- `embedding` (vector(1536)): Semantic embedding for similarity search

**Vector Embedding**: `condition + action + expected_outcome`

**Primary Index**: `runbook_steps_embedding_idx` (IVFFlat, cosine similarity)

---

### incident_signatures
**Purpose**: Failure patterns for Triage Agent classification

**Key Columns**:
- `incident_signature_id` (TEXT, UNIQUE): e.g., "SIG-DB-001"
- `failure_type` (TEXT): e.g., "SQL_AGENT_JOB_FAILURE"
- `error_class` (TEXT): e.g., "SERVICE_ACCOUNT_DISABLED"
- `symptoms` (TEXT[]): Array of symptom strings
- `resolution_refs` (TEXT[]): Array of step_ids that resolve this
- `embedding` (vector(1536)): Semantic embedding for pattern matching

**Vector Embedding**: `failure_type + error_class + symptoms`

**Primary Index**: `incident_signatures_embedding_idx` (IVFFlat, cosine similarity)

---

### triage_results
**Purpose**: Classification outputs from Triage Agent

**Key Columns**:
- `id` (UUID, PRIMARY KEY)
- `incident_id` (UUID, FK → incidents.id)
- `failure_type` (TEXT): Identified failure type
- `error_class` (TEXT): Identified error class
- `severity` (TEXT): "low", "medium", "high", "critical"
- `confidence` (NUMERIC(5,4)): 0.0000 to 1.0000
- `policy_band` (TEXT): "AUTO", "PROPOSE", "REVIEW"
- `matched_signature_ids` (TEXT[]): Array of incident_signature_id values

**No Vector Embedding**: Classification data only, not for retrieval

**Primary Indexes**: Foreign key to incidents, filtering indexes

---

### resolution_outputs
**Purpose**: Recommendations from Resolution Agent

**Key Columns**:
- `id` (UUID, PRIMARY KEY)
- `incident_id` (UUID, FK → incidents.id)
- `triage_result_id` (UUID, FK → triage_results.id)
- `overall_confidence` (NUMERIC(5,4)): 0.0000 to 1.0000
- `risk_level` (TEXT): "low", "medium", "high"
- `recommendations` (JSONB): Array of recommendation objects
- `retrieved_step_ids` (TEXT[]): Array of runbook_steps.step_id
- `used_signature_ids` (TEXT[]): Array of incident_signatures.incident_signature_id
- `execution_status` (TEXT): "pending", "accepted", "executed", "rejected", "cancelled"

**No Vector Embedding**: Recommendations only, not for retrieval

**Primary Indexes**: Foreign keys, GIN on recommendations JSONB

---

## Common Queries

### 1. Semantic Search for Runbook Steps (Resolution Agent)
```sql
SELECT 
    step_id,
    action,
    risk_level,
    1 - (embedding <=> query_embedding::vector(1536)) AS similarity
FROM runbook_steps
WHERE service = 'database'
  AND risk_level = 'low'
ORDER BY embedding <=> query_embedding::vector(1536)
LIMIT 10;
```

### 2. Semantic Search for Incident Signatures (Triage Agent)
```sql
SELECT 
    incident_signature_id,
    failure_type,
    error_class,
    1 - (embedding <=> query_embedding::vector(1536)) AS similarity
FROM incident_signatures
WHERE affected_service = 'database'
ORDER BY embedding <=> query_embedding::vector(1536)
LIMIT 5;
```

### 3. Get Complete Triage-to-Resolution Chain
```sql
SELECT 
    i.alert_id,
    tr.failure_type,
    tr.error_class,
    tr.confidence AS triage_confidence,
    ro.overall_confidence AS resolution_confidence,
    ro.retrieved_step_ids,
    ro.execution_status
FROM incidents i
JOIN triage_results tr ON i.id = tr.incident_id
LEFT JOIN resolution_outputs ro ON tr.id = ro.triage_result_id
WHERE i.alert_id = 'ALERT-2024-001';
```

### 4. Find Steps Referenced by Resolution
```sql
SELECT 
    rs.step_id,
    rs.action,
    rs.risk_level,
    ro.overall_confidence,
    ro.execution_status
FROM resolution_outputs ro
JOIN runbook_steps rs ON rs.step_id = ANY(ro.retrieved_step_ids)
WHERE ro.incident_id = '00000000-0000-0000-0000-000000000001'::uuid;
```

### 5. Get Signature Statistics
```sql
SELECT 
    incident_signature_id,
    failure_type,
    match_count,
    resolution_success_count,
    CASE 
        WHEN match_count > 0 
        THEN (resolution_success_count::numeric / match_count::numeric) * 100
        ELSE 0
    END AS success_rate_percent
FROM incident_signatures
ORDER BY match_count DESC;
```

---

## Vector Embedding Dimensions

- **Model**: OpenAI `text-embedding-3-small`
- **Dimensions**: 1536
- **Index Type**: IVFFlat with cosine similarity
- **Lists Parameter**: 100 (tuned for 10K-100K records)

---

## Foreign Key Relationships

```
incidents (id)
    ↓
triage_results (incident_id)
    ↓
resolution_outputs (triage_result_id)
    ↓
runbook_steps (referenced by retrieved_step_ids array)
    ↑
incident_signatures (referenced by matched_signature_ids array)
```

---

## Index Count Summary

| Table | Vector | Full-Text | B-tree | GIN | Unique | Total |
|-------|--------|-----------|--------|-----|--------|-------|
| `runbook_steps` | 1 | 1 | 5 | 0 | 1 | 8 |
| `incident_signatures` | 1 | 1 | 6 | 2 | 1 | 11 |
| `triage_results` | 0 | 0 | 8 | 1 | 0 | 9 |
| `resolution_outputs` | 0 | 0 | 7 | 3 | 0 | 10 |
| **Total** | **2** | **2** | **26** | **6** | **2** | **38** |

---

## Architecture Compliance Checklist

- ✅ No mixed-purpose tables
- ✅ No raw logs in resolution tables
- ✅ Clear foreign keys and provenance
- ✅ Vector embeddings aligned with semantic purpose
- ✅ Triage Agent uses incident_signatures
- ✅ Resolution Agent uses runbook_steps
- ✅ Every recommendation has provenance
- ✅ Separation of concerns maintained

---

## Next Steps

1. Review `schema_storage_vector_design.sql` for complete schema
2. See `examples_storage_vector_design.sql` for example data
3. Read `INDEX_STRATEGY.md` for index details
4. Read `STORAGE_VECTOR_DESIGN_SUMMARY.md` for design rationale

