"""Normalizers to convert various input formats to IngestDocument format."""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from ingestion.models import IngestAlert, IngestIncident, IngestRunbook, IngestLog, IngestDocument

# Optional JSON schema validation
try:
    import jsonschema

    JSON_SCHEMA_AVAILABLE = True
except ImportError:
    JSON_SCHEMA_AVAILABLE = False


def _load_json_schema(schema_name: str) -> dict:
    """Load JSON schema from config/json_schemas/ directory."""
    try:
        project_root = Path(__file__).parent.parent
        schema_path = project_root / "config" / "json_schemas" / f"{schema_name}_schema.json"
        if schema_path.exists():
            with open(schema_path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _validate_with_schema(data: dict, schema_name: str) -> tuple[bool, list]:
    """Validate data against JSON schema if available."""
    if not JSON_SCHEMA_AVAILABLE:
        return True, []  # Skip validation if jsonschema not installed

    schema = _load_json_schema(schema_name)
    if not schema:
        return True, []  # Skip if schema not found

    try:
        jsonschema.validate(instance=data, schema=schema)
        return True, []
    except jsonschema.ValidationError as e:
        return False, [str(e)]
    except Exception as e:
        return True, []  # Don't fail on validation errors, just log


def normalize_alert(alert: IngestAlert) -> IngestDocument:
    """Convert historical alert to IngestDocument format."""
    # Extract service/component from labels
    service = alert.labels.get("service") if alert.labels else None
    component = alert.labels.get("component") if alert.labels else None

    # Build content from alert fields
    content_parts = [
        f"Alert: {alert.title}",
        f"Description: {alert.description}",
    ]

    if alert.resolution_status:
        content_parts.append(f"Resolution Status: {alert.resolution_status}")

    if alert.resolution_notes:
        content_parts.append(f"Resolution Notes: {alert.resolution_notes}")

    if alert.labels:
        content_parts.append(f"Labels: {', '.join(f'{k}={v}' for k, v in alert.labels.items())}")

    content = "\n\n".join(content_parts)

    # Build comprehensive tags (mandatory fields from specification)
    tags = {
        "type": "historical_alert",
        "alert_id": alert.alert_id,
        "source": alert.source,
        "severity": alert.severity,
        "service": service,  # From labels
        "component": component,  # From labels
        "env": alert.labels.get("environment") if alert.labels else None,
        "risk": alert.severity,  # Use severity as risk indicator
        "last_reviewed_at": alert.ts.isoformat() if alert.ts else None,
        **(alert.metadata or {}),
    }

    # Remove None values
    tags = {k: v for k, v in tags.items() if v is not None}

    return IngestDocument(
        doc_type="alert",
        service=service,
        component=component,
        title=f"Alert: {alert.title}",
        content=content,
        tags=tags,
        last_reviewed_at=alert.ts,
    )


def normalize_incident(incident: IngestIncident, validate_schema: bool = False) -> IngestDocument:
    """Convert historical incident to IngestDocument format."""
    # Use raw_content if available (for unstructured), otherwise build from structured fields
    if incident.raw_content:
        content = incident.raw_content
    else:
        content_parts = [
            f"Incident: {incident.title}",
            f"Description: {incident.description}",
        ]

        if incident.root_cause:
            content_parts.append(f"Root Cause: {incident.root_cause}")

        if incident.resolution_steps:
            content_parts.append("Resolution Steps:")
            for i, step in enumerate(incident.resolution_steps, 1):
                content_parts.append(f"  {i}. {step}")

        if incident.affected_services:
            content_parts.append(f"Affected Services: {', '.join(incident.affected_services)}")

        content = "\n\n".join(content_parts)

    # Extract service from affected_services if available
    service = None
    if incident.affected_services and len(incident.affected_services) > 0:
        raw_service = incident.affected_services[0]
        # Parse service (e.g., "Database-SQL" -> "Database", "Server" stays "Server")
        if "-" in raw_service:
            service = raw_service.split("-")[0].strip()
        else:
            service = raw_service

    # Extract component from title, description, or category
    component = None
    search_text = f"{incident.title} {incident.description or ''} {incident.category or ''}".lower()

    # Pattern matching for common component types
    if "volume" in search_text or "disk" in search_text or "storage" in search_text:
        component = "Disk"
    elif "cpu" in search_text or "processor" in search_text:
        component = "CPU"
    elif "memory" in search_text or "ram" in search_text:
        component = "Memory"
    elif "network" in search_text or "connectivity" in search_text:
        component = "Network"
    elif "database" in search_text or "sql" in search_text or "db" in search_text:
        component = "Database"
    elif "performance" in search_text:
        component = "Performance"
    elif incident.category:
        # Use category as fallback
        component = incident.category

    # Build comprehensive tags (mandatory fields from specification)
    tags = {
        "type": "historical_incident",
        "incident_id": incident.incident_id,
        "ticket_id": incident.incident_id,  # ServiceNow ticket ID
        "canonical_incident_key": incident.incident_id,  # Canonical key for matching
        "alert_id": incident.alert_id,
        "severity": incident.severity,
        "category": incident.category,
        "service": service,  # From affected_services
        "component": component,  # Extracted from title/description/category
        "env": None,  # Environment (can be extracted from metadata if available)
        "risk": incident.severity,  # Use severity as risk indicator
        "last_reviewed_at": incident.timestamp.isoformat() if incident.timestamp else None,
        **(incident.metadata or {}),
    }

    # Remove None values
    tags = {k: v for k, v in tags.items() if v is not None}

    # Optional JSON schema validation
    if validate_schema:
        incident_dict = incident.model_dump(mode="json", exclude_none=True)
        is_valid, errors = _validate_with_schema(incident_dict, "incident")
        if not is_valid:
            from ai_service.core import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Incident schema validation warnings: {errors}")

    return IngestDocument(
        doc_type="incident",
        service=service,
        component=component,  # Now properly extracted
        title=f"Incident: {incident.title}",
        content=content,
        tags=tags,
        last_reviewed_at=incident.timestamp,
    )


def normalize_runbook(runbook: IngestRunbook, validate_schema: bool = False) -> IngestDocument:
    """Convert runbook to IngestDocument format."""
    # Use content as-is (can be markdown, plain text, or structured)
    content = runbook.content

    # If structured format, enrich content
    if runbook.steps:
        steps_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(runbook.steps))
        content = f"{content}\n\nSteps:\n{steps_text}"

    if runbook.prerequisites:
        prereq_text = "\n".join(f"- {p}" for p in runbook.prerequisites)
        content = f"{content}\n\nPrerequisites:\n{prereq_text}"

    if runbook.rollback_procedures:
        content = f"{content}\n\nRollback Procedures:\n{runbook.rollback_procedures}"

    # Build comprehensive tags (mandatory fields from specification)
    tags = {
        "type": "runbook",
        "runbook_id": runbook.tags.get("runbook_id") if runbook.tags else None,
        "service": runbook.service,
        "component": runbook.component,
        "env": None,  # Environment (can be extracted from metadata if available)
        "risk": None,  # Risk level (can be extracted from content if available)
        "last_reviewed_at": None,  # Can be extracted from metadata if available
        **(runbook.tags or {}),
        **(runbook.metadata or {}),
    }

    # Remove None values
    tags = {k: v for k, v in tags.items() if v is not None}

    # Optional JSON schema validation
    if validate_schema:
        runbook_dict = runbook.model_dump(mode="json", exclude_none=True)
        is_valid, errors = _validate_with_schema(runbook_dict, "runbook")
        if not is_valid:
            from ai_service.core import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Runbook schema validation warnings: {errors}")

    return IngestDocument(
        doc_type="runbook",
        service=runbook.service,
        component=runbook.component,
        title=runbook.title,
        content=content,
        tags=tags,
        last_reviewed_at=None,
    )


def normalize_log(log: IngestLog) -> IngestDocument:
    """Convert log snippet to IngestDocument format."""
    # Build title from log metadata
    title_parts = []
    if log.service:
        title_parts.append(log.service)
    if log.component:
        title_parts.append(log.component)
    if log.level:
        title_parts.append(log.level.upper())
    title = f"Log: {' '.join(title_parts)}" if title_parts else "Log Entry"

    # Build content
    content_parts = []

    if log.message:
        content_parts.append(f"Message: {log.message}")

    content_parts.append(f"Log Content:\n{log.content}")

    if log.context:
        import json

        content_parts.append(f"Context: {json.dumps(log.context, indent=2)}")

    content = "\n\n".join(content_parts)

    # Build tags
    tags = {
        "log_level": log.level,
        "log_format": log.log_format,
        "type": "log",
        **(log.metadata or {}),
    }

    return IngestDocument(
        doc_type="log",
        service=log.service,
        component=log.component,
        title=title,
        content=content,
        tags=tags,
        last_reviewed_at=log.timestamp,
    )


def normalize_json_data(data: Dict, doc_type: str) -> IngestDocument:
    """Normalize arbitrary JSON data to IngestDocument format."""
    # Extract common fields
    title = data.get("title") or data.get("name") or f"{doc_type.title()} Document"
    content = data.get("content") or data.get("description") or str(data)

    # Try to extract service/component
    service = data.get("service") or (
        data.get("labels", {}).get("service") if isinstance(data.get("labels"), dict) else None
    )
    component = data.get("component") or (
        data.get("labels", {}).get("component") if isinstance(data.get("labels"), dict) else None
    )

    # Build tags from all other fields
    tags = {
        k: v
        for k, v in data.items()
        if k not in ["title", "name", "content", "description", "service", "component", "labels"]
    }
    tags["type"] = doc_type

    return IngestDocument(
        doc_type=doc_type,
        service=service,
        component=component,
        title=title,
        content=content,
        tags=tags,
        last_reviewed_at=None,
    )
