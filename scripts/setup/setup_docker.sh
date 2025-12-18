#!/bin/bash
# Docker Setup Script for NOC Agent AI

set -e

echo " NOC Agent AI - Docker Setup"
echo "================================"

# Check if .env exists
if [ ! -f .env ]; then
    echo "  .env file not found. Creating template..."
    cat > .env << EOF
# Required
OPENAI_API_KEY=your-openai-api-key-here

# Optional
LOG_LEVEL=INFO
EOF
    echo " Created .env file. Please edit it and add your OPENAI_API_KEY"
    echo "   Then run this script again."
    exit 1
fi

# Check if OPENAI_API_KEY is set
if grep -q "your-openai-api-key-here" .env || ! grep -q "OPENAI_API_KEY=" .env; then
    echo "  Please set OPENAI_API_KEY in .env file"
    exit 1
fi

echo " Stopping existing containers..."
docker-compose down

echo "🔨 Building Docker images..."
docker-compose build --no-cache

echo " Starting services..."
docker-compose up -d

echo " Waiting for services to be ready..."
sleep 10

echo " Checking service health..."
echo ""

# Check PostgreSQL
echo " PostgreSQL:"
if docker-compose exec -T postgres pg_isready -U noc_ai > /dev/null 2>&1; then
    echo "    Healthy"
else
    echo "    Not ready"
fi

# Check AI Service
echo " AI Service:"
if curl -s http://localhost:8001/api/v1/health > /dev/null 2>&1; then
    echo "    Healthy"
    echo "    API Docs: http://localhost:8001/docs"
else
    echo "    Not ready (check logs: docker-compose logs ai-service)"
fi

# Check Ingestion Service
echo " Ingestion Service:"
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "    Healthy"
else
    echo "    Not ready (check logs: docker-compose logs ingestion-service)"
fi

echo ""
echo " Setup complete!"
echo ""
echo " Quick Commands:"
echo "   View logs:        docker-compose logs -f"
echo "   Stop services:    docker-compose down"
echo "   Restart service:  docker-compose restart <service-name>"
echo ""
echo " See README.md for testing guide"

