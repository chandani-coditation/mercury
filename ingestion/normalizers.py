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

# Try to load service/component mapping config
try:
    project_root = Path(__file__).parent.parent
    mapping_path = project_root / "config" / "service_component_mapping.json"
    if mapping_path.exists():
        with open(mapping_path, "r") as f:
            SERVICE_COMPONENT_MAPPING = json.load(f)
    else:
        SERVICE_COMPONENT_MAPPING = {}
except Exception:
    SERVICE_COMPONENT_MAPPING = {}

# Try to load technical terms config
try:
    project_root = Path(__file__).parent.parent
    tech_terms_path = project_root / "config" / "technical_terms.json"
    if tech_terms_path.exists():
        with open(tech_terms_path, "r") as f:
            TECHNICAL_TERMS_CONFIG = json.load(f)
    else:
        TECHNICAL_TERMS_CONFIG = {"abbreviations": {}, "synonyms": {}, "normalization_rules": {}}
except Exception:
    TECHNICAL_TERMS_CONFIG = {"abbreviations": {}, "synonyms": {}, "normalization_rules": {}}

# Try to load extraction patterns config
try:
    project_root = Path(__file__).parent.parent
    extraction_patterns_path = project_root / "config" / "extraction_patterns.json"
    if extraction_patterns_path.exists():
        with open(extraction_patterns_path, "r") as f:
            EXTRACTION_PATTERNS_CONFIG = json.load(f)
    else:
        EXTRACTION_PATTERNS_CONFIG = {"error_code_patterns": [], "job_patterns": [], "id_patterns": [], "service_patterns": []}
except Exception:
    EXTRACTION_PATTERNS_CONFIG = {"error_code_patterns": [], "job_patterns": [], "id_patterns": [], "service_patterns": []}

# Try to load ingestion config
try:
    project_root = Path(__file__).parent.parent
    ingestion_config_path = project_root / "config" / "ingestion.json"
    if ingestion_config_path.exists():
        with open(ingestion_config_path, "r") as f:
            INGESTION_CONFIG = json.load(f)
    else:
        INGESTION_CONFIG = {"chunking": {}, "batch_sizes": {}, "formatting": {}}
except Exception:
    INGESTION_CONFIG = {"chunking": {}, "batch_sizes": {}, "formatting": {}}

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


def normalize_technical_terms(text: str) -> str:
    """
    Normalize technical terms in text during ingestion using config file.
    
    This standardizes terms like "DB" -> "Database" based on config mappings.
    All mappings come from config file, not LLM-generated.
    
    **Soft Rule**: This is an enhancement that gracefully degrades if config is missing
    or malformed. If normalization fails, returns original text unchanged.
    
    Args:
        text: Input text to normalize
    
    Returns:
        Normalized text (or original text if normalization fails)
    """
    if not text:
        return text
    
    try:
        abbreviations = TECHNICAL_TERMS_CONFIG.get("abbreviations", {})
        if not abbreviations:
            # No config available - return original text (graceful degradation)
            return text
        
        normalized_text = text
        
        # Apply abbreviation normalization
        for abbrev, expansion in abbreviations.items():
            try:
                # Create regex pattern for word boundary
                pattern = r'\b' + re.escape(abbrev) + r'\b'
                normalized_text = re.sub(pattern, expansion, normalized_text, flags=re.IGNORECASE)
            except Exception:
                # Skip this abbreviation if regex fails (graceful degradation)
                continue
        
        return normalized_text
    except Exception:
        # If any error occurs, return original text (graceful degradation)
        return text


def extract_structured_data(text: str) -> Dict[str, List[str]]:
    """
    Extract structured data (error codes, IDs, job names) from text.
    
    This is pattern-based extraction, not LLM generation.
    Extracts actual patterns from text for better matching.
    
    **Soft Rule**: This is an enhancement that gracefully degrades if extraction fails.
    If extraction fails, returns empty dict. Never breaks ingestion.
    
    Args:
        text: Input text to extract from
    
    Returns:
        Dictionary with extracted structured data (or empty dict if extraction fails)
    """
    extracted = {
        "error_codes": [],
        "job_names": [],
        "ids": [],
    }
    
    if not text:
        return extracted
    
    try:
        # Load patterns from config (centralized)
        error_code_patterns = EXTRACTION_PATTERNS_CONFIG.get("error_code_patterns", [])
        job_patterns = EXTRACTION_PATTERNS_CONFIG.get("job_patterns", [])
        id_patterns = EXTRACTION_PATTERNS_CONFIG.get("id_patterns", [])
        
        # Get error code prefix from config
        error_code_prefix = INGESTION_CONFIG.get("formatting", {}).get("error_code_prefix", "error")
        
        # Extract error codes (e.g., "Error 500", "SQLSTATE 23505", "HTTP 404")
        for pattern_str in error_code_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                matches = pattern.findall(text)
                extracted["error_codes"].extend([f"{error_code_prefix} {m}" for m in matches])
            except Exception:
                # Skip invalid pattern (graceful degradation)
                continue
        
        # Extract job/process names (quoted strings, capitalized words after "job", "process", "task")
        for pattern_str in job_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                matches = pattern.findall(text)
                extracted["job_names"].extend(matches)
            except Exception:
                # Skip invalid pattern (graceful degradation)
                continue
        
        # Extract IDs (UUIDs, numeric IDs, alphanumeric IDs)
        for pattern_str in id_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                matches = pattern.findall(text)
                extracted["ids"].extend(matches)
            except Exception:
                # Skip invalid pattern (graceful degradation)
                continue
        
        # Remove duplicates
        extracted["error_codes"] = list(set(extracted["error_codes"]))
        extracted["job_names"] = list(set(extracted["job_names"]))
        extracted["ids"] = list(set(extracted["ids"]))
        
        return extracted
    except Exception:
        # If extraction fails, return empty dict (graceful degradation)
        return {
            "error_codes": [],
            "job_names": [],
            "ids": [],
        }


def normalize_alert(alert: IngestAlert) -> IngestDocument:
    """Convert historical alert to IngestDocument format."""
    # Extract service/component from labels
    service = alert.labels.get("service") if alert.labels else None
    component = alert.labels.get("component") if alert.labels else None

    # Build content from alert fields
    # Apply technical term normalization to improve matching consistency (soft rule - graceful degradation)
    try:
        normalized_title = normalize_technical_terms(alert.title)
        normalized_description = normalize_technical_terms(alert.description)
    except Exception:
        # If normalization fails, use original text (graceful degradation)
        normalized_title = alert.title
        normalized_description = alert.description
    
    content_parts = [
        f"Alert: {normalized_title}",
        f"Description: {normalized_description}",
    ]

    if alert.resolution_status:
        content_parts.append(f"Resolution Status: {alert.resolution_status}")

    if alert.resolution_notes:
        try:
            normalized_notes = normalize_technical_terms(alert.resolution_notes)
        except Exception:
            normalized_notes = alert.resolution_notes  # Graceful degradation
        content_parts.append(f"Resolution Notes: {normalized_notes}")

    if alert.labels:
        content_parts.append(f"Labels: {', '.join(f'{k}={v}' for k, v in alert.labels.items())}")

    content = "\n\n".join(content_parts)
    
    # Extract structured data for metadata (error codes, IDs, job names)
    structured_data = extract_structured_data(content)
    if structured_data["error_codes"] or structured_data["job_names"] or structured_data["ids"]:
        # Add to metadata for better matching
        if "metadata" not in (alert.metadata or {}):
            alert.metadata = alert.metadata or {}
        alert.metadata["structured_data"] = structured_data

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

    # PHASE 2: Normalize service/component using mapping configuration
    normalized_service, normalized_component = normalize_service_component(service, component)
    
    # Extract structured data for metadata (error codes, IDs, job names)
    structured_data = extract_structured_data(content)
    if structured_data["error_codes"] or structured_data["job_names"] or structured_data["ids"]:
        # Add to tags for better matching
        tags["structured_data"] = structured_data
    
    return IngestDocument(
        doc_type="alert",
        service=normalized_service,
        component=normalized_component,
        title=f"Alert: {normalized_title}",  # Use normalized title
        content=content,
        tags=tags,
        last_reviewed_at=alert.ts,
    )


def extract_runbook_steps(
    runbook: IngestRunbook, 
    runbook_id: str,
    normalized_service: Optional[str] = None,
    normalized_component: Optional[str] = None
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
        runbook_id = (
            runbook.tags.get("runbook_id") if runbook.tags else f"RB-{uuid.uuid4().hex[:8].upper()}"
        )

    # Log extraction attempt
    try:
        from ai_service.core import get_logger

        logger = get_logger(__name__)
        has_steps = runbook.steps is not None
        steps_count = len(runbook.steps) if isinstance(runbook.steps, list) else 0
        content_len = len(runbook.content) if runbook.content else 0
        logger.info(
            f"Extracting steps from runbook {runbook.title}. Has steps list: {has_steps}, Steps count: {steps_count}, Content length: {content_len}"
        )
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

            # Parse remediation steps that may be in format "Problem: Solution" or "Problem: Action"
            # Example: "Connection saturation: Kill idle sessions, increase max_connections if safe."
            if ":" in step_text and len(step_text.split(":")) == 2:
                parts = step_text.split(":", 1)
                condition = parts[0].strip()  # Problem/condition
                action = parts[1].strip()  # Remediation action
                # Apply technical term normalization to action text (from historical data)
                action = normalize_technical_terms(action)

            # Try to extract condition if present (e.g., "If X, then Y")
            elif "if" in step_text.lower() or "when" in step_text.lower():
                # Simple heuristic: split on "then" or "do"
                parts = re.split(r"\s+then\s+|\s+do\s+", step_text, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    condition = parts[0].strip()
                    action = parts[1].strip()
                    # Apply technical term normalization to action text (from historical data)
                    action = normalize_technical_terms(action)
            
            # Normalize action text if it wasn't parsed above
            if action == step_text:
                action = normalize_technical_terms(action)

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
                    risk_level=None,  # Removed: risk_level is not based on historical data
                    service=normalized_service or runbook.service,
                    component=normalized_component or runbook.component,
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
                paragraphs = [
                    p.strip() for p in content.split("\n\n") if p.strip() and len(p.strip()) > 20
                ]
                if paragraphs:
                    found_steps = paragraphs
                else:
                    # If no paragraphs, split by single newlines
                    lines = [
                        line.strip()
                        for line in content.split("\n")
                        if line.strip() and len(line.strip()) > 20
                    ]
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
                        rollback = (
                            "\n".join(rollback_steps)
                            if isinstance(rollback_steps, list)
                            else str(rollback_steps)
                        )
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
                    service=normalized_service or runbook.service,
                    component=normalized_component or runbook.component,
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
                action=runbook.content.strip()[:INGESTION_CONFIG.get("formatting", {}).get("max_fallback_title_length", 1000)],  # Limit from config
                expected_outcome=None,
                rollback=None,
                risk_level=None,
                service=normalized_service or runbook.service,
                component=normalized_component or runbook.component,
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
        logger.info(
            f"Extracted {len(steps)} steps from runbook {runbook.title} (runbook_id: {runbook_id})"
        )
    except:
        pass

    return steps


def validate_service_component_value(value: Optional[str], field_name: str) -> Optional[str]:
    """
    Validate and normalize a service/component value.
    
    Args:
        value: Raw value to validate
        field_name: Name of field (for logging) - "service" or "component"
    
    Returns:
        Validated and normalized value, or None if invalid
    """
    if value is None:
        return None
    
    # Convert to string if not already
    if not isinstance(value, str):
        value = str(value)
    
    # Trim whitespace
    value = value.strip()
    
    # Check for empty string after trimming
    if not value:
        return None
    
    # Validate length (reasonable limits)
    if len(value) > 100:
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.warning(f"{field_name} value too long ({len(value)} chars), truncating: {value[:50]}...")
        except:
            pass
        value = value[:100].strip()
    
    # Check for invalid characters (allow alphanumeric, spaces, hyphens, underscores, dots)
    # Remove any control characters
    import re
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
    
    # Warn about suspicious patterns (but don't reject)
    if re.search(r'[<>{}[\]\\|`~!@#$%^&*()+=\'"]', value):
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.warning(f"{field_name} contains special characters (may cause issues): {value}")
        except:
            pass
    
    return value


def normalize_service_component(service: Optional[str], component: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize and validate service/component values using mapping configuration.
    
    PHASE 2: Standardizes service/component values during ingestion to ensure consistency
    between runbooks and incidents. Uses aliases from service_component_mapping.json.
    
    TASK #9: Added validation for service/component values:
    - Trims whitespace
    - Handles None values
    - Validates format (length, special characters)
    - Logs validation warnings
    
    Args:
        service: Raw service value (may be None)
        component: Raw component value (may be None)
    
    Returns:
        Tuple of (normalized_service, normalized_component)
        - If mapping exists, returns canonical value
        - If no mapping, returns validated original value (or None)
        - If component maps to null, returns None for component
    """
    # TASK #9: Validate service/component values first
    validated_service = validate_service_component_value(service, "service")
    validated_component = validate_service_component_value(component, "component")
    
    if not SERVICE_COMPONENT_MAPPING:
        # No mapping config available, return validated values
        return validated_service, validated_component
    
    service_aliases = SERVICE_COMPONENT_MAPPING.get("service_aliases", {})
    component_aliases = SERVICE_COMPONENT_MAPPING.get("component_aliases", {})
    
    normalized_service = validated_service
    normalized_component = validated_component
    
    # Normalize service
    if validated_service and validated_service in service_aliases:
        normalized_service = service_aliases[validated_service]
    elif validated_service:
        # Try case-insensitive match
        service_lower = validated_service.lower()
        for alias, canonical in service_aliases.items():
            if alias.lower() == service_lower:
                normalized_service = canonical
                break
    
    # Normalize component
    if validated_component and validated_component in component_aliases:
        mapped_value = component_aliases[validated_component]
        # If mapped to null, remove component
        normalized_component = None if mapped_value is None else mapped_value
    elif validated_component:
        # Try case-insensitive match
        component_lower = validated_component.lower()
        for alias, canonical in component_aliases.items():
            if alias.lower() == component_lower:
                normalized_component = None if canonical is None else canonical
                break
    
    return normalized_service, normalized_component


def _extract_service_component(
    incident: IngestIncident, failure_type: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract service and component deterministically from incident data.

    Rules:
    1. Service: From affected_services[0] if available, split on '-' if present
    2. Component: Derived from failure_type and incident metadata, not keyword guessing
    """
    service = None
    component = None

    # Extract service from affected_services
    if incident.affected_services and len(incident.affected_services) > 0:
        raw_service = incident.affected_services[0]
        if "-" in raw_service:
            service = raw_service.split("-")[0].strip()
        else:
            service = raw_service

    # Extract component deterministically based on failure_type and metadata
    # This is rule-based, not keyword-based
    if failure_type == "SQL_AGENT_JOB_FAILURE" or failure_type == "DATABASE_FAILURE":
        component = "Database"
    elif failure_type == "STORAGE_FAILURE":
        component = None  # Storage signatures don't have component (per existing data)
    elif failure_type == "CONNECTION_FAILURE" or failure_type == "TIMEOUT_FAILURE":
        component = "Network"
    elif failure_type == "PERFORMANCE_FAILURE":
        # Component can be determined from error_class if available
        # But for now, leave as None to match existing behavior
        component = None
    elif failure_type == "OPERATING_SYSTEM_FAILURE":
        component = "Operating System"
    elif failure_type == "AUTHENTICATION_FAILURE":
        component = "Security"

    return service, component


def create_incident_signature(incident: IngestIncident) -> IncidentSignature:
    """
    Convert incident to incident signature (pattern, not raw text).

    Per architecture: Signatures represent patterns, not stories.
    Uses rule-based, deterministic classification with CSV-driven rules.

    Returns:
        IncidentSignature object
    """
    from ingestion.classification import get_classifier

    # Get rule-based classifier
    classifier = get_classifier()

    # Step 1: Classify failure_type using rules (deterministic)
    failure_type = classifier.classify_failure_type(incident)

    # Step 2: Classify error_class using rules (deterministic, depends on failure_type)
    error_class = classifier.classify_error_class(incident, failure_type)

    # Step 3: Generate deterministic signature ID (hash-based)
    sig_id = classifier.generate_signature_id(incident, failure_type, error_class)

    # Step 4: Normalize symptoms using controlled vocabulary (deterministic)
    symptoms = classifier.normalize_symptoms(incident)

    # Extract affected service
    affected_service = None
    if incident.affected_services and len(incident.affected_services) > 0:
        affected_service = incident.affected_services[0]

    # Step 5: Extract service/component (deterministic parsing)
    service, component = _extract_service_component(incident, failure_type)
    
    # PHASE 2: Normalize service/component using mapping configuration
    service, component = normalize_service_component(service, component)

    # Resolution refs will be populated later when linking to runbook steps
    resolution_refs = None

    # Extract assignment_group from metadata if available
    assignment_group = None
    if incident.metadata and isinstance(incident.metadata, dict):
        assignment_group = incident.metadata.get("assignment_group")
    # Also check tags if not in metadata (for backward compatibility)
    if not assignment_group and hasattr(incident, "tags") and isinstance(incident.tags, dict):
        assignment_group = incident.tags.get("assignment_group")
    # Also check if it's in the incident directly (for IngestIncident from CSV)
    if not assignment_group and hasattr(incident, "assignment_group"):
        assignment_group = getattr(incident, "assignment_group", None)

    # Extract impact and urgency from metadata if available
    impact = None
    urgency = None
    close_notes = None
    if incident.metadata and isinstance(incident.metadata, dict):
        impact = incident.metadata.get("impact")
        urgency = incident.metadata.get("urgency")
        close_notes = incident.metadata.get("close_notes")
    # Also check tags if not in metadata (for backward compatibility)
    if not impact and hasattr(incident, "tags") and isinstance(incident.tags, dict):
        impact = incident.tags.get("impact")
    if not urgency and hasattr(incident, "tags") and isinstance(incident.tags, dict):
        urgency = incident.tags.get("urgency")
    if not close_notes and hasattr(incident, "tags") and isinstance(incident.tags, dict):
        close_notes = incident.tags.get("close_notes")
    # Also check if they're in the incident directly (for IngestIncident from CSV)
    if not impact and hasattr(incident, "impact"):
        impact = getattr(incident, "impact", None)
    if not urgency and hasattr(incident, "urgency"):
        urgency = getattr(incident, "urgency", None)
    if not close_notes and hasattr(incident, "close_notes"):
        close_notes = getattr(incident, "close_notes", None)

    return IncidentSignature(
        incident_signature_id=sig_id,
        failure_type=failure_type,
        error_class=error_class,
        symptoms=symptoms[:5] if symptoms else ["unknown symptoms"],  # Limit to 5 symptoms
        affected_service=affected_service,
        resolution_refs=resolution_refs,
        service=service,
        component=component,
        assignment_group=assignment_group,
        impact=impact,
        urgency=urgency,
        close_notes=close_notes,
    )


def normalize_incident(
    incident: IngestIncident, validate_schema: bool = False
) -> Tuple[Optional[IngestDocument], IncidentSignature]:
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


def normalize_runbook(
    runbook: IngestRunbook, validate_schema: bool = False
) -> Tuple[IngestDocument, List[RunbookStep]]:
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

    # PHASE 2: Normalize service/component FIRST, then use normalized values for steps
    normalized_service, normalized_component = normalize_service_component(
        runbook.service, runbook.component
    )
    
    # Extract atomic steps (will use normalized service/component)
    steps = extract_runbook_steps(runbook, runbook_id, normalized_service, normalized_component)

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
        "service": normalized_service,  # Use normalized service
        "component": normalized_component,  # Use normalized component
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
        service=normalized_service,
        component=normalized_component,
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
