"""Pydantic models for ingestion service."""

from pydantic import BaseModel
from typing import List, Dict, Optional, Union
from datetime import datetime


class IngestDocument(BaseModel):
    """Document to ingest (base model)."""

    doc_type: str  # "runbook", "incident", "alert", "log", "sop"
    service: Optional[str] = None
    component: Optional[str] = None
    title: str
    content: str
    tags: Optional[Dict] = None
    last_reviewed_at: Optional[datetime] = None


class IngestAlert(BaseModel):
    """Historical alert for ingestion."""

    alert_id: str
    source: str
    title: str
    description: str
    labels: Optional[Dict[str, str]] = {}
    severity: Optional[str] = None
    ts: Optional[datetime] = None
    resolution_status: Optional[str] = None
    resolution_notes: Optional[str] = None
    # Additional metadata
    metadata: Optional[Dict] = None


class IngestIncident(BaseModel):
    """Historical incident for ingestion."""

    incident_id: Optional[str] = None
    alert_id: Optional[str] = None
    title: str
    description: str
    severity: Optional[str] = None
    category: Optional[str] = None
    resolution_steps: Optional[List[str]] = None
    root_cause: Optional[str] = None
    affected_services: Optional[List[str]] = None
    timestamp: Optional[datetime] = None
    # For unstructured data
    raw_content: Optional[str] = None
    metadata: Optional[Dict] = None


class IngestRunbook(BaseModel):
    """Runbook for ingestion."""

    title: str
    service: Optional[str] = None
    component: Optional[str] = None
    content: str  # Can be markdown, plain text, or structured JSON
    steps: Optional[List[str]] = None  # For structured format
    prerequisites: Optional[List[str]] = None
    rollback_procedures: Optional[str] = None
    tags: Optional[Dict] = None
    metadata: Optional[Dict] = None


class IngestLog(BaseModel):
    """Log snippet for ingestion."""

    content: str  # Raw log content
    timestamp: Optional[datetime] = None
    level: Optional[str] = None  # error, warning, info, debug
    service: Optional[str] = None
    component: Optional[str] = None
    message: Optional[str] = None  # Extracted message
    context: Optional[Dict] = None  # JSON context
    log_format: Optional[str] = None  # "plain", "json", "syslog"
    metadata: Optional[Dict] = None
