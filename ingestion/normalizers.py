"""Normalizers to convert various input formats to IngestDocument format."""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from ingestion.models import (
    IngestAlert,
    IngestIncident,
    IngestRunbook,
    IngestLog,
    IngestDocument,
    RunbookStep,
    IncidentSignature,
)

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


def extract_runbook_steps(
    runbook: IngestRunbook, runbook_id: str
) -> List[RunbookStep]:
    """
    Extract atomic runbook steps from runbook content.
    
    Per architecture: Each step is stored independently with:
    - step_id, runbook_id, condition, action, expected_outcome, rollback, risk_level
    
    Returns:
        List of RunbookStep objects
    """
    steps = []
    
    # Generate runbook_id if not provided
    if not runbook_id:
        # Try to extract from tags or generate one
        runbook_id = runbook.tags.get("runbook_id") if runbook.tags else f"RB-{uuid.uuid4().hex[:8].upper()}"
    
    # Log extraction attempt
    try:
        from ai_service.core import get_logger
        logger = get_logger(__name__)
        has_steps = runbook.steps is not None
        steps_count = len(runbook.steps) if isinstance(runbook.steps, list) else 0
        content_len = len(runbook.content) if runbook.content else 0
        logger.info(f"Extracting steps from runbook {runbook.title}. Has steps list: {has_steps}, Steps count: {steps_count}, Content length: {content_len}")
    except:
        pass
    
    # If structured steps are provided, use them
    if runbook.steps and isinstance(runbook.steps, list) and len(runbook.steps) > 0:
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.debug(f"Using {len(runbook.steps)} structured steps from runbook.steps")
        except:
            pass
        for idx, step_text in enumerate(runbook.steps, 1):
            step_id = f"{runbook_id}-S{idx}"
            
            # Try to parse structured step format
            # Look for patterns like "Condition: ... Action: ..." or similar
            condition = None
            action = step_text
            expected_outcome = None
            rollback = None
            risk_level = None
            
            # Try to extract condition if present (e.g., "If X, then Y")
            if "if" in step_text.lower() or "when" in step_text.lower():
                # Simple heuristic: split on "then" or "do"
                parts = re.split(r"\s+then\s+|\s+do\s+", step_text, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    condition = parts[0].strip()
                    action = parts[1].strip()
            
            # Extract rollback from rollback_procedures if available
            if runbook.rollback_procedures:
                if isinstance(runbook.rollback_procedures, dict):
                    rollback = runbook.rollback_procedures.get("steps", [])
                    if isinstance(rollback, list):
                        rollback = "\n".join(rollback) if rollback else None
                else:
                    rollback = runbook.rollback_procedures
            
            steps.append(
                RunbookStep(
                    step_id=step_id,
                    runbook_id=runbook_id,
                    condition=condition or f"Step {idx} applies",
                    action=action,
                    expected_outcome=expected_outcome,
                    rollback=rollback,
                    risk_level=risk_level,
                    service=runbook.service,
                    component=runbook.component,
                )
            )
    else:
        # Parse unstructured content to extract steps
        # Look for numbered lists, bullet points, or step markers
        content = runbook.content
        
        # Try multiple strategies to extract steps
        found_steps = []
        
        # Strategy 1: Numbered lists (1., 2., 3., etc.)
        numbered_pattern = r"(?i)^\s*(\d+)[\.\)]\s+(.+?)(?=\n\s*\d+[\.\)]|\n\n\n|\Z)"
        matches = re.finditer(numbered_pattern, content, re.MULTILINE | re.DOTALL)
        for match in matches:
            step_text = match.group(2).strip()
            if step_text and len(step_text) > 5:
                found_steps.append(step_text)
        
        # Strategy 2: "Step N:" or "Step N." patterns
        if not found_steps:
            step_pattern = r"(?i)^\s*step\s+(\d+)[:\.]\s+(.+?)(?=\n\s*step\s+\d+|$)"
            matches = re.finditer(step_pattern, content, re.MULTILINE | re.DOTALL)
            for match in matches:
                step_text = match.group(2).strip()
                if step_text and len(step_text) > 5:
                    found_steps.append(step_text)
        
        # Strategy 3: Bullet points (- or *)
        if not found_steps:
            bullet_pattern = r"(?i)^\s*[-*•]\s+(.+?)(?=\n\s*[-*•]|\n\n|\Z)"
            matches = re.finditer(bullet_pattern, content, re.MULTILINE | re.DOTALL)
            for match in matches:
                step_text = match.group(1).strip()
                if step_text and len(step_text) > 5:
                    found_steps.append(step_text)
        
        # Strategy 4: Split by double newlines (paragraphs)
        if not found_steps:
            paragraphs = re.split(r"\n\s*\n+", content)
            for para in paragraphs:
                para = para.strip()
                if para and len(para) > 20:  # Only meaningful paragraphs
                    found_steps.append(para)
        
        # Strategy 5: Split by single newlines if content is structured
        if not found_steps and "\n" in content:
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            # Group consecutive non-empty lines as steps
            current_step = []
            for line in lines:
                if len(line) > 10:  # Meaningful line
                    current_step.append(line)
                elif current_step:
                    found_steps.append(" ".join(current_step))
                    current_step = []
            if current_step:
                found_steps.append(" ".join(current_step))
        
        # Last resort: treat entire content as one step (but log a warning)
        if not found_steps:
            if content and content.strip():
                # Split content into paragraphs and treat each as a step
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip() and len(p.strip()) > 20]
                if paragraphs:
                    found_steps = paragraphs
                else:
                    # If no paragraphs, split by single newlines
                    lines = [line.strip() for line in content.split("\n") if line.strip() and len(line.strip()) > 20]
                    if lines:
                        found_steps = lines
                    else:
                        # Absolute last resort: use entire content
                        found_steps = [content.strip()]
                try:
                    from ai_service.core import get_logger
                    logger = get_logger(__name__)
                    logger.warning(
                        f"Could not extract structured steps from runbook {runbook_id}. "
                        f"Using {len(found_steps)} paragraph(s) as steps. Content length: {len(content)}"
                    )
                except:
                    pass
            else:
                try:
                    from ai_service.core import get_logger
                    logger = get_logger(__name__)
                    logger.error(f"Runbook {runbook_id} has no content to extract steps from!")
                except:
                    pass
        
        # Create RunbookStep objects
        for idx, step_text in enumerate(found_steps, 1):
            step_id = f"{runbook_id}-S{idx}"
            
            # Extract condition and action if possible
            condition = None
            action = step_text
            
            if "if" in step_text.lower() or "when" in step_text.lower():
                parts = re.split(r"\s+then\s+|\s+do\s+", step_text, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    condition = parts[0].strip()
                    action = parts[1].strip()
            
            # Handle rollback procedures
            rollback = None
            if runbook.rollback_procedures:
                if isinstance(runbook.rollback_procedures, dict):
                    rollback_steps = runbook.rollback_procedures.get("steps", [])
                    if rollback_steps:
                        rollback = "\n".join(rollback_steps) if isinstance(rollback_steps, list) else str(rollback_steps)
                else:
                    rollback = str(runbook.rollback_procedures)
            
            steps.append(
                RunbookStep(
                    step_id=step_id,
                    runbook_id=runbook_id,
                    condition=condition or f"Step {idx} applies",
                    action=action,
                    expected_outcome=None,
                    rollback=rollback,
                    risk_level=None,
                    service=runbook.service,
                    component=runbook.component,
                )
            )
    
    # Ensure we have at least one step if there's any content
    if len(steps) == 0 and runbook.content and runbook.content.strip():
        # Create a single step from the entire content as absolute last resort
        step_id = f"{runbook_id}-S1"
        steps.append(
            RunbookStep(
                step_id=step_id,
                runbook_id=runbook_id,
                condition="Runbook applies",
                action=runbook.content.strip()[:1000],  # Limit to 1000 chars
                expected_outcome=None,
                rollback=None,
                risk_level=None,
                service=runbook.service,
                component=runbook.component,
            )
        )
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.warning(
                f"Created single fallback step for runbook {runbook.title} "
                f"because no steps could be extracted. Content length: {len(runbook.content)}"
            )
        except:
            pass
    
    # Log final result
    try:
        from ai_service.core import get_logger
        logger = get_logger(__name__)
        logger.info(f"Extracted {len(steps)} steps from runbook {runbook.title} (runbook_id: {runbook_id})")
    except:
        pass
    
    return steps


def create_incident_signature(incident: IngestIncident) -> IncidentSignature:
    """
    Convert incident to incident signature (pattern, not raw text).
    
    Per architecture: Signatures represent patterns, not stories.
    Contains: failure_type, error_class, symptoms, affected_service, resolution_refs
    
    Returns:
        IncidentSignature object
    """
    # Generate signature ID
    sig_id = f"SIG-{uuid.uuid4().hex[:8].upper()}"
    if incident.incident_id:
        # Use part of incident_id if available
        sig_id = f"SIG-{incident.incident_id[:8].upper()}"
    
    # Extract failure type from title, description, or category
    failure_type = incident.category or "UNKNOWN_FAILURE"
    if "sql" in (incident.title + " " + (incident.description or "")).lower():
        failure_type = "SQL_AGENT_JOB_FAILURE"
    elif "database" in (incident.title + " " + (incident.description or "")).lower():
        failure_type = "DATABASE_FAILURE"
    elif "connection" in (incident.title + " " + (incident.description or "")).lower():
        failure_type = "CONNECTION_FAILURE"
    elif "timeout" in (incident.title + " " + (incident.description or "")).lower():
        failure_type = "TIMEOUT_FAILURE"
    elif "authentication" in (incident.title + " " + (incident.description or "")).lower():
        failure_type = "AUTHENTICATION_FAILURE"
    
    # Extract error class from root_cause or description
    error_class = "UNKNOWN_ERROR"
    search_text = (incident.root_cause or "") + " " + (incident.description or "")
    search_lower = search_text.lower()
    
    if "service account" in search_lower and "disabled" in search_lower:
        error_class = "SERVICE_ACCOUNT_DISABLED"
    elif "permission" in search_lower or "access denied" in search_lower:
        error_class = "PERMISSION_DENIED"
    elif "timeout" in search_lower:
        error_class = "TIMEOUT_ERROR"
    elif "connection" in search_lower and "failed" in search_lower:
        error_class = "CONNECTION_FAILED"
    elif "authentication" in search_lower:
        error_class = "AUTHENTICATION_ERROR"
    
    # Extract symptoms from description and title
    symptoms = []
    symptom_text = (incident.title or "") + " " + (incident.description or "")
    
    # Common symptom patterns
    symptom_patterns = [
        r"(\w+\s+)?(failed|failure|error|timeout|disconnected)",
        r"(\w+\s+)?(unable to|cannot|could not)",
        r"(\w+\s+)?(authentication|authorization|permission)",
    ]
    
    for pattern in symptom_patterns:
        matches = re.finditer(pattern, symptom_text, re.IGNORECASE)
        for match in matches:
            symptom = match.group(0).strip()
            if symptom and symptom not in symptoms:
                symptoms.append(symptom.lower())
    
    # If no symptoms found, use key phrases from description
    if not symptoms:
        # Split description into phrases
        phrases = re.split(r"[.!?]\s+", incident.description or "")
        symptoms = [p.strip().lower()[:50] for p in phrases[:3] if p.strip()]
    
    # Extract affected service
    affected_service = None
    if incident.affected_services and len(incident.affected_services) > 0:
        affected_service = incident.affected_services[0]
    
    # Extract service/component for signature
    service = None
    component = None
    if incident.affected_services and len(incident.affected_services) > 0:
        raw_service = incident.affected_services[0]
        if "-" in raw_service:
            service = raw_service.split("-")[0].strip()
        else:
            service = raw_service
    
    search_text = f"{incident.title} {incident.description or ''} {incident.category or ''}".lower()
    if "database" in search_text or "sql" in search_text or "db" in search_text:
        component = "Database"
    elif "network" in search_text:
        component = "Network"
    elif "disk" in search_text or "storage" in search_text:
        component = "Disk"
    elif "memory" in search_text:
        component = "Memory"
    elif "cpu" in search_text:
        component = "CPU"
    
    # Resolution refs will be populated later when linking to runbook steps
    resolution_refs = None
    
    return IncidentSignature(
        incident_signature_id=sig_id,
        failure_type=failure_type,
        error_class=error_class,
        symptoms=symptoms[:5] if symptoms else ["unknown symptoms"],  # Limit to 5 symptoms
        affected_service=affected_service,
        resolution_refs=resolution_refs,
        service=service,
        component=component,
    )


def normalize_incident(incident: IngestIncident, validate_schema: bool = False) -> Tuple[Optional[IngestDocument], IncidentSignature]:
    """
    Convert historical incident to incident signature.
    
    Per architecture: Incidents are converted to signatures (patterns, not raw text).
    Returns a minimal document (for metadata) and the signature.
    
    Returns:
        Tuple of (Optional[IngestDocument] for metadata, IncidentSignature)
    """
    # Create incident signature (primary output)
    signature = create_incident_signature(incident)
    
    # Optional JSON schema validation
    if validate_schema:
        incident_dict = incident.model_dump(mode="json", exclude_none=True)
        is_valid, errors = _validate_with_schema(incident_dict, "incident")
        if not is_valid:
            from ai_service.core import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Incident schema validation warnings: {errors}")
    
    # Create minimal document for metadata (optional - signature is primary)
    # The signature will be stored as a chunk, not as document content
    doc = IngestDocument(
        doc_type="incident_signature",
        service=signature.service,
        component=signature.component,
        title=f"Incident Signature: {signature.incident_signature_id}",
        content="",  # Empty - signature data is in the chunk, not here
        tags={
            "type": "incident_signature",
            "incident_signature_id": signature.incident_signature_id,
            "incident_id": incident.incident_id,
            "failure_type": signature.failure_type,
            "error_class": signature.error_class,
            "affected_service": signature.affected_service,
        },
        last_reviewed_at=incident.timestamp,
    )
    
    return doc, signature


def normalize_runbook(runbook: IngestRunbook, validate_schema: bool = False) -> Tuple[IngestDocument, List[RunbookStep]]:
    """
    Convert runbook to IngestDocument format and extract atomic steps.
    
    Per architecture: Runbook metadata goes in documents table,
    and each step is stored as an atomic chunk.
    
    Returns:
        Tuple of (IngestDocument for metadata, List[RunbookStep] for atomic steps)
    """
    # Extract runbook_id
    runbook_id = runbook.tags.get("runbook_id") if runbook.tags else None
    if not runbook_id:
        # Generate a runbook_id if not provided
        runbook_id = f"RB-{uuid.uuid4().hex[:8].upper()}"
    
    # Extract atomic steps
    steps = extract_runbook_steps(runbook, runbook_id)
    
    # Build metadata content (for document table - not for embedding)
    # This is just metadata, not the actual steps
    content_parts = [f"Runbook: {runbook.title}"]
    
    if runbook.prerequisites:
        prereq_text = "\n".join(f"- {p}" for p in runbook.prerequisites)
        content_parts.append(f"Prerequisites:\n{prereq_text}")
    
    # Note: Steps are NOT included in content - they are stored separately as chunks
    content = "\n\n".join(content_parts)

    # Build comprehensive tags (mandatory fields from specification)
    tags = {
        "type": "runbook",
        "runbook_id": runbook_id,
        "service": runbook.service,
        "component": runbook.component,
        "env": None,  # Environment (can be extracted from metadata if available)
        "risk": None,  # Risk level (can be extracted from content if available)
        "last_reviewed_at": None,  # Can be extracted from metadata if available
        "failure_types": runbook.tags.get("failure_types") if runbook.tags else None,
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

    doc = IngestDocument(
        doc_type="runbook",
        service=runbook.service,
        component=runbook.component,
        title=runbook.title,
        content=content,  # Metadata only - steps stored separately
        tags=tags,
        last_reviewed_at=None,
    )
    
    return doc, steps


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
