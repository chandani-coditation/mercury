## NOC Agent AI

This project is a NOC triage and resolution assistant. It:

- Ingests runbooks, historical incidents, and logs into a Postgres + pgvector KB
- Exposes an AI backend (`ai-service`) for triage and resolution
- Provides a small React UI to submit new tickets and inspect results

### Key Features

- **Hybrid Search**: Combines vector similarity and full-text search using RRF (Reciprocal Rank Fusion)
- **Soft Filtering**: Service/component fields are used as relevance boosters, not hard filters, ensuring both triage and resolution agents work even with metadata mismatches
- **Service/Component Standardization**: Automatic normalization during ingestion ensures consistency between runbooks and incidents
- **Enhanced Confidence Calculation**: Confidence scores reflect both evidence quality and service/component match quality
- **Graceful Degradation**: Both agents work even when no historical evidence exists (with appropriate confidence levels)
- **Clear Status Indicators**: Both agents provide explicit success/failure status with detailed evidence counts and actionable warnings when no historical evidence is found
- **Query Enhancement**: Automatic query text enhancement with technical term extraction, abbreviation expansion, and synonym addition for better retrieval (soft rules with graceful degradation)
- **MMR Support**: Optional Maximal Marginal Relevance for diverse results (configurable per retrieval type)
- **Robust Error Handling**: Comprehensive retry logic with exponential backoff for embedding API calls, graceful fallbacks, and clear error messages
- **Soft Rules Principle**: All enhancements (normalization, query expansion, structured data extraction) are soft rules that gracefully degrade if they fail - they enhance results when working but never break the system or drastically reduce scores if they fail

---

## Prerequisites

- **Docker** and **docker compose**
- **Node.js** (v18+ recommended) and **npm** for the UI
- **LLM Access** (choose one):
  - **For local development/testing**: A valid **OpenAI API key**
  - **For production**: Access to a **Private LLM Gateway** with authentication credentials

---

## 0. Environment Setup

**IMPORTANT**: The `.env` file is **not included in the repository** (it's gitignored for security reasons). You must create it before starting services.

**Create `.env` file:**

```bash
cp env.template .env
```

**Edit `.env` and set your configuration:**

1. **LLM Configuration** (choose one option):

   **Option A: Direct OpenAI API** (for local development and testing):
   ```bash
   OPENAI_API_KEY=sk-your-api-key-here
   PRIVATE_LLM_GATEWAY=false
   ```
   This is the default mode. Use this for local development, testing, and when you have direct access to OpenAI API.

   **Option B: Private LLM Gateway** (for production):
   ```bash
   PRIVATE_LLM_GATEWAY=true
   PRIVATE_LLM_GATEWAY_URL=https://your-gateway-url/api/v1/ai/call
   PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL=https://your-gateway-url/api/v1/ai/openai/embeddings
   PRIVATE_LLM_AUTH_KEY=your-gateway-auth-key
   # Optional: Only needed if gateway requires custom SSL certificate
   PRIVATE_LLM_CERT_PATH=/path/to/certificate.pem
   ```
   Use this mode in production environments where LLM requests must go through a private gateway. When gateway mode is enabled, `OPENAI_API_KEY` is not required for LLM calls.

   **Note**: The system automatically detects which mode to use based on the `PRIVATE_LLM_GATEWAY` environment variable. When set to `true`, all LLM calls (chat completions and embeddings) are routed through the gateway instead of directly to OpenAI.

2. **Database Configuration** (defaults are usually fine):
   ```bash
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=noc_ai
   POSTGRES_USER=noc_ai
   POSTGRES_PASSWORD=noc_ai_password  # Change this in production!
   ```

3. **Frontend API URL** (defaults to localhost:8001):
   ```bash
   VITE_API_BASE_URL=http://localhost:8001/api/v1
   ```

**Note**: The `env.template` file shows all available configuration options with their defaults.

---

## 1. Start the backend (database + services)

**Prerequisite**: Create a `.env` file first (see Section 0 above).

From the repo root:

**If `.env` is in the root folder:**
```bash
docker compose up -d
```

**If your env file is in a different location or has a different name:**
```bash
ENV_FILE=/path/to/your.env docker compose up -d
```

**Examples:**
```bash
# Env file in root folder (default)
docker compose up -d

# Env file with different name
ENV_FILE=.env.production docker compose up -d

# Env file in different location
ENV_FILE=/path/to/custom.env docker compose up -d
```

This will start:

- `postgres` on `localhost:5432`
- `ai-service` (FastAPI) on `http://localhost:8001`
- `ingestion-service` on `http://localhost:8002` 
- `frontend` (React UI) on `http://localhost:5173`

You can check health with:

```bash
curl http://localhost:8001/api/v1/health
```

---

## 2. Database Setup

**Automatic Schema Creation:**

The PostgreSQL database schema is **automatically created** when the Docker container starts for the first time. The schema file (`db/schema.sql`) is automatically executed by PostgreSQL's initialization system.

**How it works:**
- When you run `docker compose up` for the first time, PostgreSQL detects that the database is empty
- It automatically runs all `.sql` files in `/docker-entrypoint-initdb.d/` (which includes `db/schema.sql`)
- All tables, indexes, triggers, and functions are created automatically
- On subsequent starts, the schema already exists, so initialization is skipped (this is safe)

**IMPORTANT: All database operations use Docker PostgreSQL only.**
- Scripts connect via `docker exec` to the `noc-ai-postgres` container
- Never uses local PostgreSQL instance
- Database credentials are read from `.env` file

**Database Configuration (in `.env`):**
- `POSTGRES_HOST=localhost` (for Docker port mapping)
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=noc_ai` (default)
- `POSTGRES_USER=noc_ai` (default)
- `POSTGRES_PASSWORD=noc_ai_password` (set your password)

**Verify database setup and schema creation:**
```bash
# Using Python script (uses Docker exec, reads from .env)
python scripts/db/verify_db.py

# Or directly via Docker - check if tables exist
docker exec noc-ai-postgres psql -U noc_ai -d noc_ai -c "\dt"

# Check specific tables
docker exec noc-ai-postgres psql -U noc_ai -d noc_ai -c "SELECT COUNT(*) FROM documents;"
docker exec noc-ai-postgres psql -U noc_ai -d noc_ai -c "SELECT COUNT(*) FROM incident_signatures;"
docker exec noc-ai-postgres psql -U noc_ai -d noc_ai -c "SELECT COUNT(*) FROM chunks;"
```

**Note**: If you need to recreate the database from scratch, you can:
```bash
# Stop containers and remove the volume
docker compose down -v

# Start again (schema will be recreated automatically)
docker compose up -d
```

## 3. Ingest runbooks and historical data (optional but recommended)

With the backend up, you can ingest runbooks and historical tickets data using command-line scripts.

**Ingest Runbooks:**

```bash
# Ingest all runbooks from a directory
python scripts/data/ingest_runbooks.py --dir runbooks

# Ingest a single runbook file
python scripts/data/ingest_runbooks.py --file "runbooks/Runbook - Database Alerts.docx"
```

**Ingest ServiceNow Tickets (CSV):**

```bash
# Ingest all CSV files from a directory
python scripts/data/ingest_servicenow_tickets.py --dir tickets_data

# Ingest a single CSV file
python scripts/data/ingest_servicenow_tickets.py --file "tickets_data/updated network filtered - Sheet1.csv"
```

**Note**: Make sure `.env` file is configured with correct database credentials before running ingestion scripts.

**Database Management:**
```bash
# Clean up all ingested data (for fresh re-ingestion)
python scripts/db/cleanup_db.py --yes

# Verify ingestion quality
python scripts/db/verify_db.py
```

**Note**: 
- Service/component values are automatically normalized during ingestion using `config/service_component_mapping.json`. This ensures consistency between runbooks and incidents, improving retrieval accuracy.
- Query text is automatically enhanced with technical term extraction, abbreviation expansion, and synonym addition for better retrieval quality.
- Both agents provide clear status indicators (`status`, `evidence_status`, `evidence_count`) and detailed warnings when no historical evidence is found, making it easy to diagnose issues.

---

## 4. Start the frontend UI

**Option 1: Using Docker (recommended)**

The frontend is automatically started with `docker compose up` and will be available at `http://localhost:5173`.

**Option 2: Local development**

From the `ui` directory:

```bash
cd ui
npm install
npm run dev
```

By default Vite will serve the UI on `http://localhost:5173`.

**Configuration:**

The UI expects the backend `ai-service` to be reachable at `http://localhost:8001`. 

- **Docker**: The API URL is configured via `VITE_API_BASE_URL` in your `.env` file (defaults to `http://localhost:8001/api/v1`)
- **Local development**: Update the API client in `ui/src/api/client.js` or set the `VITE_API_BASE_URL` environment variable

---

## 5. Understanding Agent Output

Both triage and resolution agents provide clear status indicators in their responses:

### Success Response (with evidence):
```json
{
  "status": "success",
  "evidence_status": "success",
  "evidence_count": {
    "incident_signatures": 3,
    "runbook_metadata": 2,
    "total": 5
  },
  "evidence_warning": null
}
```

### Failure Response (no evidence):
```json
{
  "status": "failed_no_evidence",
  "evidence_status": "failed_no_evidence",
  "evidence_count": {
    "incident_signatures": 0,
    "runbook_metadata": 0,
    "total": 0
  },
  "evidence_warning": "⚠️ NO EVIDENCE FOUND: No historical data in knowledge base. Please ingest runbooks and historical incidents first using: `python scripts/data/ingest_runbooks.py` and `python scripts/data/ingest_servicenow_tickets.py`. Status: FAILED (no historical evidence available)."
}
```

**Status Fields:**
- `status`: Overall status ("success" or "failed_no_evidence")
- `evidence_status`: Detailed evidence status ("success", "failed_no_evidence", "failed_no_matching_evidence")
- `evidence_count`: Breakdown of evidence found (incident signatures, runbook metadata, total)
- `evidence_warning`: Detailed warning message with actionable instructions (null if evidence found)

**Triage Output Fields:**
- `severity`: System-calculated from impact/urgency (not from LLM)
- `confidence`: System-calculated based on evidence quality and match scores (not from LLM)
- `policy`: System-determined by policy gate configuration (not from LLM)
- `category`: Extracted from historical incidents or alert labels
- `likely_cause`: LLM-generated summary based on evidence patterns (not a direct quote from historical data)

**Resolution Agent** includes similar fields:
- `status`: Overall resolution status
- `resolution_evidence_status`: Evidence status for resolution
- `evidence_count.context_chunks`: Number of context chunks used
- `resolution_evidence_warning`: Warning message if no evidence found

**Note**: Fields like `risk_level`, `estimated_time_minutes`, and `requires_approval` have been removed from resolution output as they were not based on historical data. `requires_approval` is now derived from the policy gate configuration.

---

## 6. Using the UI

1. Open `http://localhost:5173` in your browser.
2. The **New Ticket** form is pre-filled with a sample alert that should match an ingested database runbook.
3. Click **“Submit & Triage”** to:
   - Create an incident via the backend
   - Run triage using runbook/incident/log evidence from the KB
4. After triage, you can:
   - Review the policy band and approve (if required)
   - Click **“Generate Resolution”** to request a runbook-driven resolution plan.

The right-hand **Results** panel shows interactive, user-friendly views for:
   - **Triage**: Displays severity (system-calculated), confidence (system-calculated), category (from evidence), affected services, and likely cause (LLM-generated summary)
   - **Policy**: Shows policy band (system-determined), approval requirements (from policy gate), and decision details
   - **Retrieval Evidence**: Interactive expandable chunks showing matched runbooks and historical incidents
   - **Resolution**: Final resolution plan with steps, commands, and rollback procedures

---

## 7. Running tests (optional)

Backend tests are written with `pytest`. From the repo root:

```bash
pytest
```

There are also helper scripts under `tests/` (e.g. `test_approve_and_resolve.sh`) to exercise the API end-to-end.

---

## 8. CI/CD and GitHub Secrets Configuration

For CI/CD pipelines (e.g., GitHub Actions), you can configure LLM access using GitHub Secrets.

### Using OpenAI API Key in GitHub Actions

If your GitHub secret is named `OPENAI_API_KEY`:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

If your GitHub secret has a different name (e.g., `OPENAI_KEY`), map it to the expected environment variable:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_KEY }}
```

### Using Private LLM Gateway in GitHub Actions

For production deployments, configure the gateway settings:

```yaml
env:
  PRIVATE_LLM_GATEWAY: "true"
  PRIVATE_LLM_GATEWAY_URL: ${{ secrets.PRIVATE_LLM_GATEWAY_URL }}
  PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL: ${{ secrets.PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL }}
  PRIVATE_LLM_AUTH_KEY: ${{ secrets.PRIVATE_LLM_AUTH_KEY }}
  # Optional: Only if custom SSL certificate is required
  PRIVATE_LLM_CERT_PATH: ${{ secrets.PRIVATE_LLM_CERT_PATH }}
```

**Note**: The application reads environment variables directly, so no code changes are required when using GitHub Secrets. Simply ensure the environment variable names match what the application expects (as documented in `env.template`).

