"""Ingestion service FastAPI application."""

import os
from typing import Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from ingestion.models import IngestDocument, IngestAlert, IngestIncident, IngestRunbook, IngestLog
from ingestion.normalizers import (
    normalize_alert,
    normalize_incident,
    normalize_runbook,
    normalize_log,
    normalize_json_data,
)
from ingestion.db_ops import insert_document_and_chunks
from ingestion.api import documents
from dotenv import load_dotenv

# Import logging (use ai_service modules if available)
import os

try:
    from ai_service.core import setup_logging, get_logger
except ImportError:
    # Fallback if ai_service modules not available
    import logging

    def setup_logging(log_level="INFO", log_file=None, log_dir=None, service_name="ingestion"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)


load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE", None)
log_dir = os.getenv("LOG_DIR", None)
setup_logging(log_level=log_level, log_file=log_file, log_dir=log_dir, service_name="ingestion")
logger = get_logger(__name__)

app = FastAPI(
    title="NOC Ingestion Service",
    version="1.0.0",
    description="Document ingestion service for NOC Agent AI",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
if allowed_origins_env:
    allowed_origins = [
        origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()
    ]
else:
    allowed_origins = ["http://localhost:5173"]
    logger.warning(
        "CORS_ALLOWED_ORIGINS not set. Using default localhost origin for development. "
        "This should be configured in production!"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy", "service": "ingestion", "version": "1.0.0"}


# Include documents router
app.include_router(documents.router, tags=["documents"])


@app.post("/ingest")
def ingest(doc: IngestDocument):
    """
    Ingest a document (generic endpoint).

    This endpoint:
    1. Stores the document
    2. Chunks the document
    3. Generates embeddings for each chunk
    4. Stores chunks with embeddings and tsvector
    """
    logger.info(f"Ingesting document: type={doc.doc_type}, title={doc.title[:50]}...")

    try:
        doc_id = insert_document_and_chunks(
            doc_type=doc.doc_type,
            service=doc.service,
            component=doc.component,
            title=doc.title,
            content=doc.content,
            tags=doc.tags,
            last_reviewed_at=doc.last_reviewed_at,
        )

        logger.info(f"Document ingested successfully: document_id={doc_id}")

        return {"status": "ok", "document_id": doc_id, "message": "Document ingested successfully"}
    except Exception as e:
        logger.error(f"Document ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/alert")
def ingest_alert(alert: IngestAlert):
    """Ingest a historical alert."""
    logger.info(f"Ingesting alert: alert_id={alert.alert_id}, title={alert.title[:50]}...")

    try:
        doc = normalize_alert(alert)
        doc_id = insert_document_and_chunks(
            doc_type=doc.doc_type,
            service=doc.service,
            component=doc.component,
            title=doc.title,
            content=doc.content,
            tags=doc.tags,
            last_reviewed_at=doc.last_reviewed_at,
        )

        logger.info(f"Alert ingested successfully: document_id={doc_id}")

        return {"status": "ok", "document_id": doc_id, "message": "Alert ingested successfully"}
    except Exception as e:
        logger.error(f"Alert ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/incident")
def ingest_incident(incident: IngestIncident):
    """Ingest a historical incident as an incident signature."""
    logger.info(f"Ingesting incident: title={incident.title[:50]}...")

    try:
        from ingestion.db_ops import insert_incident_signature

        doc, signature = normalize_incident(incident)
        signature_id = insert_incident_signature(
            signature,
            source_incident_id=incident.incident_id,
            source_document_id=None,  # We don't create a document for signatures
            incident_title=incident.title,
            incident_description=incident.description,
        )
        logger.info(
            f"Incident signature ingested successfully: signature_id={signature_id}, signature_id={signature.incident_signature_id}"
        )

        return {
            "status": "ok",
            "signature_id": signature_id,
            "incident_signature_id": signature.incident_signature_id,
            "message": "Incident signature ingested successfully",
        }
    except Exception as e:
        logger.error(f"Incident ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/runbook")
def ingest_runbook(runbook: IngestRunbook):
    """Ingest a runbook with atomic steps."""
    logger.info(f"Ingesting runbook: title={runbook.title[:50]}...")

    try:
        from ingestion.db_ops import insert_runbook_with_steps

        doc, steps = normalize_runbook(runbook)
        logger.info(f"Extracted {len(steps)} steps from runbook: {runbook.title}")

        if len(steps) == 0:
            logger.warning(
                f"No steps extracted from runbook: {runbook.title}. Content length: {len(runbook.content)}"
            )

        doc_id = insert_runbook_with_steps(
            doc_type=doc.doc_type,
            service=doc.service,
            component=doc.component,
            title=doc.title,
            content=doc.content,
            tags=doc.tags,
            last_reviewed_at=doc.last_reviewed_at,
            steps=steps,
            prerequisites=runbook.prerequisites,  # Pass prerequisites from historical data
        )
        logger.info(f"Runbook ingested successfully: document_id={doc_id}, steps={len(steps)}")

        return {
            "status": "ok",
            "document_id": doc_id,
            "steps_count": len(steps),
            "message": "Runbook ingested successfully",
        }
    except Exception as e:
        logger.error(f"Runbook ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/log")
def ingest_log(log: IngestLog):
    """Ingest a log snippet (supports plain text, JSON, syslog formats)."""
    logger.info(f"Ingesting log: service={log.service}, component={log.component}")

    try:
        doc = normalize_log(log)
        doc_id = insert_document_and_chunks(
            doc_type=doc.doc_type,
            service=doc.service,
            component=doc.component,
            title=doc.title,
            content=doc.content,
            tags=doc.tags,
            last_reviewed_at=doc.last_reviewed_at,
        )
        logger.info(f"Log ingested successfully: document_id={doc_id}")

        return {"status": "ok", "document_id": doc_id, "message": "Log ingested successfully"}
    except Exception as e:
        logger.error(f"Log ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/batch")
def ingest_batch(items: List[Dict], doc_type: str = "document"):
    """
    Batch ingest multiple items.

    Supports:
    - List of JSON objects (structured data)
    - List of strings (unstructured data)
    """
    logger.info(f"Batch ingesting {len(items)} items of type {doc_type}")

    try:
        results = []
        for item in items:
            if isinstance(item, str):
                # Unstructured text
                doc = IngestDocument(
                    doc_type=doc_type, title=f"{doc_type.title()} Document", content=item
                )
            elif isinstance(item, dict):
                # Structured JSON
                doc = normalize_json_data(item, doc_type)
            else:
                continue

            doc_id = insert_document_and_chunks(
                doc_type=doc.doc_type,
                service=doc.service,
                component=doc.component,
                title=doc.title,
                content=doc.content,
                tags=doc.tags,
                last_reviewed_at=doc.last_reviewed_at,
            )
            results.append({"document_id": doc_id, "title": doc.title})

        logger.info(f"Batch ingestion completed: {len(results)} items ingested successfully")

        return {"status": "ok", "ingested": len(results), "results": results}
    except Exception as e:
        logger.error(f"Batch ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("INGESTION_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("INGESTION_SERVICE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
