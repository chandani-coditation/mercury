# Storage & Vector Schema Design Summary

## Overview

This document summarizes the storage and vector schema design for the NOC Triage & Resolution System, implementing dedicated tables for `runbook_steps`, `incident_signatures`, `triage_results`, and `resolution_outputs` as specified in the architecture document.

## Design Principles

### 1. Separation of Concerns
- **No mixed-purpose tables**: Each table has a single, well-defined purpose
- **Clear boundaries**: Triage data separate from resolution data
- **Provenance chains**: Clear foreign key relationships trace data flow

### 2. Vector Embeddings Aligned with Semantic Purpose

| Table | Embedding Content | Semantic Purpose | Used By |
|-------|------------------|------------------|---------|
| `runbook_steps` | `condition + action + expected_outcome` | "What action to take" | Resolution Agent |
| `incident_signatures` | `failure_type + error_class + symptoms` | "What kind of incident is this" | Triage Agent |

### 3. No Raw Logs in Resolution Tables
- `triage_results`: Contains only structured classification data
- `resolution_outputs`: Contains only structured recommendations
- Evidence stored as JSONB metadata (for debugging), not raw logs

### 4. Clear Foreign Keys and Provenance

```
incidents (id)
    ↓
triage_results (incident_id → incidents.id)
    ↓
resolution_outputs (triage_result_id → triage_results.id)
    ↓
runbook_steps (referenced by resolution_outputs.retrieved_step_ids)
```

## Table Designs

### 1. runbook_steps

**Purpose**: Store atomic runbook steps as independent, embeddable units for semantic retrieval.

**Key Features**:
- Each step embedded independently (per architecture Section 3.1)
- Vector embedding enables semantic search for "what action to take"
- Clear provenance via `runbook_id` and `runbook_document_id`
- Full-text search support via `tsvector`

**Embedding Strategy**:
- Content: `condition + action + expected_outcome`
- Purpose: Find steps semantically similar to current incident
- Used by: Resolution Agent (Section 7.3)

**Indexes**:
- Vector similarity (IVFFlat) for semantic search
- Full-text (GIN) for keyword search
- Filtering indexes (service, component, risk_level)
- Foreign key to documents table

---

### 2. incident_signatures

**Purpose**: Store failure patterns (not raw incident text) for pattern matching.

**Key Features**:
- Represents patterns, not stories (per architecture Section 3.2)
- Vector embedding enables semantic search for "what kind of incident is this"
- Links to resolution steps via `resolution_refs` array
- Statistics tracking (match_count, resolution_success_count)

**Embedding Strategy**:
- Content: `failure_type + error_class + symptoms`
- Purpose: Find signatures semantically similar to current alert
- Used by: Triage Agent (Section 4.2)

**Indexes**:
- Vector similarity (IVFFlat) for semantic search
- Full-text (GIN) for keyword search
- Filtering indexes (failure_type, error_class, service)
- GIN indexes for array searches (symptoms, resolution_refs)

---

### 3. triage_results

**Purpose**: Store classification outputs from Triage Agent with clear provenance.

**Key Features**:
- No raw logs, only structured classification data
- Links to `incidents` table via foreign key
- References matched `incident_signatures` via array
- Policy band derived from classification
- Evidence metadata for audit trail (not used for resolution)

**Architecture Alignment**:
- Implements Triage Output Contract (Section 5.5)
- Triage Agent MUST NOT generate resolution steps (Section 5.4)
- Clear separation from resolution data

**Indexes**:
- Foreign key to incidents
- Filtering indexes (failure_type, error_class, severity, policy_band)
- GIN index for matched_signature_ids array
- Time-based indexes for analytics

---

### 4. resolution_outputs

**Purpose**: Store recommendations from Resolution Agent with clear provenance.

**Key Features**:
- No raw logs, only structured recommendations
- Links to `triage_results` via foreign key (provenance chain)
- References `runbook_steps` via `retrieved_step_ids` array
- References `incident_signatures` via `used_signature_ids` array
- Execution tracking (status, timestamps, notes)

**Architecture Alignment**:
- Implements Resolution Output Contract (Section 7.5)
- Resolution Agent MUST NOT re-classify (Section 7.4)
- Every recommendation has provenance (Section 11)

**Indexes**:
- Foreign keys to incidents and triage_results
- Filtering indexes (risk_level, overall_confidence, execution_status)
- GIN indexes for array searches (retrieved_step_ids, used_signature_ids)
- GIN index for JSONB recommendations
- Time-based indexes for analytics

---

## Index Strategy

### Primary Indexes (Vector Similarity)
- `runbook_steps.embedding` → IVFFlat for semantic search
- `incident_signatures.embedding` → IVFFlat for semantic search

### Secondary Indexes (Hybrid Retrieval)
- Full-text search (GIN on tsvector)
- Metadata filtering (B-tree on service, component, failure_type, etc.)

### Supporting Indexes
- Foreign keys (B-tree)
- Array searches (GIN on arrays)
- JSONB queries (GIN on JSONB)
- Time-based analytics (B-tree on timestamps)

**Total**: 32 indexes across 4 tables

See `INDEX_STRATEGY.md` for detailed index documentation.

---

## Data Flow

### Triage Flow
1. Alert received → `incidents` table
2. Triage Agent retrieves `incident_signatures` (vector search)
3. Classification stored in `triage_results` (references matched signatures)
4. Policy band determined from classification

### Resolution Flow
1. Triage result available → `triage_results` table
2. Resolution Agent retrieves `runbook_steps` (vector search, filtered by triage)
3. Recommendations stored in `resolution_outputs` (references steps and signatures)
4. Human reviews and executes recommendations

### Provenance Chain
```
incidents.id
    → triage_results.incident_id
        → triage_results.matched_signature_ids
            → incident_signatures.incident_signature_id
        → resolution_outputs.triage_result_id
            → resolution_outputs.retrieved_step_ids
                → runbook_steps.step_id
```

---

## Example Records

See `examples_storage_vector_design.sql` for:
- 4 example `runbook_steps` records
- 4 example `incident_signatures` records
- 3 example `triage_results` records
- 3 example `resolution_outputs` records
- Query examples demonstrating usage

---

## Migration Path

### Option 1: New Tables (Recommended)
1. Create new tables alongside existing `chunks` table
2. Migrate data from `chunks` to new tables
3. Update application code to use new tables
4. Deprecate old `chunks` usage for runbook steps and incident signatures

### Option 2: Replace Existing
1. Create new tables
2. Migrate data
3. Drop old `chunks` table (or repurpose for other document types)

### Migration Script Considerations
- Generate embeddings for existing data
- Map `chunks.metadata` to new table structures
- Preserve foreign key relationships
- Update indexes after bulk inserts

---

## Compliance with Architecture

### ✅ Architecture Requirements Met

1. **No mixed-purpose tables**: Each table has single, clear purpose
2. **No raw logs in resolution tables**: Only structured data
3. **Clear foreign keys**: Provenance chain from incidents → triage → resolution
4. **Vector embeddings aligned**: 
   - `runbook_steps`: "what action to take"
   - `incident_signatures`: "what kind of incident is this"
5. **Separation of concerns**:
   - Triage Agent uses `incident_signatures`
   - Resolution Agent uses `runbook_steps`
6. **Provenance**: Every recommendation references source steps and signatures

### Architecture Sections Referenced

- Section 3.1: Runbook Steps (atomic, independently embedded)
- Section 3.2: Incident Signatures (patterns, not stories)
- Section 4.2: Retrieval Boundaries
- Section 5: Triage Agent (classification only)
- Section 7: Resolution Agent (recommendations with provenance)
- Section 9: Storage Model (conceptual table list)
- Section 11: Invariants (provenance, confidence, separation)

---

## Files

1. **`schema_storage_vector_design.sql`**: Complete schema with tables, indexes, triggers, views
2. **`examples_storage_vector_design.sql`**: Example records and query patterns
3. **`INDEX_STRATEGY.md`**: Comprehensive index documentation
4. **`STORAGE_VECTOR_DESIGN_SUMMARY.md`**: This document

---

## Next Steps

1. Review schema design with team
2. Generate actual vector embeddings for example records
3. Create migration script from existing `chunks` table
4. Update application code to use new tables
5. Test query performance with production-like data volumes
6. Monitor index usage and optimize as needed

