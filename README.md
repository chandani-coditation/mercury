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
- A valid **OpenAI API key** exported as `OPENAI_API_KEY`

```bash
export OPENAI_API_KEY=sk-...
```

---

## 1. Start the backend (database + services)

From the repo root:

```bash
docker compose up -d
```

This will start:

- `postgres` on `localhost:5432`
- `ai-service` (FastAPI) on `http://localhost:8001`
- `ingestion-service` on `http://localhost:8002`

You can check health with:

```bash
curl http://localhost:8001/api/v1/health
```

---

## 2. Ingest runbooks and historical data (optional but recommended)

With the backend up, you can ingest runbooks from the `runbooks/` folder:

```bash
python scripts/data/ingest_runbooks.py --dir runbooks
```

Similarly, if you have historical tickets/logs configured, use the other ingest scripts under `scripts/data/`.

**Note**: 
- Service/component values are automatically normalized during ingestion using `config/service_component_mapping.json`. This ensures consistency between runbooks and incidents, improving retrieval accuracy.
- Query text is automatically enhanced with technical term extraction, abbreviation expansion, and synonym addition for better retrieval quality.
- Both agents provide clear status indicators (`status`, `evidence_status`, `evidence_count`) and detailed warnings when no historical evidence is found, making it easy to diagnose issues.

---

## 3. Start the frontend UI

From the `ui` directory:

```bash
cd ui
npm install
npm run dev
```

By default Vite will serve the UI on `http://localhost:5173`.

The UI expects the backend `ai-service` to be reachable at `http://localhost:8001`. If you change ports, update the API client in `ui/src/api/client.js`.

---

## 4. Understanding Agent Output

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

## 5. Using the UI

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

## 5. Running tests (optional)

Backend tests are written with `pytest`. From the repo root:

```bash
pytest
```

There are also helper scripts under `tests/` (e.g. `test_approve_and_resolve.sh`) to exercise the API end-to-end.


