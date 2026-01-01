#!/bin/bash
# Fix validation issues script
# This script addresses the main issues found in validation

set -e

echo "=========================================="
echo "Validation Issues Fix Script"
echo "=========================================="

# Step 1: Install missing dependencies
echo ""
echo "Step 1: Installing missing dependencies..."
pip install python-docx psycopg || {
    echo "ERROR: Failed to install dependencies"
    exit 1
}
echo "✓ Dependencies installed"

# Step 2: Check if runbooks directory exists
echo ""
echo "Step 2: Checking runbooks directory..."
if [ ! -d "runbooks" ]; then
    echo "ERROR: runbooks directory not found"
    exit 1
fi

runbook_count=$(find runbooks -name "*.docx" | wc -l)
if [ "$runbook_count" -eq 0 ]; then
    echo "WARNING: No DOCX files found in runbooks directory"
    exit 1
fi
echo "✓ Found $runbook_count runbook file(s)"

# Step 3: Ingest runbooks
echo ""
echo "Step 3: Ingesting runbooks..."
python3 scripts/data/ingest_runbooks.py --dir runbooks --ingestion-url http://localhost:8002 || {
    echo "ERROR: Failed to ingest runbooks"
    exit 1
}
echo "✓ Runbooks ingested"

# Step 4: Verify database state
echo ""
echo "Step 4: Verifying database state..."
python3 scripts/db/verify_db.py || {
    echo "WARNING: Database verification had issues, but continuing..."
}

# Step 5: Check environment variables
echo ""
echo "Step 5: Checking database pool configuration..."
if [ -z "$DB_POOL_MAX" ]; then
    echo "WARNING: DB_POOL_MAX not set. Recommended: export DB_POOL_MAX=30"
    echo "Current default: max_size=10 (may be too small for validation)"
fi

echo ""
echo "=========================================="
echo "Fix script completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Set database pool size (if not already set):"
echo "   export DB_POOL_MIN=5"
echo "   export DB_POOL_MAX=30"
echo "   export DB_POOL_WAIT_TIMEOUT=30"
echo ""
echo "2. Restart AI service to apply pool settings"
echo ""
echo "3. Re-run validation:"
echo "   python3 scripts/data/validate_agents_enhanced.py --limit 3"
echo ""

