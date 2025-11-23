# NOC Agent AI

**Standalone AI-powered Network Operations Center (NOC) system** for automated alert triage and resolution using OpenAI LLM and hybrid search (vector + full-text).

**Note:** This is a **custom POC** that works independently. Robusta integration scripts exist but are optional - the system works perfectly without Robusta or Kubernetes.

## 📚 Documentation

- **[README.md](README.md)** - This file - Quick start, API reference, and usage guide
- **[CONTEXT.md](CONTEXT.md)** - Technical context: code structure, architecture details, and implementation
- **[TODO.md](TODO.md)** - Future tasks and improvements

## Architecture

### Current Implementation (Working Now)

```
1. Historical Data Ingestion
   └── Alerts, Incidents, Runbooks, Logs → Postgres (pgvector + tsvector)
       └── 80+ items stored with embeddings and full-text indexes

2. Alert Received (Mock/Test Script)
   └── POST /api/v1/triage → AI Service
       ├── Hybrid Search (Vector + Full-text) → Retrieves relevant chunks
       ├── LLM Triage → Generates triage with evidence + provenance
       └── Store → Incident with triage_output + triage_evidence

3. User Feedback (Triage) [Optional, configurable]
   └── PUT /api/v1/incidents/{id}/feedback (feedback_type: "triage")
       └── User can: Accept, Edit, or Reject triage output

4. Policy Gate Evaluation
   └── Evaluates severity + risk → Policy Band (AUTO/PROPOSE/REVIEW)
       └── If feedback_before_policy=true: Policy deferred until feedback received

5. Resolution Generation
   └── POST /api/v1/resolution → AI Service
       ├── Hybrid Search → Retrieves runbook-heavy context
       ├── LLM Resolution → Generates steps + rationale + evidence
       ├── Policy Gate → Sets requires_approval based on policy_band
       └── Store → Resolution with resolution_output + resolution_evidence

6. User Feedback (Resolution) [Required for REVIEW, optional for others]
   └── PUT /api/v1/incidents/{id}/feedback (feedback_type: "resolution")
       └── User can: Approve, Edit, or Reject resolution steps

7. Calibration (Optional)
   └── POST /api/v1/calibrate → Analyzes feedback patterns
       └── Suggests configuration improvements
```

**Note:** Current implementation works standalone without Kubernetes. Robusta integration is optional.

## Features

- **AI-Powered Triage**: Automated alert analysis with context from knowledge base
- **AI-Powered Resolution**: Generate actionable resolution steps with policy gates
- **Hybrid Search**: Vector similarity + full-text search with RRF (Reciprocal Rank Fusion)
- **Historical Data Ingestion**: Support for alerts, incidents, runbooks, and logs (structured and unstructured)
- **Evidence Tracking**: Stores evidence chunks used by AI agents with provenance fields
- **Policy Gates**: AUTO/PROPOSE/REVIEW bands for resolution approval (fully configurable)
- **Human Feedback**: Endpoint for analyst edits and corrections (triage and resolution)
- **Stateful HITL UI**: WebSocket-driven workflow view with hero summary, progress stepper, enhanced timeline with detailed history, and inline review forms
- **State Bus Recovery**: Agent state is persisted, reloaded on restart, and monitored for pending-action timeouts (expired reviews automatically surface as errors)
- **Keyboard Shortcuts**: Power-user shortcuts (Ctrl+K for search, Ctrl+N for new triage, Escape to close, Ctrl+R to refresh)
- **Optimistic UI Updates**: Immediate UI feedback for feedback submissions and bulk actions with automatic rollback on errors
- **Diff View & Inline Editing**: Visual before/after comparison plus inline editing controls for HITL form edits, showing all changes side-by-side without leaving the workflow
- **Sound & Visual Alerts**: Browser tab notifications and audio alerts when pending actions require attention
- **Auto-Refresh**: Automatic refresh of insight cards and incident list every 30 seconds for real-time updates
- **Light/Dark Theme Toggle**: Switch between light and dark themes with preference persistence
- **Undo/Redo**: Full undo/redo support for HITL form edits with keyboard shortcuts (Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y)
- **Calibration**: Analyze feedback patterns to suggest configuration improvements
- **Configuration-Driven**: All behavior controlled via `config/` directory (no code changes needed)
- **Standardized Logging**: Structured logging with daily log file rotation (organized by date)
- **Prometheus Metrics**: Comprehensive metrics for monitoring and observability
- **Docker Support**: Full Docker Compose setup for easy deployment
- **Unit Tests**: pytest-based testing infrastructure with coverage
- **Code Quality**: Black, flake8, and mypy for code standards

## Quick Start

### Prerequisites

- Python 3.9+
- Docker and Docker Compose (for full stack deployment)
- OpenAI API key
- (Optional) Kubernetes + Helm for Robusta integration

### 1. Set Up Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# Or use helper script:
source scripts/setup/activate_venv.sh

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

**Note:** Always activate the virtual environment before running scripts or services.

### 2. Set Up Environment

```bash
cp .env.example .env
# Edit .env with your OpenAI API key:
# OPENAI_API_KEY=your-key-here
```

### 3. Start All Services with Docker Compose (Recommended)

This will start the entire stack including UI, backend, database, and ingestion service:

```bash
# Start all services (UI, AI Service, Ingestion Service, PostgreSQL, Prometheus)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Rebuild and restart (after code changes)
docker-compose up -d --build
```

**Services will be available at:**
- **UI (Frontend)**: http://localhost:3000
- **AI Service API**: http://localhost:8001
- **Ingestion Service API**: http://localhost:8002
- **PostgreSQL**: localhost:5432
- **Prometheus**: http://localhost:9090

**Note**: The UI is served via nginx and proxies API requests to the backend automatically.

**Or start Postgres only (for local development):**
```bash
docker run --name noc-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=nocdb \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16
```

### 4. Initialize Database

```bash
# Make sure virtual environment is activated
source venv/bin/activate

python scripts/db/init_db.py
python scripts/db/run_migration.py  # Run migrations for new features

# (Optional) Cleanup data safely (dry-run or confirmed wipe)
# Dry run: shows statements without executing
python scripts/data/cleanup_data.py --dry-run
# Wipe everything (requires --yes)
python scripts/data/cleanup_data.py --yes
# Or selective wipes
python scripts/data/cleanup_data.py --yes --incidents --feedback
```

### 5. Start Services (If not using Docker Compose)

**Terminal 1 - Ingestion Service:**
```bash
source venv/bin/activate
python -m uvicorn ingestion.main:app --host 0.0.0.0 --port 8002
```

**Terminal 2 - AI Service:**
```bash
source venv/bin/activate
# Set environment variables
export LOG_LEVEL=INFO
export OPENAI_API_KEY=your-key-here
python -m uvicorn ai_service.main:app --host 0.0.0.0 --port 8001 --reload
```

### 6. Ingest Sample Data

**Option A: Using LLM to generate fake data (recommended):**
```bash
source venv/bin/activate
python scripts/data/generate_fake_data.py --all --count 20 --output-dir data/faker_output
# Adjust content scale via env var (affects size/length):
FAKER_SIZE=xl python scripts/data/generate_fake_data.py --type log --count 2 --output-dir data/faker_output --save-only
```

**Features:**
- ✅ **Automatic large log chunking** - Logs >900KB are automatically split by lines before upload
- ✅ **Batch embedding generation** - Server processes chunks in batches (10-100x faster)
- ✅ **Improved error handling** - Detailed error messages with content size information
- ✅ **Multi-thousand-line logs** - Use `--synth-logs --log-lines 8000` for realistic large logs

Save-only (review files first, no upload):
```bash
python scripts/data/generate_fake_data.py --type incident --count 10 --output-dir data/faker_output --save-only
```

**Option B: Ingest existing JSONL files:**
```bash
source venv/bin/activate
# Ingest all JSONL files from data/faker_output (auto-detects type from filename)
python scripts/data/ingest_data.py --dir data/faker_output
```

### 7. Test the System

```bash
source venv/bin/activate

# Test end-to-end triage and resolution pipeline (recommended)
python scripts/test/test_triage_and_resolution.py --verbose

# Test Robusta integration flow WITHOUT K8s (simulates Robusta playbook + feedback)
# ✅ NO K8s or Robusta installation needed!
python scripts/test/test_robusta_flow.py --verbose

# Test without feedback collection (skip feedback steps)
python scripts/test/test_robusta_flow.py --no-feedback

# Or test with custom alert
python scripts/test/test_triage_and_resolution.py \
  --title "Database Connection Pool Exhausted" \
  --service "database" \
  --verbose

# Test Robusta flow with custom alert
python scripts/test/test_robusta_flow.py \
  --title "High CPU Usage" \
  --service "api-gateway" \
  --severity "critical"

# Simulate multiple alerts
python scripts/test/simulate_alerts.py --count 5

# View MTTR metrics
python scripts/db/mttr_metrics.py
```

### 8. Web UI (State-Based HITL)

The React frontend now mirrors the backend’s state-based agent flow in real time (no CopilotKit dependency).

```bash
cd ui
npm install
npm start           # for local dev; Docker Compose already runs `npm run build`
```

Open http://localhost:3000 and walk through the workflow:

1. **Full-width layout** – incidents on the left, selected incident details on the right (or stacked on smaller screens).
2. **Workflow hero card** – policy band badge, severity/confidence chips, pending-action indicator, and actionable buttons (manual review vs. auto resolution).
3. **Progress stepper + connection badge** – consumes `/api/v1/agents/{incident_id}/state` via WebSocket, showing live steps, pause/resume, and connection health.
4. **Tabbed detail view**
   - `Overview`: policy decision + alert metadata cards.
   - `Triage`: severity/category/confidence badges, summaries, actions.
   - `Resolution`: risk/time/approval metadata, ordered steps, commands, rollback.
   - `Evidence`: chunk counts plus provenance tags for triage & resolution.
   - `Timeline`: enhanced chronological state history with logs, milestones, and action events.
5. **Pending Action card** – when the agent pauses for HITL, the UI renders the corresponding review form inline (triage or resolution) with inline editing controls, diff view, and validation, then resumes the workflow after submission.
6. **Keyboard Shortcuts**: Use `Ctrl+K` to search, `Ctrl+N` for new triage, `Escape` to close, `Ctrl+R` to refresh.
7. **Optimistic Updates**: UI updates immediately for feedback and bulk actions, with automatic rollback on errors.
8. **Sound & Visual Alerts**: Browser tab notifications and audio alerts when pending actions require attention.
9. **Auto-Refresh**: Insight cards and incident list refresh automatically every 30 seconds.
10. **Theme Toggle**: Switch between light and dark themes using the toggle button in the top bar.
11. **Undo/Redo**: Full undo/redo support for form edits with `Ctrl+Z` (undo) and `Ctrl+Shift+Z` or `Ctrl+Y` (redo).

Everything is fed by the same WebSocket stream that the backend uses, so state changes, pauses, resumes, and completions appear immediately without polling.

## API Endpoints

### AI Service (Port 8001)

#### `GET /api/v1/health`
Basic health check endpoint (service status only).

**Response:**
```json
{
  "status": "healthy",
  "service": "ai",
  "version": "1.0.0"
}
```

#### `GET /api/v1/health/ready`
Readiness check endpoint with dependency verification. Checks database connectivity and LLM API availability.

**Response (healthy):**
```json
{
  "service": "ai",
  "version": "1.0.0",
  "status": "ready",
  "checks": {
    "database": {"status": "healthy"},
    "llm_api": {"status": "healthy"}
  }
}
```

**Response (unhealthy):**
- Status code: `503 Service Unavailable`
- Includes error details for failed checks

#### `GET /api/v1/health/live`
Liveness check endpoint (simple service running check).

**Response:**
```json
{
  "status": "alive",
  "service": "ai"
}
```

#### `GET /metrics`
Prometheus metrics endpoint. Returns metrics in Prometheus format.

**Response:** Prometheus text format with all metrics

#### `GET /docs`
Interactive API documentation (Swagger UI)

#### `GET /redoc`
Alternative API documentation (ReDoc)

**Note:** All API endpoints are versioned under `/api/v1/`.

### Ingestion Service (Port 8002)

#### `POST /ingest`
Generic document ingestion endpoint.

**Request:**
```json
{
  "doc_type": "runbook",
  "service": "api-gateway",
  "component": "api",
  "title": "Database Restart Procedure",
  "content": "Steps to restart database...",
  "tags": {"category": "operations"}
}
```

#### `POST /ingest/alert`
Ingest historical alert.

**Request:**
```json
{
  "alert_id": "alert-123",
  "source": "prometheus",
  "title": "High CPU Usage",
  "description": "CPU usage above 90%",
  "labels": {"service": "api-gateway", "component": "api"},
  "severity": "high",
  "resolution_status": "resolved",
  "resolution_notes": "Scaled up instances"
}
```

#### `POST /ingest/incident`
Ingest historical incident (supports structured or unstructured).

**Request (Structured):**
```json
{
  "title": "Database Connection Pool Exhausted",
  "description": "Application unable to connect",
  "severity": "critical",
  "category": "database",
  "resolution_steps": ["Restarted pool", "Increased size"],
  "root_cause": "Pool size too small"
}
```

**Request (Unstructured):**
```json
{
  "title": "Network Outage",
  "raw_content": "On 2024-01-15, we experienced a network outage..."
}
```

#### `POST /ingest/runbook`
Ingest runbook (markdown, plain text, or JSON).

**Request:**
```json
{
  "title": "Database Restart",
  "service": "database",
  "component": "postgres",
  "content": "## Steps\n1. Check connections\n2. Shutdown",
  "steps": ["Check connections", "Shutdown", "Restart"]
}
```

#### `POST /ingest/log`
Ingest log snippet.

**Request:**
```json
{
  "content": "2024-01-15 10:30:00 ERROR [api-gateway] Connection timeout",
  "level": "error",
  "service": "api-gateway",
  "component": "api"
}
```

#### `POST /ingest/batch`
Batch ingest multiple items.

**Request:**
```json
{
  "items": [
    {"title": "Incident 1", "content": "..."},
    {"title": "Incident 2", "content": "..."}
  ],
  "doc_type": "incident"
}
```

### AI Service (Port 8001)

#### `POST /api/v1/simulate-robusta-flow` ⭐ **Use POC via API without K8s!**

Simulate complete Robusta playbook flow without Kubernetes. This endpoint accepts Prometheus-style alert data and runs the full flow (triage → feedback → resolution → feedback).

**Request:**
```json
{
    "name": "High CPU Usage",
    "description": "CPU usage exceeded 90% for the last 15 minutes",
    "labels": {
        "service": "api-gateway",
        "component": "api",
        "severity": "critical"
    },
    "collect_feedback": true
}
```

**Response:**
```json
{
    "success": true,
    "incident_id": "uuid",
    "triage": {...},
    "resolution": {...},
    "feedback_triage": {...},
    "feedback_resolution": {...},
    "enrichments": [...]
}
```

**Example:**
```bash
curl -X POST http://localhost:8001/api/v1/simulate-robusta-flow \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High CPU Usage",
    "description": "CPU usage exceeded 90%",
    "labels": {
      "service": "api-gateway",
      "component": "api",
      "severity": "critical"
    }
  }'
```

#### `POST /api/v1/triage`
Triage an alert.

**Request:**
```json
{
  "alert_id": "alert-123",
  "source": "prometheus",
  "title": "High CPU Usage",
  "description": "CPU usage is above 90%",
  "labels": {"service": "api-gateway", "component": "compute"},
  "ts": "2024-01-15T10:00:00Z"
}
```

**Response:**
```json
{
  "incident_id": "uuid",
  "triage": {
    "summary": "...",
    "category": "application",
    "severity": "high",
    "confidence": 0.85,
    "likely_cause": "...",
    "affected_services": ["api-gateway"],
    "recommended_actions": ["..."]
  },
  "context_chunks_used": 5,
  "evidence_chunks": {
    "chunks_used": 5,
    "chunk_ids": ["uuid1", "uuid2"],
    "chunk_sources": ["Runbook: Database Restart", "..."],
    "retrieval_method": "hybrid_search",
    "retrieval_params": {...}
  }
}
```

### Workflow Configuration (config/workflow.json)

You can control the workflow without code changes:

```json
{
  "workflow": {
    "feedback_before_policy": true,
    "feedback_timeout_secs": 0,
    "resolution_requires_approval": false
  }
}
```

- feedback_before_policy: if true, policy is deferred until triage feedback is received (policy_band stored as "PENDING").
- feedback_timeout_secs: optional; if > 0, you can add a scheduler to auto-apply policy after timeout.
- resolution_requires_approval: if true, require approval even for AUTO band (future use; guardrails still enforced).

Behavioral changes:
- `POST /api/v1/triage`: when feedback_before_policy=true, stores policy_band="PENDING" and defers policy.
- `PUT /api/v1/incidents/{id}/feedback` (triage): computes and stores policy when triage feedback arrives.
- `POST /api/v1/resolution`: if policy is PENDING, computes policy first; always generates a resolution. For REVIEW, the resolution requires approval (not auto-applied).

#### `POST /api/v1/resolution`
Generate resolution for an incident.

**Request (with incident_id):**
```bash
POST /api/v1/resolution?incident_id=<uuid>
```
- Add `use_state=true` to switch to the asynchronous, HITL-aware workflow:
  - `POST /api/v1/resolution?incident_id=<uuid>&use_state=true`
  - Requires an existing incident (i.e., run triage first)
  - Streams live state over the `/agents/{incident_id}/state` WebSocket and pauses with a `review_resolution` action when approval is required

**Request (with alert - will triage first):**
```json
{
  "alert_id": "alert-123",
  "source": "prometheus",
  "title": "High CPU Usage",
  "description": "CPU usage is above 90%",
  "labels": {"service": "api-gateway"},
  "ts": "2024-01-15T10:00:00Z"
}
```

**Response:**
```json
{
  "incident_id": "uuid",
  "resolution": {
    "resolution_steps": ["Step 1", "Step 2"],
    "commands": ["command1", "command2"],
    "estimated_time_minutes": 30,
    "risk_level": "medium",
    "requires_approval": true
  },
  "policy": {
    "can_auto_apply": false,
    "requires_approval": true,
    "notification_required": true
  },
  "policy_band": "PROPOSE",
  "context_chunks_used": 5,
  "evidence_chunks": {...}
}
```

#### `GET /api/v1/incidents`
List incidents.

**Query Parameters:**
- `limit` (default: 50)
- `offset` (default: 0)

#### `GET /api/v1/incidents/{id}`
Get incident details.

#### `PUT /api/v1/incidents/{id}/feedback`
Submit human feedback/edits.

**Request:**
```json
{
  "feedback_type": "resolution",
  "user_edited": {
    "resolution_steps": ["Modified step 1", "Added step 2"],
    "commands": ["updated command"]
  },
  "notes": "Adjusted for our environment"
}
```

**Response:**
```json
{
  "feedback_id": "uuid",
  "incident_id": "uuid",
  "feedback_type": "resolution",
  "status": "feedback_stored",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

#### `POST /api/v1/calibrate`
Analyze feedback patterns and suggest configuration improvements.

**Query Parameters:**
- `start_date` (optional, ISO8601): Start date for feedback analysis (default: 7 days ago)
- `end_date` (optional, ISO8601): End date for feedback analysis (default: now)

**Response:**
```json
{
  "summary": {
    "total_feedback": 25,
    "triage_feedback": 12,
    "resolution_feedback": 13,
    "date_range": {
      "start": "2024-01-08T00:00:00Z",
      "end": "2024-01-15T00:00:00Z"
    }
  },
  "suggestions": {
    "retrieval": {
      "prefer_types": ["runbook", "incident"],
      "max_per_type": {"runbook": 3, "incident": 2}
    },
    "prompt_hints": [
      "Users frequently add rollback steps to resolution outputs",
      "Triage outputs often need more specific affected_services"
    ],
    "policy_notes": [
      "Consider lowering REVIEW threshold for database-related incidents"
    ]
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/api/v1/calibrate?start_date=2024-01-01&end_date=2024-01-15"
```

## Historical Data Ingestion

### Using the Script

```bash
# Ingest all JSONL files from data/faker_output (auto-detects type from filename)
python scripts/data/ingest_data.py --dir data/faker_output

# Ingest specific type with pattern
python scripts/data/ingest_data.py --dir data/faker_output --pattern "alert_*.jsonl" --type alert

# Ingest single file
python scripts/data/ingest_data.py --file data/alerts.jsonl --type alert
```

### Supported Formats

- **Structured JSON**: Full schema with all fields
- **Unstructured Text**: Free-form text (for incidents, use `raw_content` field)
- **Mixed**: Batch endpoint supports both in same request

## Configuration

### Configuration Files (`config/` directory)

Configuration is split into logical files for easier management. Edit these files to modify behavior **without code changes**:

- **`config/policy.json`** - Policy gate bands (AUTO/PROPOSE/REVIEW), conditions, actions
- **`config/guardrails.json`** - Validation rules, allowed values, limits, dangerous commands
- **`config/llm.json`** - LLM settings (model, temperature, system prompts per agent)
- **`config/retrieval.json`** - Hybrid search settings (limits, weights, filters, preferred document types)
- **`config/workflow.json`** - Workflow behavior (feedback timing, policy evaluation order)
- **`config/schemas.json`** - Data schema definitions (historical data inputs, alert metadata)

See `config/README.md` for detailed documentation.

### Prompt Templates (`ai_service/prompts.py`)

Edit `ai_service/prompts.py` to modify LLM prompts **without code changes**:
- **TRIAGE_USER_PROMPT_TEMPLATE**: User prompt for triage agent
- **TRIAGE_SYSTEM_PROMPT_DEFAULT**: Default system prompt for triage (can be overridden in `config/llm.json`)
- **RESOLUTION_USER_PROMPT_TEMPLATE**: User prompt for resolution agent
- **RESOLUTION_SYSTEM_PROMPT_DEFAULT**: Default system prompt for resolution (can be overridden in `config/llm.json`)

**Note**: System prompts can also be configured via `config/llm.json` under `triage.system_prompt` and `resolution.system_prompt`. The prompts file provides defaults and user prompt templates.

### Environment Variables

Create `.env` file or set environment variables:

```bash
# Required
OPENAI_API_KEY=your-key-here
DATABASE_URL=postgresql://user:pass@host:5432/db

# Optional - Logging
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
LOG_FILE=/app/logs/app.log  # Optional: exact log file path (overrides auto-generation)
LOG_DIR=/app/logs           # Optional: directory for log files (default: ./logs)
                            # If LOG_FILE not set, auto-generates: {service_name}_{YYYY-MM-DD}.log

# Optional - Service Configuration
AI_SERVICE_HOST=0.0.0.0
AI_SERVICE_PORT=8001
INGESTION_SERVICE_PORT=8002

# Optional - Database Resilience
DB_POOL_MIN=2                 # Minimum pooled connections (default: 2)
DB_POOL_MAX=10                # Maximum pooled connections (default: 10)
DB_CONN_RETRIES=3             # Attempts when acquiring a DB connection (default: 3)
DB_CONN_RETRY_BASE_DELAY=1.0  # Initial retry delay in seconds (default: 1.0)
DB_CONN_RETRY_MAX_DELAY=5.0   # Max retry delay in seconds (default: 5.0)
```

### Docker Environment

When using Docker Compose, set variables in `docker-compose.yml` or `.env` file:
```bash
# .env file
OPENAI_API_KEY=your-key-here
LOG_LEVEL=INFO
```

## Current Workflow (Working Now)

### End-to-End Flow

1. **Historical Data Ingestion** ✅
   - Generate data: `python scripts/data/generate_fake_data.py --all --count 20`
   - Ingest data: `python scripts/data/ingest_data.py --dir data/faker_output`
   - Or manually ingest via `/ingest/*` endpoints
   - Result: 80+ items in database (alerts, incidents, runbooks, logs)

2. **Alert Triage** ✅
   - Send alert via test script: `python scripts/test/test_triage_and_resolution.py`
   - Or simulate: `python scripts/test/simulate_alerts.py --count 5`
   - Or use interactive flow: `python scripts/test/test_robusta_flow.py --interactive`
   - AI Service retrieves relevant context from historical data (hybrid search)
   - LLM generates triage with evidence chunks + provenance stored
   - If `feedback_before_policy=true`: Policy band set to "PENDING" until feedback

3. **User Feedback (Triage)** ✅ [Configurable]
   - Interactive prompts or API: `PUT /api/v1/incidents/{id}/feedback`
   - User can: Accept, Edit, or Reject triage output
   - If edited, policy gate re-evaluates using user-edited triage
   - Stores feedback with diff for calibration

4. **Policy Gate Evaluation** ✅
   - Evaluates severity + risk level → Policy Band
   - AUTO: Low risk → Can auto-apply
   - PROPOSE: Medium risk → Requires approval but can be proposed
   - REVIEW: High risk → Requires manual review
   - Policy decision stored in incident record

5. **Resolution Generation** ✅
   - Request resolution: `POST /api/v1/resolution?incident_id={id}`
   - AI Service retrieves runbook-heavy context (configurable via `retrieval.resolution`)
   - LLM generates resolution steps + rationale + evidence
   - Policy gate sets `requires_approval` based on policy_band
   - Evidence chunks with provenance stored
   - **Always generates resolution** (even for REVIEW band, but requires approval)

6. **User Feedback (Resolution)** ✅ [Required for REVIEW, optional for others]
   - Interactive prompts or API: `PUT /api/v1/incidents/{id}/feedback`
   - User can: Approve, Edit, or Reject resolution steps
   - Stores feedback with diff for calibration
   - Marks resolution as accepted if approved

7. **Calibration** ✅ [Optional]
   - Analyze feedback patterns: `POST /api/v1/calibrate?start_date=...&end_date=...`
   - Returns suggestions for retrieval preferences, prompt hints, policy notes
   - Helps improve AI performance based on human corrections

8. **MTTR Metrics** ✅
   - Query: `python scripts/db/mttr_metrics.py`
   - Or query `incident_metrics` view directly

### Testing Without K8s

**Current Approach (No Robusta Required):**
- ✅ Mock alert generator (`scripts/test/simulate_alerts.py`)
- ✅ End-to-end test script (`scripts/test/test_triage_and_resolution.py`)
- ✅ LLM-based fake data generator (`scripts/data/generate_fake_data.py`)
- ✅ All services run locally (no K8s needed)

## What This POC Actually Is

**This is a standalone, custom AI-powered NOC system** that works independently.

### Current Reality

**What We Built:**
- ✅ **Standalone AI Service** - FastAPI endpoints (`/triage`, `/resolution`, `/simulate-robusta-flow`)
- ✅ **LLM + Hybrid Search** - OpenAI LLM with vector + full-text search (pgvector + tsvector)
- ✅ **AI Agents** - Triager and Resolution Copilot agents
- ✅ **Policy Gates** - AUTO/PROPOSE/REVIEW bands (configuration-driven)
- ✅ **Guardrails** - Input/output validation, dangerous command detection
- ✅ **Feedback System** - Human-in-the-loop feedback collection
- ✅ **Evidence Tracking** - Stores evidence chunks used by AI agents
- ✅ **Works Without K8s** - No Kubernetes or Robusta required

**What We're NOT Using (Robusta Features):**
1. ❌ **Real Prometheus Alert Integration** - Robusta listens to AlertManager in K8s cluster
2. ❌ **Automatic K8s Enrichment** - Pod logs, events, metrics automatically attached to alerts
3. ❌ **Playbook Orchestration** - Robusta's playbook system triggers actions in sequence
4. ❌ **Slack Integration** - Interactive buttons, notifications, real-time updates
5. ❌ **Self-Healing Actions** - Can execute K8s commands (restart pods, scale deployments)
6. ❌ **K8s Resource Access** - Can inspect and act on cluster resources

**Bottom Line:** This is a **custom POC** that can work standalone or integrate with Robusta (optional). The Robusta integration scripts exist but are not deployed - the system works perfectly without them.

### To Actually Use Robusta's Power

You would need to:
1. ✅ Deploy to K8s cluster
2. ✅ Install Robusta via Helm
3. ✅ Deploy our AI service to K8s
4. ✅ Create Robusta playbooks with our Custom Actions
5. ✅ Connect to real Prometheus AlertManager
6. ✅ Configure Slack integration (optional)

**Then you'd get:**
- Real Prometheus alerts from your cluster
- Automatic enrichment (pod logs, events, metrics)
- Robusta's playbook orchestration
- Slack notifications with interactive buttons
- Self-healing capabilities

### Current Status: Scripts Created, Not Deployed

**Status:** Scripts created and ready. **You can test 95% of the integration without K8s** using `test_robusta_flow.py` or `/simulate-robusta-flow` endpoint!

### Why Robusta Needs Kubernetes (Understanding the Architecture)

**Robusta is Kubernetes-native** - it's designed specifically for K8s environments. Here's why:

#### 1. **Prometheus Alert Integration**
- Robusta listens to **Prometheus AlertManager** running in your K8s cluster
- Prometheus monitors K8s resources (pods, services, nodes) and generates alerts
- Robusta needs to be **inside the cluster** to receive these alerts in real-time
- **Without K8s**: You can't get real Prometheus alerts from a K8s cluster

#### 2. **Kubernetes Resource Access**
- Robusta can **inspect K8s resources** (pods, logs, events, metrics) when alerts fire
- It can **execute actions** on K8s resources (restart pods, scale deployments, etc.)
- It uses **kubectl** and K8s API to interact with cluster resources
- **Without K8s**: No K8s resources to inspect or act upon

#### 3. **Alert Enrichment**
- Robusta automatically attaches **pod logs**, **events**, **metrics** to alerts
- It can query K8s API for context about the failing resource
- This enrichment happens **within the cluster** for low latency
- **Without K8s**: No automatic enrichment from K8s resources

#### 4. **Self-Healing Actions**
- Robusta can execute **remediation actions** (restart pods, rollback deployments)
- These actions require **direct K8s API access**
- Actions run as **K8s Jobs** or **CronJobs** within the cluster
- **Without K8s**: Can't execute remediation actions

#### 5. **Slack/Notification Integration**
- Robusta sends enriched alerts to **Slack** (or other channels)
- It uses **K8s ServiceAccounts** for authentication
- Runs as a **K8s Deployment** with proper RBAC permissions
- **Without K8s**: Can't deploy Robusta as a service

### What We Can Do WITHOUT K8s (Our Current Approach)

For **testing AI agents**, we don't actually need K8s because:

1. ✅ **AI Agent Logic**: Our agents just call HTTP APIs (`/triage`, `/resolution`)
   - These work the same whether called from Robusta or a test script
   - The AI service doesn't need K8s - it's just a FastAPI app

2. ✅ **Alert Simulation**: We can simulate Prometheus alerts
   - Test script creates mock alerts with same structure
   - Tests the exact same flow (triage → resolution → feedback)

3. ✅ **Custom Actions**: We simulate Robusta Custom Actions
   - Custom Actions are just Python functions that call our API
   - We can test the same logic without Robusta

4. ✅ **Feedback Collection**: We simulate Slack interactions
   - In production, Slack buttons trigger feedback API
   - We can test the same API calls directly

### When You DO Need K8s + Robusta

You need real Robusta deployment when you want:

1. **Real Prometheus Alerts** from your production K8s cluster
2. **Automatic Alert Enrichment** (pod logs, events, metrics)
3. **Slack Notifications** with interactive buttons
4. **Self-Healing Actions** (automatic remediation)
5. **Production Environment** testing

### Testing Without K8s (Recommended)

```bash
# Test complete Robusta flow WITHOUT K8s
python scripts/test/test_robusta_flow.py --verbose
```

This simulates:
- ✅ Prometheus alerts (same structure)
- ✅ Robusta Custom Actions (same logic)
- ✅ Agent execution flow (same API calls)
- ✅ Feedback collection (same endpoints)
- ✅ Database operations (same storage)

**No K8s or Robusta installation needed!**

### Deploying to Real Robusta (Optional - Requires K8s)

**When you need it**: Real Prometheus alerts, Slack notifications, production environment

**Prerequisites**:
- Kubernetes cluster (kind/minikube for local, cloud K8s for production)
- Prometheus installed in cluster
- Robusta installed via Helm
- Your AI service deployed to K8s

**Steps**:
1. Set up K8s cluster: `bash scripts/setup/setup_robusta.sh`
2. Deploy AI service: `kubectl apply -f scripts/robusta/deploy_ai_service_k8s.yaml`
3. Create playbook: `bash scripts/robusta/create_robusta_playbook.sh`
4. Add feedback actions: `bash scripts/robusta/create_robusta_feedback_actions.sh`
5. Test: `bash scripts/robusta/send_fake_prometheus_alerts.sh 5`

**Recommendation**: Use `test_robusta_flow.py` for testing/demo. Only deploy to real Robusta when you need production features.

**Note:** Robusta integration is optional. The system works perfectly standalone for POC/demo purposes.

## Database Schema

### Tables

- **documents**: Source documents (runbooks, SOPs, historical incidents)
- **chunks**: Chunked documents with embeddings and tsvector
- **incidents**: Alert triage and resolution data
  - `triage_evidence` (JSONB): Evidence chunks used by triager agent
  - `resolution_evidence` (JSONB): Evidence chunks used by resolution copilot agent
  - `policy_band` (TEXT): AUTO, PROPOSE, or REVIEW
  - `policy_decision` (JSONB): Full policy decision JSON
- **feedback**: Human-in-the-loop edits
  - `feedback_type` (TEXT): "triage" or "resolution"
- **incident_metrics**: View for MTTR calculations

## Architecture Details

### Architecture Layers

The system follows a **clean architecture** with clear separation of concerns:

1. **API Layer** - HTTP endpoints (`/api/v1/*`)
2. **Service Layer** - Business logic orchestration
3. **Repository Layer** - Data access abstraction
4. **Agent Layer** - AI agent implementations
5. **Core Layer** - Shared infrastructure (logging, metrics, config)

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

### Hybrid Search

- **Vector Search**: OpenAI embeddings with pgvector cosine similarity
- **Full-Text Search**: PostgreSQL tsvector with ts_rank
- **RRF**: Reciprocal Rank Fusion combining both results
- **MMR**: Maximal Marginal Relevance for diverse results

### Chunking and Embedding Strategy

The system uses a **two-level chunking approach** for optimal performance:

1. **Client-Side Chunking** (Transport Layer):
   - Large logs (>900KB) are automatically chunked by lines before upload
   - Handles FastAPI's 1MB request body limit
   - Preserves log structure (splits by lines, not arbitrary bytes)
   - Location: `scripts/data/generate_fake_data.py::_chunk_large_content_for_upload()`

2. **Server-Side Chunking** (RAG Layer):
   - Token-based chunking (120-360 tokens per chunk) using tiktoken
   - Optimized for embedding model limits (text-embedding-3-small: 8191 tokens max)
   - 30-token overlap between chunks for context preservation
   - Location: `ingestion/chunker.py::chunk_text()`

3. **Batch Embedding Generation**:
   - Processes up to 50 chunks per API call (instead of 1 at a time)
   - **10-100x faster** for large documents (e.g., 100 chunks = 2 API calls vs 100)
   - Reduces API rate limit issues and costs
   - Location: `ingestion/embeddings.py::embed_texts_batch()`

**Performance Example**:
- Before: 100 chunks = 100 API calls = ~100 seconds
- After: 100 chunks = 2 API calls (50 per batch) = ~2 seconds

### Triage Flow (Current Implementation)

1. **Alert Source**: Mock alert from test script (`scripts/test_triage_and_resolution.py`) or simulator (`scripts/simulate_alerts.py`)
2. **Context Retrieval**: Hybrid search from historical data (80+ ingested items)
   - Searches across alerts, incidents, runbooks, logs
   - Filters by service/component if available
   - Returns top 5 relevant chunks with scores
3. **LLM Analysis**: OpenAI GPT-4 analyzes alert + retrieved context
   - Generates structured triage JSON (severity, category, likely_cause, etc.)
4. **Evidence Storage**: Stores evidence chunks used in `triage_evidence` column
   - Includes chunk IDs, sources, retrieval method, scores
5. **Response**: Returns triage output + evidence_chunks for inspection

### Resolution Flow (Current Implementation)

1. **Incident Lookup**: Get existing incident by ID or create from alert
2. **Context Retrieval**: Hybrid search with preference for runbooks
   - Searches historical data for relevant resolution steps
   - Returns top 5 chunks with scores
3. **LLM Generation**: OpenAI GPT-4 generates resolution steps
   - Includes commands, rollback plan, time estimate, risk level
4. **Policy Gate**: Evaluates severity + risk level
   - Determines policy_band: AUTO (low risk), PROPOSE (medium), REVIEW (high)
5. **Evidence Storage**: Stores evidence chunks in `resolution_evidence` column
6. **Policy Storage**: Stores policy_band and full policy_decision JSON
7. **Response**: Returns resolution + policy_band + evidence_chunks

### Policy Gates

- **AUTO**: Low risk + low severity → Can auto-apply
- **PROPOSE**: Medium risk + low/medium severity → Requires approval but can be proposed
- **REVIEW**: High risk or critical severity → Requires manual review

## Troubleshooting

### Database Connection Issues

```bash
# Check Postgres is running
docker ps | grep noc-pg

# Check connection
psql -h localhost -U postgres -d nocdb
```

### Service Not Starting

```bash
# Check logs
tail -f /tmp/ai_service.log

# Check if port is in use
lsof -i :8001

# Kill existing processes
pkill -9 -f uvicorn
```

### Migration Issues

```bash
# Run migration manually
python scripts/run_migration.py

# Check database schema
psql -h localhost -U postgres -d nocdb -c "\d incidents"
```

## Development

### Project Structure

```
.
├── ai_service/              # AI service package
│   ├── api/                 # API routes (separated by version)
│   │   └── v1/              # API v1 endpoints
│   │       ├── health.py    # Health check
│   │       ├── triage.py    # Triage endpoints
│   │       ├── resolution.py # Resolution endpoints
│   │       ├── incidents.py # Incident management
│   │       ├── feedback.py  # Feedback endpoints
│   │       ├── calibration.py # Calibration endpoints
│   │       └── simulate.py   # Simulation endpoints
│   ├── agents/              # Agent implementations
│   │   ├── triager.py       # Triager agent
│   │   └── resolution_copilot.py # Resolution copilot agent
│   ├── core/                # Core utilities
│   │   ├── logger.py        # Logging configuration
│   │   ├── metrics.py       # Prometheus metrics
│   │   ├── config_loader.py # Configuration loading
│   │   └── exceptions.py    # Custom exceptions
│   ├── repositories/        # Data access layer (Repository pattern)
│   │   ├── incident_repository.py
│   │   └── feedback_repository.py
│   ├── services/            # Business logic layer
│   │   ├── incident_service.py
│   │   └── feedback_service.py
│   ├── models.py            # Pydantic models
│   ├── llm_client.py        # LLM client
│   ├── policy.py            # Policy gates
│   ├── guardrails.py        # Validation guardrails
│   ├── prompts.py          # LLM prompt templates
│   └── main.py              # FastAPI application (thin layer)
├── ingestion/               # Ingestion service (documents, historical data)
├── retrieval/               # Hybrid search implementation
├── db/                      # Database schema and connection
├── tests/                   # Unit tests (pytest)
├── scripts/                 # Utility scripts
├── config/                  # Configuration files (split by concern)
│   ├── policy.json         # Policy gate configuration
│   ├── guardrails.json     # Validation rules
│   ├── llm.json            # LLM settings
│   ├── retrieval.json      # Search settings
│   ├── workflow.json       # Workflow behavior
│   └── schemas.json        # Data schemas
├── requirements.txt         # Python dependencies
├── Dockerfile               # Docker image definition
├── docker-compose.yml       # Full stack deployment
├── Makefile                # Common development tasks
├── ARCHITECTURE.md         # Detailed architecture documentation
└── README.md               # This file
```

### Architecture Overview

The codebase follows a **clean architecture** with clear separation of concerns:

#### Layers

1. **API Layer** (`ai_service/api/v1/`)
   - HTTP endpoints, request/response handling
   - Input validation (Pydantic models)
   - Error handling and HTTP status codes
   - No business logic - delegates to services

2. **Service Layer** (`ai_service/services/`)
   - Business logic orchestration
   - Coordinates between agents, repositories, and policies
   - Enforces business rules
   - No direct database access - uses repositories

3. **Repository Layer** (`ai_service/repositories/`)
   - Data access abstraction
   - Database operations (CRUD)
   - Query building and data mapping
   - Easy to test and swap databases

4. **Agent Layer** (`ai_service/agents/`)
   - AI agent implementations
   - Context retrieval, LLM calls, validation
   - Evidence tracking

5. **Core Layer** (`ai_service/core/`)
   - Shared infrastructure (logging, metrics, config, exceptions)

#### Design Patterns

- **Repository Pattern**: Separates data access from business logic
- **Service Layer Pattern**: Separates business logic from API layer
- **API Versioning**: `/api/v1/` prefix allows evolution without breaking clients

#### Data Flow

```
POST /api/v1/triage
  → api/v1/triage.py (endpoint)
    → agents/triager.py (agent)
      → repositories/incident_repository.py (store)
        → database
```

For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

### Development Commands

Using Makefile (recommended):
```bash
make install          # Install dependencies
make test            # Run tests with coverage
make lint            # Run flake8 linter
make format          # Format code with black
make type-check      # Run mypy type checking
make all             # Run all checks (format, lint, type-check, test)
make docker-up       # Start Docker services
make docker-down     # Stop Docker services
make docker-logs     # View Docker logs
make clean           # Clean temporary files
```

Manual commands:
```bash
# Run tests
pytest tests/ -v --cov=ai_service --cov-report=html

# Format code
black ai_service/ ingestion/ retrieval/ tests/

# Lint code
flake8 ai_service/ --max-line-length=100

# Type check
mypy ai_service/ --ignore-missing-imports

# Test services
curl http://localhost:8001/api/v1/health          # Basic health check
curl http://localhost:8001/api/v1/health/ready   # Readiness check with dependencies
curl http://localhost:8001/api/v1/health/live     # Liveness check
curl http://localhost:8001/metrics                # Prometheus metrics
```

### Monitoring and Observability

**Prometheus Metrics:**
- Endpoint: `http://localhost:8001/metrics`
- Key metrics:
  - `http_requests_total` - HTTP request counts by method/endpoint/status
  - `http_request_duration_seconds` - Request latency
  - `triage_requests_total` - Triage operations
  - `resolution_requests_total` - Resolution operations
  - `llm_requests_total` - LLM API calls
  - `db_queries_total` - Database operations

**Logging:**
- Format: `TIMESTAMP | LEVEL | MODULE:FUNCTION:LINE | MESSAGE`
- Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Output: Console (stdout) + Daily log files
- **Daily Log Files**: Automatically creates `logs/{service_name}_{YYYY-MM-DD}.log`
  - Rotates at midnight daily
  - Keeps 30 days of logs
  - Separate files for `ai_service` and `ingestion` services
- Configure via `LOG_LEVEL`, `LOG_FILE` (optional), and `LOG_DIR` (optional) environment variables
- Example log files:
  - `logs/ai_service_2025-11-12.log`
  - `logs/ingestion_2025-11-12.log`

**API Documentation:**
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
