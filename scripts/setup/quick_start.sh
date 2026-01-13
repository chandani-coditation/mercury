#!/bin/bash
# Ensure Homebrew binaries are on PATH for macOS (Apple Silicon default)
export PATH="/opt/homebrew/bin:$PATH"

# Quick start script for NOC Agent AI

set -e

echo " NOC Agent AI - Quick Start"
echo "=============================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo " Please edit .env and add your OPENAI_API_KEY"
    echo ""
    read -r -p "Press Enter after you've added your API key..."
fi

# Check if Postgres is running
echo " Checking if Postgres is running..."
if ! docker ps | grep -q noc-pg; then
    echo " Starting Postgres container with pgvector..."
    # Try to use pgvector-enabled image first, fallback to standard
    if docker pull pgvector/pgvector:pg16 >/dev/null 2>&1; then
        docker run --name noc-pg \
            -e POSTGRES_PASSWORD=postgres \
            -e POSTGRES_DB=nocdb \
            -p 5432:5432 \
            -d pgvector/pgvector:pg16
        echo " Using pgvector-enabled Postgres image"
    else
        echo "  pgvector image not available, using standard Postgres"
        echo "   You may need to install pgvector manually"
        docker run --name noc-pg \
            -e POSTGRES_PASSWORD=postgres \
            -e POSTGRES_DB=nocdb \
            -p 5432:5432 \
            -d postgres:16
    fi
    echo " Waiting for Postgres to be ready..."
    sleep 5
else
    echo " Postgres container is running"
fi

# Install/verify extensions
echo " Setting up database extensions..."
docker exec -i noc-pg psql -U postgres -d nocdb <<EOF
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\q
EOF

# Verify pgvector is installed
if docker exec -i noc-pg psql -U postgres -d nocdb -c "SELECT * FROM pg_extension WHERE extname = 'vector';" | grep -q vector; then
    echo " pgvector extension installed"
else
    echo "  WARNING: pgvector extension not found!"
    echo "   You may need to install it manually or use pgvector/pgvector:pg16 image"
fi

# Initialize database schema
echo "  Initializing database schema..."
python scripts/db/init_db.py

# Start services in background
echo " Starting services..."
echo "   - Ingestion service on port 8000"
echo "   - AI service on port 8001"
echo ""

# Start ingestion service
python -m ingestion.main &
INGESTION_PID=$!

# Wait a bit for ingestion service to start
sleep 2

# Start AI service
python -m ai_service.main &
AI_SERVICE_PID=$!

# Wait for services to start
sleep 3

# Ingest sample data
echo " Ingesting sample data..."
python scripts/data/ingest_data.py --dir data/faker_output

echo ""
echo " Setup complete!"
echo ""
echo "Services are running:"
echo "  - Ingestion: http://localhost:8000"
echo "  - AI Service: http://localhost:8001"
echo ""
echo "To test with mock alerts:"
echo "  python scripts/test/simulate_alerts.py"
echo ""
echo "To view MTTR metrics:"
echo "  python scripts/db/mttr_metrics.py"
echo ""
echo "To stop services, press Ctrl+C or run:"
echo "  kill $INGESTION_PID $AI_SERVICE_PID"

# Wait for user interrupt
trap 'kill "$INGESTION_PID" "$AI_SERVICE_PID" 2>/dev/null; exit' INT TERM
wait

