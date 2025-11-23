"""Normalizers to convert various input formats to IngestDocument format."""
from typing import Dict, Optional
from datetime import datetime
from ingestion.models import IngestAlert, IngestIncident, IngestRunbook, IngestLog, IngestDocument


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
    
    # Build tags
    tags = {
        "alert_id": alert.alert_id,
        "source": alert.source,
        "severity": alert.severity,
        "type": "historical_alert",
        **(alert.metadata or {})
    }
    
    return IngestDocument(
        doc_type="alert",
        service=service,
        component=component,
        title=f"Alert: {alert.title}",
        content=content,
        tags=tags,
        last_reviewed_at=alert.ts
    )


def normalize_incident(incident: IngestIncident) -> IngestDocument:
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
        service = incident.affected_services[0]
    
    # Build tags
    tags = {
        "incident_id": incident.incident_id,
        "alert_id": incident.alert_id,
        "severity": incident.severity,
        "category": incident.category,
        "type": "historical_incident",
        **(incident.metadata or {})
    }
    
    return IngestDocument(
        doc_type="incident",
        service=service,
        component=None,  # Can be extracted from content if needed
        title=f"Incident: {incident.title}",
        content=content,
        tags=tags,
        last_reviewed_at=incident.timestamp
    )


def normalize_runbook(runbook: IngestRunbook) -> IngestDocument:
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
    
    # Build tags
    tags = {
        "type": "runbook",
        **(runbook.tags or {}),
        **(runbook.metadata or {})
    }
    
    return IngestDocument(
        doc_type="runbook",
        service=runbook.service,
        component=runbook.component,
        title=runbook.title,
        content=content,
        tags=tags,
        last_reviewed_at=None
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
        **(log.metadata or {})
    }
    
    return IngestDocument(
        doc_type="log",
        service=log.service,
        component=log.component,
        title=title,
        content=content,
        tags=tags,
        last_reviewed_at=log.timestamp
    )


def normalize_json_data(data: Dict, doc_type: str) -> IngestDocument:
    """Normalize arbitrary JSON data to IngestDocument format."""
    # Extract common fields
    title = data.get("title") or data.get("name") or f"{doc_type.title()} Document"
    content = data.get("content") or data.get("description") or str(data)
    
    # Try to extract service/component
    service = data.get("service") or (data.get("labels", {}).get("service") if isinstance(data.get("labels"), dict) else None)
    component = data.get("component") or (data.get("labels", {}).get("component") if isinstance(data.get("labels"), dict) else None)
    
    # Build tags from all other fields
    tags = {k: v for k, v in data.items() if k not in ["title", "name", "content", "description", "service", "component", "labels"]}
    tags["type"] = doc_type
    
    return IngestDocument(
        doc_type=doc_type,
        service=service,
        component=component,
        title=title,
        content=content,
        tags=tags,
        last_reviewed_at=None
    )

