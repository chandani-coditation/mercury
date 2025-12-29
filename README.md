## NOC Agent AI

This project is a NOC triage and resolution assistant. It:

- Ingests runbooks, historical incidents, and logs into a Postgres + pgvector KB
- Exposes an AI backend (`ai-service`) for triage and resolution
- Provides a small React UI to submit new tickets and inspect results

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

## 4. Using the UI

1. Open `http://localhost:5173` in your browser.
2. The **New Ticket** form is pre-filled with a sample alert that should match an ingested database runbook.
3. Click **“Submit & Triage”** to:
   - Create an incident via the backend
   - Run triage using runbook/incident/log evidence from the KB
4. After triage, you can:
   - Review the policy band and approve (if required)
   - Click **“Generate Resolution”** to request a runbook-driven resolution plan.

The right-hand **Results** panel shows interactive, user-friendly views for:
   - **Triage**: Displays severity, confidence, category, affected services, and recommended actions
   - **Policy**: Shows policy band, approval requirements, and decision details
   - **Retrieval Evidence**: Interactive expandable chunks showing matched runbooks and historical incidents
   - **Resolution**: Final resolution plan

---

## 5. Running tests (optional)

Backend tests are written with `pytest`. From the repo root:

```bash
pytest
```

There are also helper scripts under `tests/` (e.g. `test_approve_and_resolve.sh`) to exercise the API end-to-end.

