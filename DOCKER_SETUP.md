# Docker Setup and Testing Guide

## Prerequisites

1. **Docker and Docker Compose** installed
2. **OpenAI API Key** - Required for AI service

## Quick Setup

### 1. Set Environment Variables

Create a `.env` file in the project root (if it doesn't exist):

```bash
# Required
OPENAI_API_KEY=your-openai-api-key-here

# Optional
LOG_LEVEL=INFO
```

### 2. Build and Start Services

```bash
# Build and start all services
docker-compose up -d --build

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f ai-service
docker-compose logs -f ui
docker-compose logs -f postgres
```

### 3. Verify Services are Running

```bash
# Check service status
docker-compose ps

# Check health endpoints
curl http://localhost:8001/api/v1/health
curl http://localhost:8001/api/v1/health/ready
curl http://localhost:8002/health
```

### 4. Access Services

- **UI**: http://localhost:3000
- **AI Service API**: http://localhost:8001
- **AI Service Docs**: http://localhost:8001/docs
- **Ingestion Service**: http://localhost:8002
- **Prometheus**: http://localhost:9090
- **PostgreSQL**: localhost:5432

## Manual Testing Steps

### Step 1: Ingest Sample Data

First, we need to populate the database with historical data for context retrieval.

```bash
# Option A: Use the ingestion API
curl -X POST http://localhost:8002/ingest/runbook \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Restart Procedure",
    "service": "database",
    "component": "postgres",
    "content": "1. Check active connections\n2. Graceful shutdown\n3. Restart service\n4. Verify health",
    "tags": {"category": "operations"}
  }'

# Option B: Use Python script (if running locally)
# python scripts/data/generate_fake_data.py --all --count 20
# python scripts/data/ingest_data.py --dir data/faker_output
```

### Step 2: Test Triage (Synchronous)

```bash
curl -X POST http://localhost:8001/api/v1/triage \
  -H "Content-Type: application/json" \
  -d '{
    "title": "High CPU Usage Detected",
    "description": "CPU usage exceeded 90% for 5 minutes",
    "source": "prometheus",
    "labels": {
      "service": "api-gateway",
      "component": "api",
      "severity": "high"
    }
  }'
```

**Expected Response:**
- `incident_id`: UUID
- `triage`: Object with severity, category, confidence, summary, etc.
- `policy_band`: AUTO, PROPOSE, or REVIEW
- `evidence_chunks`: Retrieved context chunks

### Step 3: Test Triage (State-Based HITL)

```bash
curl -X POST "http://localhost:8001/api/v1/triage?use_state=true" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Connection Pool Exhausted",
    "description": "Application unable to acquire database connections",
    "source": "prometheus",
    "labels": {
      "service": "database",
      "component": "postgres"
    }
  }'
```

**Expected Response:**
- `incident_id`: UUID
- `state`: AgentState object with current_step, policy_band, etc.
- `pending_action`: May be present if policy requires approval

### Step 4: Test Resolution

```bash
# First, get the incident_id from Step 2 or 3
INCIDENT_ID="<incident-id-from-triage>"

# Generate resolution
curl -X POST "http://localhost:8001/api/v1/resolution?incident_id=${INCIDENT_ID}" \
  -H "Content-Type: application/json"
```

**Expected Response:**
- `incident_id`: UUID
- `resolution`: Object with resolution_steps, commands, rollback_plan, etc.
- `policy_band`: Policy decision
- `evidence_chunks`: Retrieved context chunks

### Step 5: Test State-Based Resolution

```bash
curl -X POST "http://localhost:8001/api/v1/resolution?incident_id=${INCIDENT_ID}&use_state=true" \
  -H "Content-Type: application/json"
```

**Expected Response:**
- `incident_id`: UUID
- `state`: AgentState with resolution workflow state
- `pending_action`: May be present if review required

### Step 6: Test WebSocket State Streaming

```bash
# Connect to WebSocket (use wscat or similar tool)
# wscat -c ws://localhost:8001/api/v1/agents/${INCIDENT_ID}/state

# Or use browser DevTools Console:
# const ws = new WebSocket('ws://localhost:8001/api/v1/agents/${INCIDENT_ID}/state');
# ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

### Step 7: Test Feedback Endpoint

```bash
curl -X PUT "http://localhost:8001/api/v1/incidents/${INCIDENT_ID}/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "feedback_type": "triage",
    "approved": true,
    "user_edited": {
      "severity": "high",
      "category": "database",
      "confidence": 0.95,
      "summary": "Updated summary",
      "likely_cause": "Connection pool too small"
    },
    "notes": "Reviewed and approved with edits"
  }'
```

### Step 8: Test Health Checks

```bash
# Basic health
curl http://localhost:8001/api/v1/health

# Readiness check (with dependency verification)
curl http://localhost:8001/api/v1/health/ready

# Liveness check
curl http://localhost:8001/api/v1/health/live
```

### Step 9: Test UI

1. Open http://localhost:3000 in browser
2. Click "+ New Triage" button
3. Fill in alert details and submit
4. Watch the workflow progress in real-time
5. If policy requires approval, review form will appear
6. Test keyboard shortcuts:
   - `Ctrl+K` - Focus search
   - `Ctrl+N` - New triage
   - `Escape` - Close modal/back
   - `Ctrl+R` - Refresh
7. Test theme toggle (moon/sun icon)
8. Test bulk operations (select multiple incidents)

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Database Connection Issues

```bash
# Check PostgreSQL is healthy
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Verify connection from ai-service
docker-compose exec ai-service python -c "from db.connection import get_db_connection; conn = get_db_connection(); print('Connected!'); conn.close()"
```

### OpenAI API Issues

```bash
# Verify API key is set
docker-compose exec ai-service env | grep OPENAI_API_KEY

# Test LLM connection
curl -X POST http://localhost:8001/api/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "description": "Test", "source": "test"}'
```

### UI Not Loading

```bash
# Check UI logs
docker-compose logs ui

# Verify nginx is proxying correctly
curl http://localhost:3000/api/v1/health

# Rebuild UI
docker-compose build ui
docker-compose up -d ui
```

### Port Conflicts

If ports are already in use:

```bash
# Edit docker-compose.yml to change ports:
# - "8001:8001" → "8002:8001" (for ai-service)
# - "3000:80" → "3001:80" (for ui)
```

## Clean Up

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (deletes database data)
docker-compose down -v

# Remove all containers, networks, and volumes
docker-compose down -v --remove-orphans
```

## Useful Commands

```bash
# View real-time logs
docker-compose logs -f

# Execute command in container
docker-compose exec ai-service python -c "from ai_service.core import get_logger; logger = get_logger('test'); logger.info('Test')"

# Access database
docker-compose exec postgres psql -U noc_ai -d noc_ai

# Check metrics
curl http://localhost:8001/metrics

# Restart specific service
docker-compose restart ai-service
```

## Next Steps

1. Ingest more historical data for better context retrieval
2. Test different policy bands (AUTO, PROPOSE, REVIEW)
3. Test HITL workflows with state-based agents
4. Monitor metrics at http://localhost:9090 (Prometheus)
5. Review logs in `./logs/` directory

