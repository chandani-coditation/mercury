#!/bin/bash
# Script to restart the ingestion service

echo "🔄 Restarting ingestion service..."

# Kill existing uvicorn processes for ingestion
pkill -f "uvicorn.*ingestion.main:app" || echo "  No existing ingestion service found"

# Wait a moment
sleep 2

# Start the service
echo "  Starting ingestion service on port 8000..."
cd "$(dirname "$0")/.."
source venv/bin/activate
python -m uvicorn ingestion.main:app --host 0.0.0.0 --port 8000 --reload &

echo "  ✓ Ingestion service should be starting..."
echo "  Check: curl http://localhost:8000/health"
echo "  Docs: http://localhost:8000/docs"

