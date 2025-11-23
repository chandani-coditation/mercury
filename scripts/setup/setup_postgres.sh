#!/bin/bash
# Ensure Homebrew binaries are on PATH for macOS (Apple Silicon default)
export PATH="/opt/homebrew/bin:$PATH"

# Setup script for Postgres with pgvector

set -e

echo "🗄️  Setting up Postgres with pgvector"
echo "====================================="
echo ""

# Check if container exists
if docker ps -a | grep -q noc-pg; then
    echo "⚠️  Container 'noc-pg' already exists"
    read -p "Remove existing container? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker stop noc-pg 2>/dev/null || true
        docker rm noc-pg
        echo "✓ Removed existing container"
    else
        echo "Using existing container"
        docker start noc-pg 2>/dev/null || true
        exit 0
    fi
fi

# Try to use pgvector-enabled image
echo "📦 Pulling pgvector-enabled Postgres image..."
if docker pull pgvector/pgvector:pg16 >/dev/null 2>&1; then
    echo "✓ Using pgvector/pgvector:pg16 image"
    IMAGE="pgvector/pgvector:pg16"
else
    echo "⚠️  pgvector image not available, using standard postgres:16"
    echo "   You'll need to install pgvector manually"
    IMAGE="postgres:16"
fi

# Start container
echo "🚀 Starting Postgres container..."
docker run --name noc-pg \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=nocdb \
    -p 5432:5432 \
    -d "$IMAGE"

echo "⏳ Waiting for Postgres to be ready..."
sleep 5

# Wait for Postgres to be ready
for i in {1..30}; do
    if docker exec -i noc-pg psql -U postgres -c "SELECT 1;" >/dev/null 2>&1; then
        echo "✓ Postgres is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Postgres failed to start"
        exit 1
    fi
    sleep 1
done

# Install extensions
echo "🔧 Installing database extensions..."
docker exec -i noc-pg psql -U postgres -d nocdb <<EOF
-- Try to create vector extension
DO \$\$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
    RAISE NOTICE 'pgvector extension created';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pgvector extension not available. Error: %', SQLERRM;
        RAISE NOTICE 'You may need to install pgvector manually or use pgvector/pgvector:pg16 image';
END
\$\$;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOF

# Verify extensions
echo ""
echo "🔍 Verifying extensions..."
if docker exec -i noc-pg psql -U postgres -d nocdb -c "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp');" | grep -q vector; then
    echo "✓ pgvector extension: INSTALLED"
else
    echo "⚠️  pgvector extension: NOT FOUND"
    echo "   Full-text search (tsvector) is built into Postgres and will work"
    echo ""
    echo "To install pgvector manually:"
    echo "  docker exec -it noc-pg bash"
    echo "  apt-get update"
    echo "  apt-get install -y postgresql-16-pgvector"
    echo "  exit"
    echo "  docker restart noc-pg"
fi

if docker exec -i noc-pg psql -U postgres -d nocdb -c "SELECT extname FROM pg_extension WHERE extname = 'uuid-ossp';" | grep -q uuid-ossp; then
    echo "✓ uuid-ossp extension: INSTALLED"
else
    echo "⚠️  uuid-ossp extension: NOT FOUND"
fi

echo ""
echo "✅ Postgres setup complete!"
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: nocdb"
echo "  User: postgres"
echo "  Password: postgres"
echo ""
echo "Next steps:"
echo "  1. Run: python scripts/init_db.py"
echo "  2. Run: python scripts/data/ingest_data.py --dir data/faker_output"



