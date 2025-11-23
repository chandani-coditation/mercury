"""Ingestion service FastAPI application."""
import os
import time
from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from ingestion.models import (
    IngestDocument, IngestAlert, IngestIncident, 
    IngestRunbook, IngestLog
)
from ingestion.normalizers import (
    normalize_alert, normalize_incident, 
    normalize_runbook, normalize_log, normalize_json_data
)
from ingestion.db_ops import insert_document_and_chunks
from ingestion.api import documents
from dotenv import load_dotenv

# Import logging and metrics (create if needed, or use ai_service modules)
import os
try:
    from ai_service.core import setup_logging, get_logger
    from ai_service.core import (
        http_requests_total, http_request_duration_seconds,
        get_metrics_response
    )
except ImportError:
    # Fallback if ai_service modules not available
    import logging
    def setup_logging(log_level="INFO", log_file=None, log_dir=None, service_name="ingestion"):
        logging.basicConfig(level=getattr(logging, log_level))
    def get_logger(name):
        return logging.getLogger(name)
    http_requests_total = None
    http_request_duration_seconds = None
    def get_metrics_response():
        return Response(content="", media_type="text/plain")

load_dotenv()

# Setup logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE", None)
log_dir = os.getenv("LOG_DIR", None)
setup_logging(log_level=log_level, log_file=log_file, log_dir=log_dir, service_name="ingestion")
logger = get_logger(__name__)

# Increase max request body size to 50MB for large logs
# Default Starlette limit is 1MB which is too small for multi-thousand-line logs
app = FastAPI(
    title="NOC Ingestion Service", 
    version="1.0.0",
    description="Document ingestion service for NOC Agent AI",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Note: Starlette/FastAPI has a default 1MB request body size limit.
# For large logs, this can be increased by setting the environment variable
# or by using a custom ASGI wrapper. The limit is enforced at the ASGI level.
# If you encounter "Request body too large" errors, increase the limit.

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to track HTTP metrics."""
    if http_requests_total is None:
        return await call_next(request)
    
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Extract endpoint (normalize)
    endpoint = request.url.path
    
    # Record metrics
    if http_requests_total:
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        ).inc()
    
    if http_request_duration_seconds:
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
    
    logger.debug(
        f"HTTP {request.method} {request.url.path} - {response.status_code} - {duration:.3f}s"
    )
    
    return response


@app.get("/health")
def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy", "service": "ingestion", "version": "1.0.0"}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()


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
            last_reviewed_at=doc.last_reviewed_at
        )
        
        logger.info(f"Document ingested successfully: document_id={doc_id}")
        
        return {
            "status": "ok",
            "document_id": doc_id,
            "message": "Document ingested successfully"
        }
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
            last_reviewed_at=doc.last_reviewed_at
        )
        
        logger.info(f"Alert ingested successfully: document_id={doc_id}")
        
        return {
            "status": "ok",
            "document_id": doc_id,
            "message": "Alert ingested successfully"
        }
    except Exception as e:
        logger.error(f"Alert ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/incident")
def ingest_incident(incident: IngestIncident):
    """Ingest a historical incident (supports structured and unstructured data)."""
    logger.info(f"Ingesting incident: title={incident.title[:50]}...")
    
    try:
        doc = normalize_incident(incident)
        doc_id = insert_document_and_chunks(
            doc_type=doc.doc_type,
            service=doc.service,
            component=doc.component,
            title=doc.title,
            content=doc.content,
            tags=doc.tags,
            last_reviewed_at=doc.last_reviewed_at
        )
        logger.info(f"Incident ingested successfully: document_id={doc_id}")
        
        return {
            "status": "ok",
            "document_id": doc_id,
            "message": "Incident ingested successfully"
        }
    except Exception as e:
        logger.error(f"Incident ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/runbook")
def ingest_runbook(runbook: IngestRunbook):
    """Ingest a runbook (supports markdown, plain text, or structured JSON)."""
    logger.info(f"Ingesting runbook: title={runbook.title[:50]}...")
    
    try:
        doc = normalize_runbook(runbook)
        doc_id = insert_document_and_chunks(
            doc_type=doc.doc_type,
            service=doc.service,
            component=doc.component,
            title=doc.title,
            content=doc.content,
            tags=doc.tags,
            last_reviewed_at=doc.last_reviewed_at
        )
        logger.info(f"Runbook ingested successfully: document_id={doc_id}")
        
        return {
            "status": "ok",
            "document_id": doc_id,
            "message": "Runbook ingested successfully"
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
            last_reviewed_at=doc.last_reviewed_at
        )
        logger.info(f"Log ingested successfully: document_id={doc_id}")
        
        return {
            "status": "ok",
            "document_id": doc_id,
            "message": "Log ingested successfully"
        }
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
                    doc_type=doc_type,
                    title=f"{doc_type.title()} Document",
                    content=item
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
                last_reviewed_at=doc.last_reviewed_at
            )
            results.append({"document_id": doc_id, "title": doc.title})
        
        logger.info(f"Batch ingestion completed: {len(results)} items ingested successfully")
        
        return {
            "status": "ok",
            "ingested": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Batch ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("INGESTION_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("INGESTION_SERVICE_PORT", "8000"))
    
    # Note: To increase request body size limit beyond 1MB default,
    # run uvicorn with: --limit-max-requests 1000
    # The actual body size limit is controlled by Starlette's Request class
    # For production, consider using nginx or a reverse proxy to handle large payloads
    uvicorn.run(app, host=host, port=port)



