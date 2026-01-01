# Quick Start: Apply Storage & Vector Schema

## TL;DR - Apply During Restart

### For Existing Databases

```bash
# Run all migrations (includes new storage vector tables)
python scripts/db/run_migration.py
```

### For Fresh Installs

```bash
# Initialize schema (includes new tables)
python scripts/db/init_db.py
```

That's it! The migration is idempotent and safe to run multiple times.

---

## What Gets Created

The migration creates 4 new tables:

1. **`runbook_steps`** - Atomic runbook steps with vector embeddings
2. **`incident_signatures`** - Failure patterns with vector embeddings  
3. **`triage_results`** - Classification outputs from Triage Agent
4. **`resolution_outputs`** - Recommendations from Resolution Agent

Plus:
- 38 indexes (vector, full-text, filtering, etc.)
- Triggers for auto-updating timestamps and tsvector
- Helper views for querying
- Foreign key constraints for provenance

---

## How It Works

The system uses two files:

1. **`db/schema.sql`** - Base schema for fresh installs (includes new tables)
2. **`db/migrations/004_add_storage_vector_tables.sql`** - Migration for existing databases

When you run:
- `python scripts/db/init_db.py` → Uses `schema.sql` (fresh installs)
- `python scripts/db/run_migration.py` → Runs all migrations in `db/migrations/` (existing databases)

---

## Files Created

| File | Purpose |
|------|---------|
| `db/migrations/004_add_storage_vector_tables.sql` | Migration script (idempotent) |
| `scripts/db/apply_storage_vector_schema.py` | Helper script to apply schema |
| `db/MIGRATION_GUIDE.md` | Detailed migration guide |
| `db/APPLY_SCHEMA_QUICKSTART.md` | This file |

---

## For Docker/Production

Add to your startup script or docker-compose:

```bash
# Before starting services
python scripts/db/run_migration.py
```

Or add to `docker-compose.yml`:

```yaml
command: >
  sh -c "
    python scripts/db/run_migration.py &&
    python -m ai_service.main
  "
```

---

## Verification Commands

```sql
-- Check tables exist
SELECT table_name 
FROM information_schema.tables
WHERE table_name IN ('runbook_steps', 'incident_signatures', 'triage_results', 'resolution_outputs');

-- Check vector indexes
SELECT tablename, indexname 
FROM pg_indexes 
WHERE tablename IN ('runbook_steps', 'incident_signatures')
  AND indexname LIKE '%embedding%';
```

---

## Need More Details?

- **Full migration guide**: See `db/MIGRATION_GUIDE.md`
- **Schema design**: See `db/STORAGE_VECTOR_DESIGN_SUMMARY.md`
- **Index strategy**: See `db/INDEX_STRATEGY.md`
- **Quick reference**: See `db/QUICK_REFERENCE.md`

