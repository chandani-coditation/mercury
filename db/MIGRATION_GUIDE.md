# Migration Guide: Storage & Vector Schema

This guide explains how to apply the new storage and vector schema tables (`runbook_steps`, `incident_signatures`, `triage_results`, `resolution_outputs`) to your database during restart or initialization.

## Quick Start

### For Existing Databases (Production)

```bash
# Run all migrations (including new one)
python scripts/db/run_migration.py
```

This will automatically apply migration `004_add_storage_vector_tables.sql`.

### For Fresh Installs

```bash
# Initialize base schema (includes new tables)
python scripts/db/init_db.py
```

The new tables are already included in `schema.sql`, so fresh installs get them automatically.

---

## Detailed Instructions

### For Existing Databases (Production)

If you have an existing database with data:

1. **Backup your database first**:
   ```bash
   pg_dump -U postgres -d nocdb > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Apply migration** (idempotent - safe to run multiple times):
   ```bash
   python scripts/db/run_migration.py
   ```

   This will run all migrations in `db/migrations/` including `004_add_storage_vector_tables.sql`.

3. **Verify tables were created**:
   ```sql
   SELECT table_name 
   FROM information_schema.tables
   WHERE table_name IN ('runbook_steps', 'incident_signatures', 'triage_results', 'resolution_outputs');
   ```

The migration file (`004_add_storage_vector_tables.sql`) uses `IF NOT EXISTS` clauses, so it's safe to run multiple times.

---

### For Fresh Installs

If you're setting up a new database:

1. **Initialize base schema** (includes new tables):
   ```bash
   python scripts/db/init_db.py
   ```

   The new tables are already included in `schema.sql`, so they'll be created automatically.

---

## During Service Restart

### Docker Compose

If using Docker Compose, you can add the migration to your startup sequence:

```yaml
# docker-compose.yml
services:
  ai-service:
    # ... other config ...
    command: >
      sh -c "
        python scripts/db/run_migration.py &&
        python -m ai_service.main
      "
```

### Manual Restart

1. **Stop services**:
   ```bash
   docker-compose down
   # or
   systemctl stop ai-service
   ```

2. **Apply migration**:
   ```bash
   python scripts/db/run_migration.py
   ```

3. **Start services**:
   ```bash
   docker-compose up -d
   # or
   systemctl start ai-service
   ```

---

## Manual SQL Execution

If you prefer to run SQL directly:

### Using psql

```bash
# Connect to database
psql -U postgres -d nocdb

# Run migration
\i db/migrations/004_add_storage_vector_tables.sql
```

### Using Python Script

```python
from db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

with open('db/migrations/004_add_storage_vector_tables.sql', 'r') as f:
    cur.execute(f.read())

conn.commit()
cur.close()
conn.close()
```

---

## Verification

After applying the schema, verify it was created correctly:

### Check Tables Exist

```sql
SELECT table_name 
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('runbook_steps', 'incident_signatures', 'triage_results', 'resolution_outputs')
ORDER BY table_name;
```

Expected output:
```
     table_name
---------------------
 incident_signatures
 resolution_outputs
 runbook_steps
 triage_results
```

### Check Indexes

```sql
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('runbook_steps', 'incident_signatures', 'triage_results', 'resolution_outputs')
ORDER BY tablename, indexname;
```

### Check Vector Indexes

```sql
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE tablename IN ('runbook_steps', 'incident_signatures')
  AND indexname LIKE '%embedding%'
ORDER BY tablename;
```

---

## Troubleshooting

### Error: "relation already exists"

This is normal if tables already exist. The migration uses `IF NOT EXISTS`, so it's safe to ignore or re-run.

### Error: "extension vector does not exist"

Install the pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

If using Docker, ensure the Postgres image includes pgvector, or use a custom image like `pgvector/pgvector`.

### Error: "foreign key constraint fails"

Ensure the `incidents` table exists first. Run the base schema:

```bash
python scripts/db/init_db.py
```

### Vector Index Build Fails

If you have existing data, vector indexes may take time to build. For large tables, use `CONCURRENTLY`:

```sql
CREATE INDEX CONCURRENTLY runbook_steps_embedding_idx 
    ON runbook_steps 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);
```

---

## Rollback

If you need to rollback (remove the new tables):

```sql
-- WARNING: This will delete all data in these tables!
DROP TABLE IF EXISTS resolution_outputs CASCADE;
DROP TABLE IF EXISTS triage_results CASCADE;
DROP TABLE IF EXISTS incident_signatures CASCADE;
DROP TABLE IF EXISTS runbook_steps CASCADE;

-- Drop views
DROP VIEW IF EXISTS triage_to_resolution_chain;
DROP VIEW IF EXISTS runbook_steps_with_metadata;

-- Drop functions (if not used elsewhere)
DROP FUNCTION IF EXISTS update_updated_at() CASCADE;
DROP FUNCTION IF EXISTS update_runbook_steps_tsv() CASCADE;
DROP FUNCTION IF EXISTS update_incident_signatures_tsv() CASCADE;
```

**Note**: Only rollback if absolutely necessary. Consider backing up data first.

---

## Migration Files

| File | Purpose | When to Use |
|------|---------|-------------|
| `db/migrations/004_add_storage_vector_tables.sql` | Migration script (idempotent) | Existing databases, production |
| `db/schema.sql` | Base schema (includes new tables) | Fresh installs |
| `db/schema_storage_vector_design.sql` | Complete schema reference | Documentation, reference |

---

## Next Steps

After applying the schema:

1. **Migrate existing data** (if any):
   - Migrate runbook steps from `chunks` table to `runbook_steps`
   - Migrate incident signatures from `chunks` table to `incident_signatures`
   - See `examples_storage_vector_design.sql` for data format

2. **Update application code**:
   - Update repositories to use new tables
   - Update retrieval logic to use new vector indexes
   - Test with sample data

3. **Monitor performance**:
   - Check index usage: `SELECT * FROM pg_stat_user_indexes WHERE ...`
   - Monitor query performance
   - Adjust index parameters if needed

---

## Support

For issues or questions:
- Check `db/INDEX_STRATEGY.md` for index details
- Check `db/STORAGE_VECTOR_DESIGN_SUMMARY.md` for design rationale
- Check `db/QUICK_REFERENCE.md` for quick lookup

