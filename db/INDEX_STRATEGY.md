# Index Strategy for Storage & Vector Schema

This document outlines the comprehensive index strategy for the four core tables: `runbook_steps`, `incident_signatures`, `triage_results`, and `resolution_outputs`.

## Index Categories

### 1. Vector Similarity Indexes (Primary Retrieval)

**Purpose**: Enable fast semantic similarity search using cosine distance.

**Tables**:
- `runbook_steps.embedding` → `runbook_steps_embedding_idx` (IVFFlat)
- `incident_signatures.embedding` → `incident_signatures_embedding_idx` (IVFFlat)

**Index Type**: `ivfflat` with `vector_cosine_ops`
- Lists: 100 (tuned for ~10K-100K records)
- Operations: Cosine similarity (`<=>` operator)

**Usage**:
- Resolution Agent: Vector search on `runbook_steps` to find semantically similar steps
- Triage Agent: Vector search on `incident_signatures` to find matching patterns

**Query Pattern**:
```sql
SELECT * FROM runbook_steps
ORDER BY embedding <=> query_embedding::vector(1536)
LIMIT 10;
```

**Maintenance**:
- Rebuild index after bulk inserts: `REINDEX INDEX runbook_steps_embedding_idx;`
- Monitor index size and query performance
- Adjust `lists` parameter based on table size

---

### 2. Full-Text Search Indexes (Hybrid Retrieval)

**Purpose**: Enable keyword-based search for hybrid retrieval (vector + keyword).

**Tables**:
- `runbook_steps.tsv` → `runbook_steps_tsv_idx` (GIN)
- `incident_signatures.tsv` → `incident_signatures_tsv_idx` (GIN)

**Index Type**: `GIN` on `tsvector`
- Language: English
- Auto-updated via triggers

**Usage**:
- Hybrid retrieval combining vector similarity and keyword matching
- RRF (Reciprocal Rank Fusion) or MMR (Maximal Marginal Relevance) ranking

**Query Pattern**:
```sql
SELECT * FROM runbook_steps
WHERE tsv @@ to_tsquery('english', 'authentication & error')
ORDER BY embedding <=> query_embedding::vector(1536);
```

---

### 3. Foreign Key Indexes (Join Performance)

**Purpose**: Optimize foreign key lookups and joins.

**Tables**:
- `runbook_steps.runbook_document_id` → `runbook_steps_runbook_document_id_idx`
- `incident_signatures.source_document_id` → `incident_signatures_source_document_id_idx`
- `triage_results.incident_id` → `triage_results_incident_id_idx`
- `resolution_outputs.incident_id` → `resolution_outputs_incident_id_idx`
- `resolution_outputs.triage_result_id` → `resolution_outputs_triage_result_id_idx`

**Index Type**: `B-tree` (default)

**Usage**:
- Joins between tables
- Cascading deletes
- Foreign key constraint enforcement

---

### 4. Filtering Indexes (Metadata Queries)

**Purpose**: Enable fast filtering by metadata fields for hybrid retrieval.

#### runbook_steps
- `runbook_id` → `runbook_steps_runbook_id_idx` (B-tree)
- `service` → `runbook_steps_service_idx` (B-tree, partial: `WHERE service IS NOT NULL`)
- `component` → `runbook_steps_component_idx` (B-tree, partial: `WHERE component IS NOT NULL`)
- `risk_level` → `runbook_steps_risk_level_idx` (B-tree, partial: `WHERE risk_level IS NOT NULL`)

#### incident_signatures
- `failure_type` → `incident_signatures_failure_type_idx` (B-tree)
- `error_class` → `incident_signatures_error_class_idx` (B-tree)
- `affected_service` → `incident_signatures_affected_service_idx` (B-tree, partial)
- `service` → `incident_signatures_service_idx` (B-tree, partial)
- `component` → `incident_signatures_component_idx` (B-tree, partial)

#### triage_results
- `failure_type` → `triage_results_failure_type_idx` (B-tree)
- `error_class` → `triage_results_error_class_idx` (B-tree)
- `severity` → `triage_results_severity_idx` (B-tree)
- `policy_band` → `triage_results_policy_band_idx` (B-tree)
- `confidence` → `triage_results_confidence_idx` (B-tree)

#### resolution_outputs
- `risk_level` → `resolution_outputs_risk_level_idx` (B-tree)
- `overall_confidence` → `resolution_outputs_overall_confidence_idx` (B-tree)
- `execution_status` → `resolution_outputs_execution_status_idx` (B-tree, partial)

**Usage**:
- Filtering in WHERE clauses
- Hybrid retrieval combining vector search with metadata filters
- Analytics and reporting queries

**Query Pattern**:
```sql
SELECT * FROM runbook_steps
WHERE service = 'database'
  AND risk_level = 'low'
ORDER BY embedding <=> query_embedding::vector(1536)
LIMIT 10;
```

---

### 5. Array Indexes (GIN)

**Purpose**: Enable fast searches within array columns.

**Tables**:
- `incident_signatures.symptoms` → `incident_signatures_symptoms_idx` (GIN)
- `incident_signatures.resolution_refs` → `incident_signatures_resolution_refs_idx` (GIN)
- `triage_results.matched_signature_ids` → `triage_results_matched_signature_ids_idx` (GIN)
- `resolution_outputs.retrieved_step_ids` → `resolution_outputs_retrieved_step_ids_idx` (GIN)
- `resolution_outputs.used_signature_ids` → `resolution_outputs_used_signature_ids_idx` (GIN)

**Index Type**: `GIN` (Generalized Inverted Index)

**Usage**:
- Check if array contains a value: `WHERE 'RB123-S3' = ANY(resolution_refs)`
- Find records referencing a specific step or signature
- Provenance queries

**Query Pattern**:
```sql
SELECT * FROM incident_signatures
WHERE 'RB123-S3' = ANY(resolution_refs);
```

---

### 6. JSONB Indexes (Structured Data)

**Purpose**: Enable fast queries on JSONB columns.

**Tables**:
- `resolution_outputs.recommendations` → `resolution_outputs_recommendations_idx` (GIN)

**Index Type**: `GIN` on JSONB

**Usage**:
- Query recommendations by step_id within JSONB
- Extract specific fields from recommendations
- Analytics on recommendation structure

**Query Pattern**:
```sql
SELECT * FROM resolution_outputs
WHERE recommendations @> '[{"step_id": "RB123-S3"}]'::jsonb;
```

---

### 7. Time-Based Indexes (Analytics)

**Purpose**: Enable time-range queries for analytics and MTTR calculations.

**Tables**:
- `triage_results.created_at` → `triage_results_created_at_idx` (B-tree)
- `triage_results.completed_at` → `triage_results_completed_at_idx` (B-tree, partial)
- `resolution_outputs.created_at` → `resolution_outputs_created_at_idx` (B-tree)
- `resolution_outputs.proposed_at` → `resolution_outputs_proposed_at_idx` (B-tree, partial)
- `resolution_outputs.accepted_at` → `resolution_outputs_accepted_at_idx` (B-tree, partial)

**Usage**:
- MTTR calculations
- Time-series analytics
- Performance monitoring
- Audit trails

**Query Pattern**:
```sql
SELECT 
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) AS triage_count,
    AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) AS avg_triage_time
FROM triage_results
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day;
```

---

### 8. Unique Constraints

**Purpose**: Ensure data integrity and prevent duplicates.

**Tables**:
- `runbook_steps.step_id` → `runbook_steps_step_id_unique_idx` (UNIQUE)
- `incident_signatures.incident_signature_id` → `incident_signatures_signature_id_unique_idx` (UNIQUE)

**Usage**:
- Prevent duplicate step_ids or signature_ids
- Enable upsert operations
- Data validation

---

## Index Maintenance Strategy

### Monitoring

1. **Index Bloat**: Monitor index size vs. table size
   ```sql
   SELECT 
       schemaname, tablename, indexname,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
   FROM pg_stat_user_indexes
   ORDER BY pg_relation_size(indexrelid) DESC;
   ```

2. **Index Usage**: Track which indexes are actually used
   ```sql
   SELECT 
       schemaname, tablename, indexname,
       idx_scan, idx_tup_read, idx_tup_fetch
   FROM pg_stat_user_indexes
   WHERE schemaname = 'public'
   ORDER BY idx_scan DESC;
   ```

3. **Query Performance**: Use `EXPLAIN ANALYZE` to verify index usage

### Maintenance Tasks

1. **Regular VACUUM**: Keep tables and indexes updated
   ```sql
   VACUUM ANALYZE runbook_steps;
   VACUUM ANALYZE incident_signatures;
   ```

2. **Rebuild Vector Indexes**: After bulk inserts
   ```sql
   REINDEX INDEX runbook_steps_embedding_idx;
   REINDEX INDEX incident_signatures_embedding_idx;
   ```

3. **Update Statistics**: For query planner
   ```sql
   ANALYZE runbook_steps;
   ANALYZE incident_signatures;
   ANALYZE triage_results;
   ANALYZE resolution_outputs;
   ```

---

## Index Selection Guidelines

### For Resolution Agent (Retrieving Runbook Steps)

1. **Primary**: Vector similarity on `runbook_steps.embedding`
2. **Secondary**: Metadata filters (service, component, risk_level)
3. **Tertiary**: Full-text search on `runbook_steps.tsv` (for hybrid retrieval)

### For Triage Agent (Retrieving Incident Signatures)

1. **Primary**: Vector similarity on `incident_signatures.embedding`
2. **Secondary**: Metadata filters (failure_type, error_class, service)
3. **Tertiary**: Full-text search on `incident_signatures.tsv` (for hybrid retrieval)

### For Analytics Queries

1. **Time-based**: Use time indexes for range queries
2. **Aggregations**: Use filtering indexes for GROUP BY operations
3. **Joins**: Use foreign key indexes

---

## Performance Considerations

### Vector Index Tuning

- **Lists Parameter**: 
  - Small tables (<10K): lists = 10-50
  - Medium tables (10K-100K): lists = 100 (current)
  - Large tables (>100K): lists = 200-500

- **Index Build Time**: IVFFlat indexes build quickly but may need periodic rebuilding

### Partial Indexes

- Use partial indexes (WHERE clause) for sparse columns
- Reduces index size and improves maintenance
- Examples: `service`, `component`, `risk_level` (when NULL is common)

### GIN Indexes

- Larger than B-tree indexes but faster for array/JSONB queries
- Slower updates, so batch inserts when possible
- Monitor size and rebuild if needed

---

## Index Summary Table

| Table | Index Type | Count | Purpose |
|-------|-----------|-------|---------|
| `runbook_steps` | Vector (IVFFlat) | 1 | Semantic search |
| `runbook_steps` | Full-text (GIN) | 1 | Keyword search |
| `runbook_steps` | B-tree | 5 | Filtering, foreign keys |
| `runbook_steps` | Unique | 1 | Data integrity |
| `incident_signatures` | Vector (IVFFlat) | 1 | Semantic search |
| `incident_signatures` | Full-text (GIN) | 1 | Keyword search |
| `incident_signatures` | B-tree | 6 | Filtering, foreign keys |
| `incident_signatures` | GIN (array) | 2 | Array searches |
| `incident_signatures` | Unique | 1 | Data integrity |
| `triage_results` | B-tree | 8 | Filtering, foreign keys, time |
| `triage_results` | GIN (array) | 1 | Array searches |
| `resolution_outputs` | B-tree | 7 | Filtering, foreign keys, time |
| `resolution_outputs` | GIN (array) | 2 | Array searches |
| `resolution_outputs` | GIN (JSONB) | 1 | JSONB queries |
| **Total** | | **32** | |

---

## Migration Notes

When applying these indexes:

1. **Create indexes in order**: Foreign keys first, then filtering, then vector
2. **Use CONCURRENTLY**: For production, use `CREATE INDEX CONCURRENTLY` to avoid locks
3. **Monitor disk space**: Vector indexes can be large
4. **Test query performance**: Verify index usage with EXPLAIN ANALYZE

Example concurrent index creation:
```sql
CREATE INDEX CONCURRENTLY runbook_steps_embedding_idx 
    ON runbook_steps 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);
```

