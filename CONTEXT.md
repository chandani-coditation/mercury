# NOC Agent AI - Technical Context

**Source of Truth for Codebase Development and Maintenance**

This document contains all technical details, architecture, configuration, and implementation details needed to understand, develop, and maintain the codebase.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Structure](#code-structure)
3. [Configuration System](#configuration-system)
4. [Data Flow](#data-flow)
5. [Guardrails and Limitations](#guardrails-and-limitations)
6. [Database Schema](#database-schema)
7. [Error Handling](#error-handling)
8. [Key Implementation Details](#key-implementation-details)
9. [Deployment and Infrastructure](#deployment-and-infrastructure)

---

## Architecture Overview

### System Components

```
┌─────────────────┐
│   API Layer     │  FastAPI endpoints (/api/v1/*)
├─────────────────┤
│  Service Layer  │  Business logic orchestration
├─────────────────┤
│  Agent Layer    │  AI agents (triage, resolution)
├─────────────────┤
│ Repository Layer│  Data access abstraction
├─────────────────┤
│   Core Layer    │  Logging, metrics, config, exceptions
└─────────────────┘
```

### Architecture Layers

#### 1. API Layer (`ai_service/api/v1/`)
- **Purpose**: HTTP endpoints, request/response handling
- **Responsibilities**:
  - Route requests to services or agents
  - Validate input (Pydantic models)
  - Handle HTTP exceptions
  - Return JSON responses
- **No business logic** - delegates to services or agents
- **Files**: `health.py`, `triage.py`, `resolution.py`, `incidents.py`, `feedback.py`, `calibration.py`, `simulate.py`

#### 2. Service Layer (`ai_service/services/`)
- **Purpose**: Business logic orchestration
- **Responsibilities**:
  - Coordinate between agents, repositories, and policies
  - Enforce business rules
  - Handle transactions
  - Provide reusable business logic
- **No direct database access** - uses repositories
- **Files**: `incident_service.py`, `feedback_service.py`

#### 3. Repository Layer (`ai_service/repositories/`)
- **Purpose**: Data access abstraction
- **Responsibilities**:
  - Database operations (CRUD)
  - Query building
  - Data mapping
  - Transaction management
- **Benefits**:
  - Easy to test (can mock repositories)
  - Easy to swap databases
  - Centralized data access
  - Type-safe operations
- **Files**: `incident_repository.py`, `feedback_repository.py`
- **Note**: Uses `dict_row` factory - `fetchone()` returns dictionaries, not tuples

#### 4. Agent Layer (`ai_service/agents/`)
- **Purpose**: AI agent implementations
- **Responsibilities**:
  - Context retrieval (hybrid search)
  - LLM calls (via `llm_client.py`)
  - Output validation (via `guardrails.py`)
  - Evidence tracking
  - Policy evaluation (via `policy.py`)
- **Uses**: Repositories, LLM client, guardrails, policy, retrieval
- **Files**: `triager.py`, `resolution_copilot.py`

#### 5. Core Layer (`ai_service/core/`)
- **Purpose**: Shared infrastructure
- **Components**:
  - **Logging** (`logger.py`): Structured logging with configurable levels, daily log rotation
  - **Metrics** (`metrics.py`): Prometheus metrics instrumentation
  - **Configuration** (`config_loader.py`): Dynamic config loading and caching
  - **Exceptions** (`exceptions.py`): Custom exception hierarchy
- **Benefits**: Centralized, reusable, consistent across the application

---

## Code Structure

### Folder Structure

```
noc_agent_ai/
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
│   ├── prompts.py           # LLM prompt templates
│   └── main.py              # FastAPI application (thin layer)
├── ingestion/               # Ingestion service
├── retrieval/               # Hybrid search
├── db/                      # Database schema and migrations
├── config/                  # Configuration files (split by concern)
│   ├── policy.json
│   ├── guardrails.json
│   ├── llm.json
│   ├── retrieval.json
│   ├── workflow.json
│   └── schemas.json
├── ui/                      # React frontend
│   ├── src/                 # React source code
│   │   ├── components/      # React components
│   │   │   ├── IncidentList.js
│   │   │   ├── IncidentDetail.js
│   │   │   └── TriageForm.js
│   │   ├── App.js           # Main app component
│   │   └── index.js         # Entry point
│   ├── public/              # Static files
│   ├── Dockerfile           # Multi-stage Docker build
│   ├── nginx.conf           # Nginx configuration
│   └── package.json         # Node.js dependencies
├── tests/                   # Unit tests
├── scripts/                 # Utility scripts
├── Dockerfile               # Backend Docker image
├── docker-compose.yml       # Full stack deployment
└── README.md
```

### Design Patterns

#### Repository Pattern
- **Why**: Separates data access from business logic
- **Implementation**: `IncidentRepository`, `FeedbackRepository`
- **Benefits**: 
  - Testable (easy to mock)
  - Maintainable (centralized queries)
  - Swappable (can change database without affecting business logic)
  - Type-safe operations

#### Service Layer Pattern
- **Why**: Separates business logic from API layer
- **Implementation**: `IncidentService`, `FeedbackService`
- **Benefits**: 
  - Reusable (can be used by multiple API endpoints)
  - Testable (can test business logic independently)
  - Clear separation of concerns

#### API Versioning
- **Why**: Allows breaking changes without breaking clients
- **Implementation**: `/api/v1/` prefix
- **Future**: Can add `/api/v2/` when needed

#### Dependency Injection
- **Why**: Makes code testable and flexible
- **Implementation**: Services accept repository instances (optional, defaults provided)
- **Benefits**: Easy to mock for testing

---

## Configuration System

### Configuration Files

All configuration is in `config/` directory, split by concern:

| Config File | Purpose | Used In |
|------------|---------|---------|
| `config/policy.json` | Policy gate bands (AUTO/PROPOSE/REVIEW), conditions, actions | `ai_service/policy.py`, `ai_service/agents/resolution_copilot.py`, `ai_service/api/v1/feedback.py` |
| `config/guardrails.json` | Validation rules, allowed values, limits, dangerous commands | `ai_service/guardrails.py` |
| `config/llm.json` | LLM settings (model, temperature, system prompts) | `ai_service/llm_client.py` |
| `config/retrieval.json` | Hybrid search settings (limits, weights, filters, preferred types) | `ai_service/agents/triager.py`, `ai_service/agents/resolution_copilot.py` |
| `config/workflow.json` | Workflow behavior (feedback timing, policy evaluation) | `ai_service/agents/triager.py`, `ai_service/agents/resolution_copilot.py`, `ai_service/api/v1/feedback.py` |
| `config/schemas.json` | Data schema definitions (historical data inputs, alert metadata) | `scripts/data/generate_fake_data.py` |

### Configuration Access

All configuration is accessed via helper functions in `ai_service/core/config_loader.py`:

```python
from ai_service.core import (
    get_policy_config,
    get_guardrail_config,
    get_llm_config,
    get_retrieval_config,
    get_workflow_config
)
```

These functions:
1. Load and cache configuration
2. Return the relevant section
3. Provide defaults if config is missing
4. Log configuration loading for observability

### Configuration Loading Mechanism

- **`core/config_loader.py`** loads and merges all config files
- **Cached** for performance (loaded once, reused)
- **Can be reloaded** at runtime (via `reload_config()`)
- **Type-safe access** via helper functions

### Key Configuration Details

#### Policy Configuration (`config/policy.json`)
- Defines policy bands: AUTO, PROPOSE, REVIEW
- Each band has:
  - `can_auto_apply`: Boolean - whether resolution can proceed automatically
  - `requires_approval`: Boolean - whether user approval is needed
  - `notification_required`: Boolean - whether to notify stakeholders
  - `rollback_required`: Boolean - whether rollback plan is mandatory
- Conditions evaluated in `evaluation_order`
- **Important**: Code uses `can_auto_apply` and `requires_approval` flags, NOT hardcoded band names

#### Guardrails Configuration (`config/guardrails.json`)
- **Triage limits**:
  - `max_summary_length`: 500 characters
  - `max_likely_cause_length`: 300 characters
  - `max_affected_services`: 50 items (increased from 10)
  - `max_recommended_actions`: 50 items (increased from 10)
- **Resolution limits**:
  - `min_resolution_steps`: 1
  - `max_resolution_steps`: 20
  - `min_estimated_time_minutes`: 1
  - `max_estimated_time_minutes`: 1440 (24 hours)
  - `max_commands`: 10
  - `max_rollback_steps`: 10
- **Safety checks**:
  - `dangerous_commands`: List of blocked commands
  - `destructive_patterns`: Regex patterns for dangerous operations
  - `require_rollback_for_risk_levels`: Risk levels requiring rollback

#### Retrieval Configuration (`config/retrieval.json`)
- **Triage section**:
  - `limit`: Number of chunks to retrieve (default: 5)
  - `vector_weight`: Weight for vector similarity (default: 0.7)
  - `fulltext_weight`: Weight for full-text search (default: 0.3)
  - `prefer_types`: Preferred document types
  - `max_per_type`: Maximum chunks per type
- **Resolution section**: Same structure, optimized for runbook retrieval

#### Workflow Configuration (`config/workflow.json`)
- `feedback_before_policy`: If true, policy is deferred until triage feedback is received
- `feedback_timeout_secs`: Optional timeout for feedback (0 = no timeout)
- `resolution_requires_approval`: If true, require approval even for AUTO band

---

## Data Flow

### Triage Flow

```
POST /api/v1/triage
  → api/v1/triage.py (endpoint)
    → agents/triager.py (agent)
      ├── retrieval/hybrid_search.py (context retrieval)
      ├── llm_client.py (LLM call)
      ├── guardrails.py (validation)
      ├── policy.py (policy evaluation)
      └── repositories/incident_repository.py (store)
        → database
```

**Key Steps**:
1. Retrieve context using hybrid search (vector + full-text)
2. Call LLM for triage analysis
3. Validate output against guardrails
4. Evaluate policy (or defer if `feedback_before_policy=true`)
5. Store incident with triage_output, triage_evidence, policy_band, policy_decision

### Resolution Flow

```
POST /api/v1/resolution?incident_id={id}
  → api/v1/resolution.py (endpoint)
    → agents/resolution_copilot.py (agent)
      ├── repositories/incident_repository.py (get incident)
      ├── Check policy: can_auto_apply and requires_approval
      ├── If approval needed: Raise ApprovalRequiredError (403)
      ├── retrieval/hybrid_search.py (context retrieval - runbook-heavy)
      ├── llm_client.py (LLM call)
      ├── guardrails.py (validation)
      └── repositories/incident_repository.py (update)
        → database
```

**Key Steps**:
1. Fetch incident from database (fresh fetch to get updated policy)
2. Check policy: Read `stored_policy_decision` from database
3. If `not can_auto_apply or requires_approval`: Raise `ApprovalRequiredError` (403)
4. Retrieve context (prefer runbooks)
5. Call LLM for resolution generation
6. Validate output against guardrails
7. Store resolution with resolution_output, resolution_evidence

**Important**: Resolution agent fetches fresh incident data to get updated `policy_band` and `triage_output` (in case user edited via feedback).

### Feedback Flow

```
PUT /api/v1/incidents/{id}/feedback
  → api/v1/feedback.py (endpoint)
    → services/feedback_service.py (service)
      ├── repositories/feedback_repository.py (store feedback)
      ├── If user_edited provided: Update incident.triage_output
      ├── If policy_band provided: Update policy
      │   ├── Recompute policy_decision with new band
      │   ├── Set can_auto_apply and requires_approval based on band
      │   └── repositories/incident_repository.py (update policy)
      └── Verify update by fetching incident again
```

**Key Steps**:
1. Store feedback in feedback table
2. If `user_edited` provided: Update `incident.triage_output` with user edits
3. If `policy_band` provided: 
   - Recompute policy_decision with new band
   - Update `incident.policy_band` and `incident.policy_decision`
   - Verify update succeeded
4. Return feedback confirmation

**Important**: 
- User can edit `triage_output` (same structure, no new fields)
- User can override `policy_band` (AUTO, PROPOSE, REVIEW)
- Updated `triage_output` is used by resolution agent on next call

### Approval Workflow

**Current Flow (Corrected)**:

1. **Triage** → Creates incident with policy_band (AUTO/PROPOSE/REVIEW) based on severity/confidence
2. **Policy Evaluation**:
   - **AUTO** (`can_auto_apply=True, requires_approval=False`): 
     - ✅ Resolution can be generated immediately
     - ✅ "Generate Resolution" button is enabled
     - ❌ NO feedback required
   - **PROPOSE/REVIEW** (`can_auto_apply=False, requires_approval=True`):
     - ❌ Resolution blocked until approval
     - ✅ "Generate Resolution" button is disabled
     - ✅ Feedback form shown for user review/edits
3. **User Approval** (only for PROPOSE/REVIEW):
   - User reviews/edits triage output via feedback form
   - User clicks "Approve & Generate Resolution"
   - Feedback endpoint with `policy_band="AUTO"` → Updates DB:
     - Sets `policy_band="AUTO"`
     - Sets `policy_decision.can_auto_apply=True`
     - Sets `policy_decision.requires_approval=False`
     - Updates `triage_output` if user made edits
4. **Resolution Generation**:
   - For AUTO: Directly enabled, user clicks "Generate Resolution"
   - For PROPOSE/REVIEW: Enabled after approval, auto-triggers or user clicks

**Key Rules**:
- ❌ **AUTO policy should NEVER require feedback** - if `can_auto_apply=True`, proceed directly
- ✅ **"Generate Resolution" button enabled when**:
  - Policy is AUTO (`can_auto_apply=True, requires_approval=False`), OR
  - Feedback has been provided (policy updated to AUTO via approval)
- ❌ **"Generate Resolution" button disabled when**:
  - Policy is PROPOSE/REVIEW and no feedback provided yet
  - Warning present (no matching evidence)
- ✅ **UI should NOT auto-trigger resolution** - user must click button explicitly

---

## Guardrails and Limitations

### Purpose
Guardrails ensure:
- **Quality**: Consistent, actionable outputs
- **Consistency**: Standardized format across all incidents
- **Database constraints**: Reasonable field sizes
- **UI/Display**: Fits in user interfaces
- **Safety**: Prevents dangerous commands in resolutions

### Triage Output Limits

| Field | Limit | Purpose |
|-------|-------|---------|
| `summary` | Max 500 characters | Brief, scannable summary |
| `likely_cause` | Max 300 characters | Concise root cause explanation |
| `affected_services` | Max 10 items | Focused list of impacted services |
| `recommended_actions` | Max 10 items | Actionable, prioritized list |
| `severity` | Must be: `low`, `medium`, `high`, `critical` | Standardized severity levels |
| `category` | Must be: `database`, `network`, `application`, `infrastructure`, `security`, `other` | Standardized categories |
| `confidence` | Range: 0.0 to 1.0 | Confidence score validation |

**Required Fields**: `severity`, `category`, `confidence`, `summary`, `likely_cause`, `affected_services`, `recommended_actions`

### Resolution Output Limits

| Field | Limit | Purpose |
|-------|-------|---------|
| `resolution_steps` | Min 1, Max 20 steps | Reasonable number of steps |
| `estimated_time_minutes` | Min 1, Max 1440 (24 hours) | Realistic time estimates |
| `commands` | Max 10 commands | Focused command list |
| `rollback_steps` | Max 10 steps | Reasonable rollback plan |
| `risk_level` | Must be: `low`, `medium`, `high` | Standardized risk levels |

**Safety Checks**:
- **Dangerous Commands Blocked**: `rm -rf`, `dd if=`, `mkfs`, `fdisk`, `format`, `drop database`, `truncate table`, `delete from`, `kill -9`
- **Destructive Patterns Detected**: Drop/delete/truncate/format/rm/remove, Kill/terminate/shutdown, Clear/purge/wipe
- **Rollback Required**: For `risk_level: "high"` or `"critical"`

**Required Fields**: `resolution_steps`, `estimated_time_minutes`, `risk_level`, `requires_approval`

### LLM Prompt Constraints

The LLM prompts (`ai_service/prompts.py`) include character limits to guide the model:
- `summary`: Maximum 500 characters
- `likely_cause`: Maximum 300 characters
- `affected_services`: Maximum 10 items
- `recommended_actions`: Maximum 10 items

**Note**: Limits are configurable in `config/guardrails.json`. If LLM consistently exceeds limits, either:
1. Update the prompt to be more explicit
2. Increase limits in `config/guardrails.json`

---

## Database Schema

### Tables

#### `documents`
- Source documents (runbooks, SOPs, historical incidents)
- Fields: `id`, `doc_type`, `title`, `content`, `metadata`, `created_at`

#### `chunks`
- Chunked documents with embeddings and tsvector
- Fields: `id`, `document_id`, `chunk_index`, `content`, `embedding`, `fulltext_vector`, `metadata`

#### `incidents`
- Alert triage and resolution data
- Fields:
  - `id`: UUID primary key
  - `alert_id`: Original alert ID
  - `raw_alert`: JSONB - Original alert data
  - `triage_output`: JSONB - Triage analysis result
  - `triage_evidence`: JSONB - Evidence chunks used by triager agent
  - `resolution_output`: JSONB - Resolution steps
  - `resolution_evidence`: JSONB - Evidence chunks used by resolution copilot agent
  - `policy_band`: TEXT - AUTO, PROPOSE, or REVIEW (or PENDING if deferred)
  - `policy_decision`: JSONB - Full policy decision JSON with `can_auto_apply`, `requires_approval`, etc.
  - `alert_received_at`: Timestamp
  - `triage_completed_at`: Timestamp
  - `resolution_proposed_at`: Timestamp
  - `resolution_accepted_at`: Timestamp

#### `feedback`
- Human-in-the-loop edits
- Fields:
  - `id`: UUID primary key
  - `incident_id`: Foreign key to incidents
  - `feedback_type`: TEXT - "triage" or "resolution"
  - `system_output`: JSONB - Original system output
  - `user_edited`: JSONB - User-edited version
  - `notes`: TEXT - User notes
  - `created_at`: Timestamp

#### `incident_metrics`
- View for MTTR calculations
- Computed fields: `triage_secs`, `resolution_proposed_secs`, `mttr_secs`

### Database Connection

- **Connection Pooling**: `db/connection.py` implements connection pooling using `psycopg_pool`
  - Pool initialized on service startup via `init_db_pool(min_size=2, max_size=10)`
  - Configurable via environment variables: `DB_POOL_MIN` (default: 2), `DB_POOL_MAX` (default: 10)
  - Connections are automatically returned to pool when using `get_db_connection_context()` context manager
  - Falls back to direct connections if pool not initialized (backward compatible)
- **Connection Retries**:
  - `get_db_connection()` retries transient `psycopg.OperationalError` failures using exponential backoff
  - Controlled via env vars: `DB_CONN_RETRIES` (default: 3), `DB_CONN_RETRY_BASE_DELAY` (default: 1s), `DB_CONN_RETRY_MAX_DELAY` (default: 5s)
  - Each attempt is logged with the attempt number and next backoff to simplify debugging
- **Connection Factory**: `db/connection.py::get_db_connection()` - Gets connection from pool
- **Context Manager**: `get_db_connection_context()` - Recommended for new code (auto-returns connection)
- **Row Factory**: `dict_row` (returns dictionaries, not tuples)
- **Important**: Always use `.get()` or dictionary access when reading query results

---

## Error Handling and Resilience

### Retry Logic

**LLM API Calls** (`ai_service/llm_client.py`):
- Automatic retry with exponential backoff for transient failures
- Retries on: `RateLimitError`, `APIConnectionError`, `APITimeoutError`, and 5xx server errors
- Configuration:
  - `MAX_RETRIES`: 3 attempts
  - `INITIAL_RETRY_DELAY`: 1.0 second
  - `MAX_RETRY_DELAY`: 60.0 seconds
  - `RETRY_EXPONENTIAL_BASE`: 2.0 (exponential backoff)
  - Jitter: Up to 10% random delay added to prevent thundering herd
- Metrics: Tracks retry attempts and distinguishes rate_limit errors from other errors

**Database Operations**:
- Connection pooling provides automatic connection recovery
- Connection acquisition now includes exponential backoff retry logic (see **Database Connection** section for configuration)
- `get_db_connection_context()` detects unhealthy cursors/connections and closes them instead of returning corrupted handles to the pool

### Custom Exceptions Hierarchy

```
NOCAgentError (base)
├── ConfigurationError
├── DatabaseError
├── RetrievalError
├── LLMError
├── PolicyError
├── ValidationError
│   ├── TriageValidationError
│   └── ResolutionValidationError
├── IncidentNotFoundError
└── ApprovalRequiredError
```

### Error Flow

1. **Repository** throws `DatabaseError` or `IncidentNotFoundError`
2. **Service** catches and re-raises (or handles business logic)
3. **API endpoint** catches and converts to `HTTPException`
4. Returns appropriate HTTP status code:
   - `400`: Bad Request (validation errors)
   - `403`: Forbidden (approval required)
   - `404`: Not Found (incident not found)
   - `422`: Unprocessable Entity (data preconditions not met - e.g., no historical data)
   - `500`: Internal Server Error

### User-Facing Error Guidance
- `ai_service/api/error_utils.py::format_user_friendly_error()` inspects exceptions and appends actionable hints.
- Triage and resolution endpoints use these hints when returning `500` errors so operators immediately know whether to:
  - Set `OPENAI_API_KEY`
  - Wait and retry after an upstream rate limit
  - Ingest historical data for better retrieval
  - Check PostgreSQL availability and credentials

### Error Response Format

```json
{
  "detail": "Error message"
}
```

For approval errors:
```json
{
  "detail": {
    "error": "approval_required",
    "message": "User approval required before generating resolution. Policy band: PROPOSE (from configuration), can_auto_apply: False, requires_approval: True. Please review the triage results for incident {incident_id} and approve before requesting resolution.",
    "incident_id": "uuid"
  }
}
```

---

## Key Implementation Details

### Early Stopping for Missing Data

**Triage Agent** (`ai_service/agents/triager.py`):
- If `len(context_chunks) == 0`:
  - Check if database is empty (`doc_count == 0`)
  - If empty: Raise `ValueError("No historical data found...")`
  - If not empty but no matches: Raise `ValueError("No matching evidence found...")`
- Prevents proceeding without evidence

**Resolution Agent** (`ai_service/agents/resolution_copilot.py`):
- Same logic when performing triage first (no incident_id)
- Ensures resolution doesn't proceed without evidence

### Policy Update Flow

**Feedback Endpoint** (`ai_service/api/v1/feedback.py`):
1. Store feedback in feedback table
2. If `user_edited` provided: Update `incident.triage_output` via `incident_service.update_triage_output()`
3. If `policy_band` provided:
   - Recompute `policy_decision` with new band (using user_edited triage_output if provided)
   - Set `can_auto_apply` and `requires_approval` based on band
   - Update database via `incident_service.update_policy()`
   - Verify update by fetching incident again

**Resolution Agent** (`ai_service/agents/resolution_copilot.py`):
1. Fetch fresh incident from database (line 189)
2. Update `existing_policy_band` from fresh fetch (line 191)
3. Update `triage_output` from fresh fetch (line 193) - may have been edited by user
4. Read `stored_policy_decision` from database
5. Use `can_auto_apply` and `requires_approval` from stored decision
6. If approval needed: Raise `ApprovalRequiredError`

### Database Update Verification

**Repository** (`ai_service/repositories/incident_repository.py`):
- `update_policy()` method:
  1. Gets current policy values for logging
  2. Updates database
  3. Commits transaction
  4. Verifies update by fetching again
  5. Logs before/after values for debugging
- `update_triage_output()` method:
  1. Checks if incident exists
  2. Updates `triage_output` column with user-edited version
  3. Commits transaction
  4. Logs update

**Important**: Uses dictionary access (`current.get("policy_band")`) because cursor uses `dict_row` factory. All `fetchone()` results are dictionaries, not tuples.

### Hybrid Search

**Implementation**: `retrieval/hybrid_search.py`
- **Vector Search**: OpenAI embeddings with pgvector cosine similarity
- **Full-Text Search**: PostgreSQL tsvector with ts_rank
- **RRF**: Reciprocal Rank Fusion combining both results
- **MMR**: Maximal Marginal Relevance for diverse results
- **Configuration**: Limits and weights from `config/retrieval.json`

### Chunking Strategy

**Two-Level Chunking**:

1. **Client-Side Chunking** (Transport Layer):
   - Large logs (>900KB) are automatically chunked by lines before upload
   - Handles FastAPI's 1MB request body limit
   - Location: `scripts/data/generate_fake_data.py::_chunk_large_content_for_upload()`

2. **Server-Side Chunking** (RAG Layer):
   - Token-based chunking (120-360 tokens per chunk) using tiktoken
   - Optimized for embedding model limits (text-embedding-3-small: 8191 tokens max)
   - 30-token overlap between chunks for context preservation
   - Location: `ingestion/chunker.py::chunk_text()`

3. **Batch Embedding Generation**:
   - Processes up to 50 chunks per API call (instead of 1 at a time)
   - **10-100x faster** for large documents
   - Location: `ingestion/embeddings.py::embed_texts_batch()`

### Logging

- **Format**: `TIMESTAMP | LEVEL | MODULE:FUNCTION:LINE | MESSAGE`
- **Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Output**: Console (stdout) + Daily log files
- **Daily Log Files**: Automatically creates `logs/{service_name}_{YYYY-MM-DD}.log`
  - Rotates at midnight daily
  - Keeps 30 days of logs
  - Separate files for `ai_service` and `ingestion` services
- **Configuration**: `LOG_LEVEL`, `LOG_FILE` (optional), `LOG_DIR` (optional) environment variables

### Metrics

**Prometheus Metrics** (endpoint: `/metrics`):
- `http_requests_total` - HTTP request counts by method/endpoint/status
- `http_request_duration_seconds` - Request latency
- `triage_requests_total` - Triage operations
- `resolution_requests_total` - Resolution operations
- `llm_requests_total` - LLM API calls
- `retrieval_requests_total` - Hybrid search operations
- `policy_decisions_total` - Policy band decisions

### Testing

**Test Scripts**:
- `scripts/test/test_triage_and_resolution.py` - End-to-end triage and resolution flow
- `scripts/test/test_robusta_flow.py` - Simulates Robusta playbook flow without K8s
- `scripts/test/simulate_alerts.py` - Simulates multiple alerts

**Unit Tests**: `tests/` directory with pytest

---

## Common Issues and Solutions

### Issue: Policy Update Not Working

**Symptoms**: Policy band remains old value after feedback update

**Causes**:
1. Database cursor returns dictionaries, not tuples - use `.get()` not `[0]`
2. Docker container running old code - rebuild with `docker-compose build --no-cache`
3. Exception silently caught - check logs for errors

**Solution**: 
- Use dictionary access: `current.get("policy_band")` not `current[0]`
- Rebuild Docker: `docker-compose build ai-service && docker-compose up -d ai-service`
- Check logs: `docker logs noc-ai-service --tail 100 | grep -E "(Policy|update)"`

### Issue: LLM Exceeds Character Limits

**Symptoms**: Validation error "Likely cause too long: 331 chars (max: 300)"

**Causes**:
1. LLM prompt doesn't mention limits
2. Limits too restrictive

**Solution**:
- Update prompt in `ai_service/prompts.py` to include limits
- Increase limits in `config/guardrails.json` if needed

### Issue: Resolution Still Requires Approval After Feedback

**Symptoms**: Resolution returns 403 even after feedback with `policy_band="AUTO"`

**Causes**:
1. Resolution agent not fetching fresh incident data
2. Policy update failing silently
3. Database update not committed

**Solution**:
- Ensure resolution agent fetches fresh incident (line 189 in `resolution_copilot.py`)
- Check logs for policy update errors
- Verify database update succeeded (check logs for verification messages)

---

## Development Guidelines

### Adding New Features

1. **API Endpoint**: Add to `ai_service/api/v1/`
2. **Business Logic**: Add to `ai_service/services/` or `ai_service/agents/`
3. **Data Access**: Add to `ai_service/repositories/`
4. **Configuration**: Add to appropriate `config/*.json` file
5. **Tests**: Add to `tests/` or `scripts/test/`

### Modifying Configuration

1. Edit appropriate `config/*.json` file
2. No code changes needed (configuration is loaded dynamically)
3. Restart service to reload (or use `reload_config()` if implemented)

### Database Changes

1. Create migration in `db/migrations/`
2. Run migration: `python scripts/db/run_migration.py`
3. Update repository methods if schema changes

### Adding New Guardrails

1. Add rules to `config/guardrails.json`
2. Update `ai_service/guardrails.py` to use new rules
3. Update prompts if needed to guide LLM

---

## Key Files Reference

### Core Files
- `ai_service/core/config_loader.py` - Configuration loading
- `ai_service/core/exceptions.py` - Custom exceptions
- `ai_service/core/logger.py` - Logging setup
- `ai_service/core/metrics.py` - Prometheus metrics

### Agent Files
- `ai_service/agents/triager.py` - Triage agent implementation
- `ai_service/agents/resolution_copilot.py` - Resolution agent implementation

### Repository Files
- `ai_service/repositories/incident_repository.py` - Incident data access
- `ai_service/repositories/feedback_repository.py` - Feedback data access

### Service Files
- `ai_service/services/incident_service.py` - Incident business logic
  - `get_incident()` - Get incident by ID
  - `create_incident()` - Create new incident
  - `update_policy()` - Update policy_band and policy_decision
  - `update_triage_output()` - Update triage_output with user edits
  - `update_resolution()` - Update resolution_output
- `ai_service/services/feedback_service.py` - Feedback business logic

### Configuration Files
- `config/policy.json` - Policy gate configuration
- `config/guardrails.json` - Validation rules
- `config/llm.json` - LLM settings
- `config/retrieval.json` - Search settings
- `config/workflow.json` - Workflow behavior
- `config/schemas.json` - Data schemas

### Prompt Files
- `ai_service/prompts.py` - LLM prompt templates

---

## Workflow Improvements (2025-11-13)

### Issues Identified

1. **AUTO Policy Feedback Requirement**: UI was showing feedback form even for AUTO policy, which is incorrect. AUTO means no feedback needed.

2. **Auto-Triggering Resolution**: UI was automatically triggering resolution generation when AUTO policy detected, instead of just enabling the button.

3. **Button Enable Logic**: "Generate Resolution" button should only be enabled when:
   - Policy is AUTO (can_auto_apply=True), OR
   - Feedback has been provided (policy updated to AUTO)
   - NOT when PROPOSE/REVIEW without feedback

4. **Performance**: Resolution generation takes 3-4 seconds (normal for LLM calls), but UI state management could be improved.

### Planned Changes

1. **Fix UI Workflow Logic** (`ui/src/components/IncidentDetail.js`):
   - Remove auto-triggering of resolution for AUTO policy
   - Only enable "Generate Resolution" button when appropriate
   - Show feedback form ONLY for PROPOSE/REVIEW policies
   - Hide feedback form after approval (don't show again)

2. **Fix Backend Evidence Warning Bug** (`ai_service/agents/resolution_copilot.py`):
   - Ensure `evidence_warning` and `resolution_evidence_warning` are initialized at function start
   - Already fixed, but verify Docker container has latest code

3. **Improve State Management**:
   - Track whether feedback has been provided
   - Update button state based on policy + feedback status
   - Better loading states during resolution generation

4. **Add Frontend Logging**:
   - Console logging for debugging
   - Error tracking for failed API calls

### Implementation Order

1. ✅ Update CONTEXT.md with workflow documentation
2. Fix UI workflow logic (remove auto-trigger, fix button enable logic)
3. Verify backend bug fix is deployed
4. Add frontend logging
5. Test end-to-end workflow

---

## Deployment and Infrastructure

### Docker Compose Setup

The entire stack can be deployed using Docker Compose, including:
- **UI (Frontend)**: React app served via nginx
- **AI Service**: FastAPI backend
- **Ingestion Service**: Data ingestion API
- **PostgreSQL**: Database with pgvector extension
- **Prometheus**: Metrics collection

#### Services and Ports

| Service | Container Name | Port | Description |
|---------|---------------|------|-------------|
| UI | `noc-ai-ui` | 3000 | React frontend (nginx) |
| AI Service | `noc-ai-service` | 8001 | FastAPI backend API |
| Ingestion Service | `noc-ai-ingestion` | 8002 | Data ingestion API |
| PostgreSQL | `noc-ai-postgres` | 5432 | Database |
| Prometheus | `noc-ai-prometheus` | 9090 | Metrics |

#### Starting the Stack

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Rebuild after code changes
docker-compose up -d --build

# Stop all services
docker-compose down
```

### UI Architecture

#### Frontend Stack
- **Framework**: React 18.2.0
- **HTTP Client**: Axios
- **Build Tool**: react-scripts (Create React App)
- **Production Server**: Nginx (Alpine)

#### Design System

- Dark-theme design tokens defined in `ui/src/styles/designSystem.css` (colors, typography, spacing, radii, shadows).
- Shared layout primitives (sidebar shell, top bar, modal) live in `App.css` and `components/layout/`.
- Common UI primitives start with `components/common/Button` to ensure consistent styling for actions across the UI.
- Buttons, cards, pills, and forms derive their styling directly from the CSS variables so the UI remains cohesive without pulling in a third-party component library.

#### UI Docker Setup

**Files**:
- `ui/Dockerfile`: Multi-stage build (Node.js build → Nginx serve)
- `ui/nginx.conf`: Nginx configuration with API proxy
- `ui/.dockerignore`: Excludes node_modules, build artifacts

**Build Process**:
1. **Build Stage**: Node.js 18 Alpine
   - Installs dependencies (`npm ci`)
   - Builds React app (`npm run build`)
2. **Production Stage**: Nginx Alpine
   - Copies built app from build stage
   - Serves static files
   - Proxies `/api/*` requests to backend

#### API Integration

The UI uses environment-aware API URLs:
- **Docker/Production**: Uses relative paths (`/api/v1/*`) - proxied by nginx
- **Local Development**: Uses `http://localhost:8001/api/v1`

**Nginx Proxy Configuration**:
```nginx
location /api {
    proxy_pass http://ai-service:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    # ... other headers
}
```

This eliminates CORS issues and allows the UI to make requests as if they're same-origin.

#### UI Components

**Main Components** (`ui/src/components/`):
- `IncidentList.js`: Displays incidents with selection + triage creation CTA.
- `IncidentDetail.js`: Full-width, tabbed incident workspace with workflow hero, progress stepper, timeline, and inline HITL forms.
- `hitl/ProgressStepper.js`: Visualizes state bus steps + WebSocket status.
- `hitl/PendingActionCard.js`, `TriageReviewForm.js`, `ResolutionReviewForm.js`: Render pending HITL actions with inline review/approval UX.

**Key Features**:
- WebSocket-powered workflow hero that surfaces policy band, severity/confidence, pending action status, and action buttons.
- Responsive, full-width layout (two-column on desktop, stacked on mobile) with reusable layout panes defined in `App.css`.
- Tabbed detail surface (Overview, Triage, Resolution, Evidence, Timeline) with contextual cards and grids.
- Real-time timeline view derived from state history (includes paused/resumed markers and timestamps when available).
- Inline pending-action cards that resume the backend via `onRespondPendingAction`.
- Workspace tabs (Incidents, Runbooks, Analytics) live inside `TopBar` so operators can pivot contexts without leaving the shell; non-incident tabs currently show guided placeholders.
- `IncidentList` uses `react-window` virtualization + pagination to keep scrolling smooth even with large datasets, while still supporting bulk selection, quick actions, and HITL status badges.

#### UI State Management

- `AgentStateContext` supplies live agent state + connection status to any component beneath `AgentStateProvider`.
- `useAgentState` hook handles WebSocket lifecycle, reconnection, and JSON parsing.
- `IncidentDetail` tracks `legacyReviewMode` (manual fallback) and `activeTab`; everything else is driven directly from live state snapshots (triage/resolution/policy/pending_action).
- Policy-based action buttons live inside the workflow hero: they evaluate `canAutoApply` / `requiresApproval` and toggle between manual feedback vs automatic resolution triggers.

### Backend Docker Setup

**Dockerfile** (root):
- Base: Python 3.9-slim
- Installs system dependencies (gcc, postgresql-client)
- Installs Python dependencies from `requirements.txt`
- Runs as non-root user (`appuser`)
- Exposes port 8001
- Health check endpoint

**Volumes**:
- `./config:/app/config:ro`: Configuration files (read-only)
- `./logs:/app/logs`: Log files

**Environment Variables**:
- `DATABASE_URL`: PostgreSQL connection string
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: Database config
- `OPENAI_API_KEY`: OpenAI API key (required)
- `LOG_LEVEL`: Logging level (default: INFO)

### Network Configuration

All services are on the `noc-ai-network` bridge network:
- Services can communicate using container names (e.g., `ai-service:8001`)
- UI proxies to `ai-service:8001` via nginx
- All services can access `postgres:5432`

### Data Persistence

**Volumes**:
- `postgres_data`: PostgreSQL data directory
- `prometheus_data`: Prometheus metrics storage

**Note**: Logs are stored in `./logs` directory (mounted as volume).

### Development vs Production

**Development**:
- UI can run separately: `cd ui && npm start` (port 3000, proxies to localhost:8001)
- Backend can run locally: `uvicorn ai_service.main:app --reload`
- Hot reload enabled for faster iteration

**Production (Docker)**:
- UI built and served via nginx (optimized, no dev server overhead)
- Backend runs in container (no hot reload)
- All services managed by docker-compose
- Single command to start entire stack

### Troubleshooting Docker

**Common Issues**:

1. **Container not starting**:
   ```bash
   docker-compose logs <service-name>
   docker-compose ps  # Check container status
   ```

2. **Code changes not reflected**:
   ```bash
   docker-compose build --no-cache <service-name>
   docker-compose up -d <service-name>
   ```

3. **Port conflicts**:
   - Check if ports 3000, 8001, 8002, 5432, 9090 are already in use
   - Modify ports in `docker-compose.yml` if needed

4. **Database connection issues**:
   - Ensure `postgres` service is healthy: `docker-compose ps postgres`
   - Check network connectivity: `docker-compose exec ai-service ping postgres`

5. **UI not connecting to backend**:
   - Check nginx logs: `docker-compose logs ui`
   - Verify API proxy config in `ui/nginx.conf`
   - Check backend is running: `docker-compose ps ai-service`

---

## State-Based HITL System

### Overview

The system includes a state-based Human-In-The-Loop (HITL) integration that supports real-time agent workflows with state emission and pause/resume capabilities. **Note: We use WebSocket directly (NOT CopilotKit)** - CopilotKit was only used as a reference pattern for the HITL concept.

### HITL Implementation Pattern

The HITL system follows this pattern:
1. **Agent runs** → emits state snapshots at each step
2. **Hits review checkpoint** → emits state with `pending_action`
3. **State sent to UI** via WebSocket → UI renders review component
4. **Human approves/edits** → submits response via REST API
5. **Response fed back** → agent resumes from checkpoint
6. **Agent continues** → completes remaining steps

This is similar to CopilotKit/LangGraph patterns but implemented with our own WebSocket infrastructure.

### State Models (`ai_service/state/models.py`)

- **`AgentState`**: Canonical state model with incident metadata, current step, agent type, progress tracking, policy state, pending actions, logs, and error state
- **`PendingAction`**: Model for HITL actions awaiting human response
- **`ActionResponse`**: Model for human responses to actions
- **`AgentStep`**: Enum for agent execution steps (INITIALIZED, RETRIEVING_CONTEXT, CONTEXT_RETRIEVED, CALLING_LLM, LLM_COMPLETED, VALIDATING, VALIDATION_COMPLETE, POLICY_EVALUATING, POLICY_EVALUATED, PAUSED_FOR_REVIEW, RESUMED_FROM_REVIEW, STORING, COMPLETED, ERROR)

### State Bus (`ai_service/state/bus.py`)

- **`StateBus`**: Central state management system
  - Emits state snapshots to subscribers
  - Manages pending HITL actions
  - Handles pause/resume logic
  - Persists state to database
  - Thread-safe with async locks
  - Reloads non-completed states on startup so workflows survive restarts
  - Guards against duplicate resume calls (idempotent action tracking)
  - Background monitor escalates expired pending actions to `approve_policy` checkpoints and records timeout metrics

### State Repository (`ai_service/repositories/agent_state_repository.py`)

- **`AgentStateRepository`**: Database persistence for agent state
  - Save/load agent state
  - Query pending actions
  - Supports state recovery after restarts

### Agent State Endpoints (`ai_service/api/v1/agents.py`)

- **`GET /api/v1/agents/{incident_id}/state`**: Get current agent state
- **`WebSocket /api/v1/agents/{incident_id}/state`**: Real-time state streaming
- **`POST /api/v1/agents/{incident_id}/actions/{action_name}/respond`**: Respond to HITL action
- **`GET /api/v1/agents/{incident_id}/actions/pending`**: Get pending action

### State-Based Triage Agent (`ai_service/agents/triager_state.py`)

- **`triage_agent_state()`**: Async state-based triage agent
  - Emits state at each step
  - Pauses for HITL when `requires_approval=True`
  - Returns state in response

### State-Based Resolution Agent (`ai_service/agents/resolution_copilot_state.py`)

- **`resolution_agent_state()`**: Async analogue of `resolution_copilot_agent`
  - Requires an existing incident (triage first) to ensure triage/policy context
  - Emits the same state machine events (retrieval → LLM → validation → storing)
  - Persists provisional resolution output/evidence, then:
    - Auto-completes when `can_auto_apply=True` and `requires_approval=False`
    - Or pauses with a `review_resolution` action so a human can edit/approve before execution
  - Returns the latest `AgentState` plus `pending_action` metadata so the UI can display the resolution review form inline

### State Bus Persistence & Timeout Monitor

- On startup the global `StateBus` reloads any non-completed states from `agent_state`, rehydrates live WebSocket data, and repopulates the pending-action gauge so analysts can refresh the UI without losing progress.
- Pending actions are monitored via an async background task (configured in `ai_service/main.py` startup). When `expires_at` is reached, the bus marks the state as `ERROR`, removes the pending action, emits an updated snapshot, and records timeout metrics (`hitl_actions_total{status="timeout"}` + `hitl_action_duration_seconds`).
- When a reviewer responds, `resume_from_action()` now records the action duration and decrements `hitl_actions_pending`, guaranteeing the gauge stays accurate across restarts.
- The repository gained `list_states()` so recovery can happen deterministically, and the bus exposes `start()/stop()` for FastAPI lifecycle hooks.

### Database Schema

- **`agent_state` table** (migration `003_add_agent_state.sql`): Stores agent state snapshots
  - Columns: id, incident_id, agent_type, current_step, state_data (JSONB), pending_action (JSONB)
  - Indexes for efficient querying

### State-Based Flow

1. Client calls `POST /api/v1/triage?use_state=true`
2. Agent initializes state and emits `INITIALIZED`
3. Agent retrieves context → emits `RETRIEVING_CONTEXT` → `CONTEXT_RETRIEVED`
4. Agent calls LLM → emits `CALLING_LLM` → `LLM_COMPLETED`
5. Agent validates → emits `VALIDATING` → `VALIDATION_COMPLETE`
6. Agent evaluates policy → emits `POLICY_EVALUATING` → `POLICY_EVALUATED`
7. If approval needed: Agent pauses and emits `PAUSED_FOR_REVIEW`, creates `PendingAction`
8. Human responds via `POST /api/v1/agents/{incident_id}/actions/{action_name}/respond`
9. Agent resumes → emits `RESUMED_FROM_REVIEW` → continues to `STORING` → `COMPLETED`

### Frontend Integration (WebSocket-Based)

**Current State**: Custom, state-aware React UI that consumes the WebSocket stream directly (no CopilotKit). Live workflow, timeline, and pending-action forms are already wired to the backend.

**Key Building Blocks**:

1. **WebSocket Hook** (`ui/src/hooks/useAgentState.js`):
   - Connects to `/api/v1/agents/{incident_id}/state`
   - Handles open/close/error/reconnect lifecycle
   - Emits parsed `AgentState` snapshots + connection status

2. **State Context** (`ui/src/context/AgentStateContext.js`):
   - Wraps any view needing live state
   - Provides `{ state, connectionStatus }` via React context

3. **HITL Components** (`ui/src/components/hitl/`):
   - `ProgressStepper`: shows ordered steps + connection badge
   - `PendingActionCard`: renders the correct review form, status, and CTA
   - `TriageReviewForm` / `ResolutionReviewForm`: inline editing with diff view, validation, and submission to `/actions/{action_name}/respond`
   - **Diff View**: Visual before/after comparison showing all form changes (text fields side-by-side, arrays with added/removed indicators)

4. **Incident Workspace** (`ui/src/components/IncidentDetail.js`):
   - Workflow hero with policy/severity badges and action buttons
   - Tabbed layout (Overview, Triage, Resolution, Evidence, Timeline)
   - **Enhanced Timeline**: Detailed state transition history with logs, milestones, and action events
   - Live timeline + full-width grids leveraging the shared layout styles in `App.css`

5. **User Experience Enhancements**:
   - **Keyboard Shortcuts** (`ui/src/hooks/useKeyboardShortcuts.js`):
     - `Ctrl+K` (or `Cmd+K`): Focus search input
     - `Ctrl+N` (or `Cmd+N`): Open new triage form
     - `Escape`: Close modal or go back from incident detail
     - `Ctrl+R` (or `Cmd+R`): Refresh incidents list
     - `Ctrl+Z`: Undo form changes (in HITL forms)
     - `Ctrl+Shift+Z` or `Ctrl+Y`: Redo form changes (in HITL forms)
   - **Theme Toggle** (`ui/src/context/ThemeContext.js`, `ui/src/components/common/ThemeToggle.js`):
     - Light/dark theme switching with localStorage persistence
     - Respects system preference on first load
     - Smooth transitions between themes
   - **Undo/Redo** (`ui/src/hooks/useUndoRedo.js`):
     - Full undo/redo history for HITL form edits (up to 50 states)
     - Keyboard shortcuts and UI buttons
     - Integrated into TriageReviewForm and ResolutionReviewForm
   - **Optimistic UI Updates**: Immediate UI feedback for feedback submissions and bulk actions with automatic rollback on API errors
   - **Sound & Visual Alerts**: Browser tab title flashing and audio alerts (800Hz tone) when pending actions appear
   - **Auto-Refresh**: Automatic refresh of insight cards and incident list every 30 seconds when on incidents workspace

**Frontend Structure** (current):
```
ui/src/
├── hooks/
│   ├── useAgentState.js          # WebSocket connection and state parsing
│   ├── useKeyboardShortcuts.js  # Keyboard shortcut handler
│   └── useUndoRedo.js           # Undo/redo history management
├── context/
│   ├── AgentStateContext.js     # State context provider
│   ├── ToastContext.js          # Toast notification system
│   └── ThemeContext.js          # Theme management (light/dark)
├── components/
│   ├── IncidentList.js          # Virtualized list with bulk operations
│   ├── IncidentDetail.js        # Tabbed workspace with enhanced timeline
│   ├── common/
│   │   ├── Button.js            # Reusable button component
│   │   ├── Toast.js             # Toast notification component
│   │   ├── Tooltip.js           # Tooltip component
│   │   ├── LoadingSkeleton.js   # Loading skeleton components
│   │   ├── ErrorBoundary.js    # Error boundary for graceful error handling
│   │   ├── DiffView.js          # Diff view for before/after comparisons
│   │   └── ThemeToggle.js       # Light/dark theme toggle button
│   ├── hitl/
│   │   ├── ProgressStepper.js  # Visual progress indicator
│   │   ├── PendingActionCard.js # Pending action display
│   │   ├── TriageReviewForm.js  # Triage review with diff view
│   │   └── ResolutionReviewForm.js
│   └── layout/
│       ├── Sidebar.js           # Global sidebar with badges
│       └── TopBar.js            # Top navigation with workspace tabs
```

### Correct HITL Flow

**Backend**:
1. Agent emits state at each step via `state_bus.emit_state()`
2. When approval needed: `state_bus.pause_for_action()` creates `PendingAction`
3. Agent pauses execution (returns response with `pending_action`)
4. Backend waits for human response via REST API
5. On response: `state_bus.resume_from_action()` updates state
6. Agent continues execution (if implemented as async/resumable). For triage/resolution today, the pause simply hands control to the human reviewer; edits are persisted via `IncidentService` before resuming the state stream.

**Frontend**:
1. Connect to WebSocket when incident selected
2. Receive state updates in real-time
3. When `state.pending_action` exists: Show review form
4. User reviews/edits and submits
5. POST to `/api/v1/agents/{incident_id}/actions/{action_name}/respond`
6. Continue receiving state updates as agent resumes

**Important**: The agent doesn't actually "pause" in the traditional sense - it returns a response with `pending_action` and the frontend must call the resume endpoint to continue. For true pause/resume, the agent would need to be implemented as a state machine that can be resumed (future enhancement).

---

**Last Updated**: 2025-01-XX
**Maintained By**: Development Team

