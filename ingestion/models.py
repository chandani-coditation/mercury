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
    tags: Optional[Dict] = None  # Tags for additional metadata (assignment_group, impact, urgency, etc.)


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


class RunbookStep(BaseModel):
    """Atomic runbook step for storage (per architecture)."""

    step_id: str  # e.g., "RB123-S3"
    runbook_id: str  # e.g., "RB123"
    condition: str  # When this step applies
    action: str  # What to do
    expected_outcome: Optional[str] = None  # Expected result
    rollback: Optional[str] = None  # Rollback procedure
    risk_level: Optional[str] = None  # "low", "medium", "high"
    service: Optional[str] = None
    component: Optional[str] = None


class IncidentSignature(BaseModel):
    """Incident signature (pattern, not raw text) for storage (per architecture)."""

    incident_signature_id: str  # e.g., "SIG-DB-001"
    failure_type: str  # e.g., "SQL_AGENT_JOB_FAILURE"
    error_class: str  # e.g., "SERVICE_ACCOUNT_DISABLED"
    symptoms: List[str]  # List of symptom strings
    affected_service: Optional[str] = None
    resolution_refs: Optional[List[str]] = None  # List of step_ids (e.g., ["RB123-S3"])
    service: Optional[str] = None
    component: Optional[str] = None
    assignment_group: Optional[str] = None  # Team/group that handles this type of incident (e.g., "SE DBA SQL", "NOC")
    impact: Optional[str] = None  # Typical impact value from historical incidents (e.g., "3 - Low", "1 - High")
    urgency: Optional[str] = None  # Typical urgency value from historical incidents (e.g., "3 - Low", "1 - High")
    close_notes: Optional[str] = None  # Resolution notes/close notes from historical incidents (for resolution agent)
