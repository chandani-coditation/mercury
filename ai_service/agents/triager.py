"""Triager Agent - Analyzes and triages alerts."""

from datetime import datetime
from typing import Dict, Any, Optional, List
from ai_service.llm_client import call_llm_for_triage
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import (
    validate_triage_output,
    validate_triage_no_hallucination,
    validate_triage_retrieval_boundaries,
)
from ai_service.core import get_retrieval_config, get_workflow_config, get_logger, load_config
from retrieval.hybrid_search import triage_retrieval

logger = get_logger(__name__)


def derive_severity_from_impact_urgency(impact: str, urgency: str) -> str:
    """Derive severity from impact and urgency using config mapping."""
    try:
        config = load_config()
        severity_mapping = config.get("field_mappings", {}).get("severity_mapping", {})
        mapping = severity_mapping.get("impact_urgency_to_severity", {})
        default = severity_mapping.get("default_severity", "medium")
        
        # Extract numeric values (e.g., "3 - Low" -> "3")
        impact_val = impact.split()[0] if impact and isinstance(impact, str) else "3"
        urgency_val = urgency.split()[0] if urgency and isinstance(urgency, str) else "3"
        
        # Create key (e.g., "3-3")
        key = f"{impact_val}-{urgency_val}"
        
        # Look up in mapping
        severity = mapping.get(key, default)
        return severity
    except Exception as e:
        logger.warning(f"Error deriving severity from impact/urgency: {e}. Using default 'medium'")
        return "medium"


def extract_routing_from_alert(alert: Dict[str, Any]) -> Optional[str]:
    """Extract routing (assignment_group) from alert labels."""
    labels = alert.get("labels", {})
    routing = labels.get("assignment_group") or labels.get("routing")
    return routing


def predict_routing_from_evidence(incident_signatures: List[Dict[str, Any]]) -> Optional[str]:
    """
    Predict routing (assignment_group) from matched incident signatures.
    
    Uses the most common assignment_group from historical incident signatures.
    This is the primary method - alert labels are only used as fallback.
    
    Args:
        incident_signatures: List of retrieved incident signature chunks with metadata
        
    Returns:
        Most common assignment_group from signatures, or None if none found
    """
    if not incident_signatures:
        logger.debug("No incident signatures provided for routing prediction")
        return None
    
    assignment_groups = []
    for sig in incident_signatures:
        metadata = sig.get("metadata", {})
        assignment_group = metadata.get("assignment_group")
        logger.debug(f"Checking signature {sig.get('incident_signature_id', 'unknown')}: assignment_group={assignment_group}, metadata keys={list(metadata.keys())}")
        if assignment_group and str(assignment_group).strip():
            assignment_groups.append(str(assignment_group).strip())
    
    if not assignment_groups:
        logger.warning(f"No assignment_group found in {len(incident_signatures)} incident signatures. Available metadata keys: {[list(sig.get('metadata', {}).keys()) for sig in incident_signatures[:2]]}")
        return None
    
    # Return the most common assignment_group
    from collections import Counter
    counter = Counter(assignment_groups)
    most_common = counter.most_common(1)
    if most_common:
        routing = most_common[0][0]
        logger.info(f"Predicted routing from {len(assignment_groups)} signatures: {routing} (appeared {most_common[0][1]} times)")
        return routing
    
    return None


def predict_impact_urgency_from_evidence(incident_signatures: List[Dict[str, Any]]) -> Optional[tuple[str, str]]:
    """
    Predict impact and urgency from matched incident signatures.
    
    Uses the most common impact/urgency combination from historical incident signatures.
    This is the primary method - alert labels are only used as fallback.
    
    Args:
        incident_signatures: List of retrieved incident signature chunks with metadata
        
    Returns:
        Tuple of (impact, urgency) or None if none found
    """
    if not incident_signatures:
        logger.debug("No incident signatures provided for impact/urgency prediction")
        return None
    
    impact_urgency_pairs = []
    for sig in incident_signatures:
        metadata = sig.get("metadata", {})
        impact = metadata.get("impact")
        urgency = metadata.get("urgency")
        logger.debug(f"Checking signature {sig.get('incident_signature_id', 'unknown')}: impact={impact}, urgency={urgency}")
        if impact and urgency:
            impact_urgency_pairs.append((str(impact).strip(), str(urgency).strip()))
    
    if not impact_urgency_pairs:
        logger.warning(f"No impact/urgency found in {len(incident_signatures)} incident signatures. Available metadata keys: {[list(sig.get('metadata', {}).keys()) for sig in incident_signatures[:2]]}")
        return None
    
    # Find the most common impact/urgency combination
    from collections import Counter
    counter = Counter(impact_urgency_pairs)
    most_common = counter.most_common(1)
    if most_common:
        impact, urgency = most_common[0][0]
        logger.info(
            f"Predicted impact/urgency from {len(impact_urgency_pairs)} signatures: "
            f"impact={impact}, urgency={urgency} "
            f"(appeared {most_common[0][1]} times)"
        )
        return (impact, urgency)
    
    return None


def predict_severity_from_evidence(incident_signatures: List[Dict[str, Any]]) -> Optional[str]:
    """
    Predict severity from matched incident signatures based on impact/urgency.
    
    Uses the most common impact/urgency combination from historical incident signatures
    to derive severity. This is the primary method - alert labels are only used as fallback.
    
    Args:
        incident_signatures: List of retrieved incident signature chunks with metadata
        
    Returns:
        Predicted severity (critical, high, medium, low) or None if none found
    """
    impact_urgency = predict_impact_urgency_from_evidence(incident_signatures)
    if impact_urgency:
        impact, urgency = impact_urgency
        severity = derive_severity_from_impact_urgency(impact, urgency)
        logger.info(f"Derived severity from predicted impact/urgency: {impact}/{urgency} -> {severity}")
        return severity
    
    return None


def format_evidence_chunks(
    context_chunks: list, retrieval_method: str = "hybrid_search", retrieval_params: dict = None
) -> dict:
    """Format evidence chunks for storage with provenance fields."""
    formatted = {
        "chunks_used": len(context_chunks),
        "chunk_ids": [chunk.get("chunk_id") for chunk in context_chunks],
        "chunk_sources": [chunk.get("doc_title") for chunk in context_chunks],
        "chunks": [],
        "retrieval_method": retrieval_method,
        "retrieval_params": retrieval_params or {},
    }
    type_counts = {}
    for chunk in context_chunks:
        metadata = chunk.get("metadata") or {}
        source_type = (
            chunk.get("doc_type") or metadata.get("doc_type") or metadata.get("source_type")
        )
        if source_type:
            type_counts[source_type] = type_counts.get(source_type, 0) + 1
        formatted["chunks"].append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "doc_title": chunk.get("doc_title"),
                "content": chunk.get("content", "")[:500],
                "provenance": {
                    "source_type": source_type,
                    "source_id": chunk.get("document_id"),
                    "service": metadata.get("service"),
                    "component": metadata.get("component"),
                },
                "metadata": metadata,
                "scores": {
                    "vector_score": chunk.get("vector_score"),
                    "fulltext_score": chunk.get("fulltext_score"),
                    "rrf_score": chunk.get("rrf_score"),
                },
            }
        )
    if type_counts:
        parts = [f"{count} {t}" for t, count in sorted(type_counts.items(), key=lambda x: -x[1])]
        formatted["provenance_summary"] = ", ".join(parts)
    return formatted


def apply_retrieval_preferences(context_chunks: list, retrieval_cfg: dict) -> list:
    """Apply retrieval preferences (prefer_types, max_per_type) to context chunks."""
    prefer_types = retrieval_cfg.get("prefer_types", [])
    max_per_type = retrieval_cfg.get("max_per_type", {})

    if prefer_types:
        # Light re-ranking boost
        for ch in context_chunks:
            if ch.get("doc_type") in prefer_types:
                ch["rrf_score"] = (ch.get("rrf_score") or 0.0) + 0.05
        context_chunks = sorted(
            context_chunks, key=lambda c: c.get("rrf_score") or 0.0, reverse=True
        )

    if max_per_type:
        taken = []
        counts = {}
        for ch in context_chunks:
            t = ch.get("doc_type")
            allowed = max_per_type.get(t)
            if allowed is None or counts.get(t, 0) < allowed:
                taken.append(ch)
                counts[t] = counts.get(t, 0) + 1
        context_chunks = taken

    return context_chunks


def triage_agent(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Triager Agent - Analyzes and triages an alert.

    Flow:
    1. Retrieve context from knowledge base
    2. Call LLM for triage
    3. Validate output with guardrails
    4. Apply policy gate
    5. Store incident in database
    6. Return triage output with evidence

    Args:
        alert: Alert dictionary with title, description, labels, etc.

    Returns:
        Dictionary with incident_id, triage output, evidence, and policy information
    """
    return _triage_agent_internal(alert)


def _triage_agent_internal(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Internal triage agent implementation per architecture.
    
    Per architecture: Triage agent ONLY retrieves:
    - Incident signatures (chunks with incident_signature_id)
    - Runbook metadata (documents, NOT steps)
    
    Output schema per architecture:
    {
        "incident_signature": {"failure_type": "...", "error_class": "..."},
        "matched_evidence": {"incident_signatures": [...], "runbook_refs": [...]},
        "severity": "...",
        "confidence": 0.0-1.0,
        "policy": "AUTO|PROPOSE|REVIEW"
    }
    """
    # Convert alert timestamp if needed
    if isinstance(alert.get("ts"), datetime):
        alert["ts"] = alert["ts"].isoformat()
    elif "ts" not in alert:
        alert["ts"] = datetime.utcnow().isoformat()
    
    # Debug: Log alert structure to verify affected_services is present
    logger.debug(f"Alert keys: {list(alert.keys())}, affected_services: {alert.get('affected_services')}")

    # Retrieve evidence (incident signatures and runbook metadata only)
    # Build query text with better keyword extraction
    title = alert.get('title', '') or ''
    description = alert.get('description', '') or ''
    
    # Extract key phrases from description for better matching
    # Remove common noise words and focus on error messages
    key_phrases = []
    if description:
        # Extract error messages, job names, step names
        import re
        # Look for patterns like "Unable to...", "The step failed", "Job failed"
        error_patterns = [
            r'Unable to [^\.]+',
            r'[Tt]he step failed',
            r'[Jj]ob failed',
            r'[Ee]rror[^\.]*',
            r'[Ff]ailed[^\.]*',
        ]
        for pattern in error_patterns:
            matches = re.findall(pattern, description)
            key_phrases.extend(matches)
    
    # Combine title, description, and unique key phrases
    query_parts = [title, description]
    if key_phrases:
        # Remove duplicates while preserving order
        seen = set()
        unique_phrases = []
        for phrase in key_phrases:
            phrase_lower = phrase.lower().strip()
            if phrase_lower and phrase_lower not in seen:
                seen.add(phrase_lower)
                unique_phrases.append(phrase.strip())
        query_parts.extend(unique_phrases)
    
    # Join and clean up extra whitespace
    query_text = ' '.join(query_parts).strip()
    # Clean up: remove extra spaces, normalize punctuation
    import re
    query_text = re.sub(r'\s+', ' ', query_text)  # Multiple spaces to single
    query_text = re.sub(r'\.\s*\.', '.', query_text)  # Multiple periods
    query_text = query_text.strip()
    
    labels = alert.get("labels", {}) or {}
    service_val = labels.get("service") if isinstance(labels, dict) else None
    component_val = labels.get("component") if isinstance(labels, dict) else None

    logger.info(
        f"Starting triage: query_text='{query_text[:150]}...', "
        f"service={service_val}, component={component_val}, "
        f"key_phrases={key_phrases[:3] if key_phrases else []}"
    )

    # Get retrieval config for triage
    retrieval_cfg = (get_retrieval_config() or {}).get("triage", {})
    retrieval_limit = retrieval_cfg.get("limit", 5)
    vector_weight = retrieval_cfg.get("vector_weight", 0.7)
    fulltext_weight = retrieval_cfg.get("fulltext_weight", 0.3)

    # Use specialized triage retrieval (incident signatures + runbook metadata only)
    try:
        triage_evidence = triage_retrieval(
            query_text=query_text,
            service=service_val,
            component=component_val,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight,
        )
        
        # Validate retrieval boundaries (guardrail: wrong retrieval)
        is_valid_retrieval, retrieval_errors = validate_triage_retrieval_boundaries(triage_evidence)
        if not is_valid_retrieval:
            logger.error(f"Triage retrieval boundary violation: {retrieval_errors}")
            raise ValueError(f"Triage retrieval violated architecture boundaries: {', '.join(retrieval_errors)}")
        
    except Exception as e:
        logger.error(f"Triage retrieval failed: {e}", exc_info=True)
        triage_evidence = {"incident_signatures": [], "runbook_metadata": []}

    incident_signatures = triage_evidence.get("incident_signatures", [])
    runbook_metadata = triage_evidence.get("runbook_metadata", [])
    
    logger.info(
        f"Triage retrieval completed: {len(incident_signatures)} signatures, "
        f"{len(runbook_metadata)} runbook metadata"
    )
    
    # Debug: Log metadata structure of first signature to verify fields are present
    if incident_signatures:
        first_sig = incident_signatures[0]
        metadata = first_sig.get("metadata", {})
        logger.debug(
            f"First signature metadata keys: {list(metadata.keys())}, "
            f"assignment_group={metadata.get('assignment_group')}, "
            f"impact={metadata.get('impact')}, urgency={metadata.get('urgency')}"
        )

    # Check if we have evidence
    evidence_warning = None
    has_evidence = len(incident_signatures) > 0 or len(runbook_metadata) > 0

    if not has_evidence:
        try:
            from db.connection import get_db_connection

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM documents")
            result = cur.fetchone()
            doc_count = result["count"] if isinstance(result, dict) else result[0]
            conn.close()
        except Exception as e:
            logger.warning(f"Could not check document count: {e}")
            doc_count = None

        if doc_count is None:
            evidence_warning = (
                "No matching evidence found (could not verify database). Manual review required."
            )
        elif doc_count == 0:
            evidence_warning = (
                "No historical data found in knowledge base. Please ingest runbooks/incidents. "
                "Proceeding with REVIEW and confidence=0.0."
            )
        else:
            evidence_warning = (
                f"No matching evidence found. Database has {doc_count} documents, but none match the alert context. "
                "Proceeding with REVIEW and confidence=0.0. Please align service/component metadata or ingest matching data."
            )

    # Call LLM for triage with evidence
    if has_evidence:
        logger.info("Calling LLM for triage with evidence...")
        triage_output = call_llm_for_triage(alert, triage_evidence)
        logger.debug(
            f"LLM triage completed: failure_type={triage_output.get('incident_signature', {}).get('failure_type')}, "
            f"confidence={triage_output.get('confidence')}"
        )

        # Validate triage output with guardrails
        is_valid, validation_errors = validate_triage_output(triage_output)
        if not is_valid:
            logger.error(f"Triage validation failed: {validation_errors}")
            raise ValueError(f"Triage output validation failed: {', '.join(validation_errors)}")
        
        # Validate no hallucination (guardrail: hallucination)
        is_valid_no_hallucination, hallucination_errors = validate_triage_no_hallucination(
            triage_output, triage_evidence
        )
        if not is_valid_no_hallucination:
            logger.error(f"Triage hallucination detected: {hallucination_errors}")
            raise ValueError(f"Triage output contains hallucinated content: {', '.join(hallucination_errors)}")

        # Apply policy gate
        workflow_cfg = get_workflow_config() or {}
        feedback_before_policy = bool(workflow_cfg.get("feedback_before_policy", False))
        if feedback_before_policy:
            policy_decision = None
            policy_band = "PENDING"
            logger.info("Policy evaluation deferred until feedback received")
        else:
            policy_decision = get_policy_from_config(triage_output)
            policy_band = policy_decision.get("policy_band", "REVIEW")
            logger.info(f"Policy decision: {policy_band}")
        
        # Update triage output with policy (policy gate determines this)
        triage_output["policy"] = policy_band
        
        # PREDICT routing from matched incident signatures (primary method)
        # This uses historical evidence to determine which team should handle this incident
        predicted_routing = predict_routing_from_evidence(incident_signatures)
        if predicted_routing:
            triage_output["routing"] = predicted_routing
            logger.info(f"Routing predicted from evidence: {predicted_routing}")
        else:
            # Fallback: Extract routing from alert labels if no evidence available
            routing = extract_routing_from_alert(alert)
            if routing:
                triage_output["routing"] = routing
                logger.info(f"Routing extracted from alert labels (fallback): {routing}")
        
        # PREDICT impact and urgency from matched incident signatures (primary method)
        # This uses historical evidence to determine priority based on impact/urgency patterns
        predicted_impact_urgency = predict_impact_urgency_from_evidence(incident_signatures)
        if predicted_impact_urgency:
            impact, urgency = predicted_impact_urgency
            # Store impact and urgency separately
            triage_output["impact"] = impact
            triage_output["urgency"] = urgency
            # Derive severity from impact/urgency
            predicted_severity = derive_severity_from_impact_urgency(impact, urgency)
            triage_output["severity"] = predicted_severity
            logger.info(f"Impact/urgency/severity predicted from evidence: impact={impact}, urgency={urgency}, severity={predicted_severity}")
        else:
            # Fallback: Derive from alert labels if no evidence available
            labels = alert.get("labels", {})
            impact = labels.get("impact")
            urgency = labels.get("urgency")
            if impact and urgency:
                triage_output["impact"] = impact
                triage_output["urgency"] = urgency
                mapped_severity = derive_severity_from_impact_urgency(impact, urgency)
                triage_output["severity"] = mapped_severity
                logger.info(f"Impact/urgency/severity derived from alert labels (fallback): impact={impact}, urgency={urgency}, severity={mapped_severity}")
        
        # Extract affected_services from alert
        affected_services = alert.get("affected_services")
        if affected_services is not None:
            if isinstance(affected_services, str):
                affected_services = [affected_services]
            elif not isinstance(affected_services, list):
                affected_services = [str(affected_services)]
            if len(affected_services) > 0:
                triage_output["affected_services"] = affected_services
        # Also check labels if not in alert directly
        elif isinstance(alert.get("labels"), dict):
            labels = alert.get("labels", {})
            if "affected_services" in labels:
                aff_svc = labels.get("affected_services")
                if isinstance(aff_svc, str):
                    aff_svc = [aff_svc]
                elif not isinstance(aff_svc, list):
                    aff_svc = [str(aff_svc)]
                if len(aff_svc) > 0:
                    triage_output["affected_services"] = aff_svc

        # Format evidence for storage
        formatted_evidence = {
            "incident_signatures": [
                {
                    "chunk_id": sig.get("chunk_id"),
                    "document_id": sig.get("document_id"),
                    "incident_signature_id": sig.get("metadata", {}).get("incident_signature_id"),
                    "failure_type": sig.get("metadata", {}).get("failure_type"),
                    "error_class": sig.get("metadata", {}).get("error_class"),
                }
                for sig in incident_signatures
            ],
            "runbook_metadata": [
                {
                    "document_id": rb.get("document_id"),
                    "runbook_id": rb.get("tags", {}).get("runbook_id"),
                    "title": rb.get("title"),
                    "service": rb.get("service"),
                    "component": rb.get("component"),
                }
                for rb in runbook_metadata
            ],
            "retrieval_method": "triage_retrieval",
            "retrieval_params": {
                "query_text": query_text,
                "service": service_val,
                "component": component_val,
                "limit": retrieval_limit,
            },
        }
    else:
        # Fallback triage output with REVIEW band and confidence 0.0
        title = alert.get("title", "Unknown alert") if isinstance(alert, dict) else "Unknown alert"
        
        # No evidence found - use fallback methods
        # Extract routing from alert (fallback when no evidence)
        routing = extract_routing_from_alert(alert)
        labels = alert.get("labels", {})
        impact = labels.get("impact", "3 - Low")
        urgency = labels.get("urgency", "3 - Low")
        severity = derive_severity_from_impact_urgency(impact, urgency)
        
        triage_output = {
            "incident_signature": {
                "failure_type": "UNKNOWN_FAILURE",
                "error_class": "UNKNOWN_ERROR"
            },
            "matched_evidence": {
                "incident_signatures": [],
                "runbook_refs": []
            },
            "severity": severity,
            "confidence": 0.0,
            "policy": "REVIEW"
        }
        
        if routing:
            triage_output["routing"] = routing
            logger.info(f"Routing extracted from alert labels (no evidence available): {routing}")

        # Extract affected_services from alert
        affected_services = alert.get("affected_services")
        logger.debug(f"Extracting affected_services from alert: {affected_services}, type: {type(affected_services)}")
        if affected_services is not None:
            if isinstance(affected_services, str):
                affected_services = [affected_services]
            elif not isinstance(affected_services, list):
                affected_services = [str(affected_services)]
            if len(affected_services) > 0:
                triage_output["affected_services"] = affected_services
                logger.info(f"Added affected_services to triage output: {affected_services}")
        
        # Also check labels if not already set
        if "affected_services" not in triage_output and isinstance(alert.get("labels"), dict):
            labels = alert.get("labels", {})
            logger.debug(f"Checking labels for affected_services: {labels.get('affected_services')}")
            if "affected_services" in labels:
                aff_svc = labels.get("affected_services")
                if isinstance(aff_svc, str):
                    aff_svc = [aff_svc]
                elif not isinstance(aff_svc, list):
                    aff_svc = [str(aff_svc)]
                if len(aff_svc) > 0:
                    triage_output["affected_services"] = aff_svc
                    logger.info(f"Added affected_services from labels to triage output: {aff_svc}")

        # Force REVIEW policy band
        policy_decision = {
            "policy_band": "REVIEW",
            "can_auto_apply": False,
            "requires_approval": True,
            "notification_required": False,
            "rollback_required": False,
            "policy_reason": "No matching evidence; manual review required.",
        }
        policy_band = "REVIEW"

        formatted_evidence = {
            "incident_signatures": [],
            "runbook_metadata": [],
            "retrieval_method": "triage_retrieval",
            "retrieval_params": {
                "query_text": query_text,
                "service": service_val,
                "component": component_val,
                "limit": retrieval_limit,
            },
        }

    # Store incident with evidence and policy decision
    repository = IncidentRepository()
    incident_id = repository.create(
        alert=alert,
        triage_output=triage_output,
        triage_evidence=formatted_evidence,
        policy_band=policy_band,
        policy_decision=policy_decision,
    )

    logger.info(
        f"Triage completed successfully: incident_id={incident_id}, "
        f"severity={triage_output.get('severity')}, policy_band={policy_band}"
    )

    result = {
        "incident_id": incident_id,
        "triage": triage_output,
        "evidence": formatted_evidence,
        "policy_band": policy_band,
        "policy_decision": policy_decision,
    }

    if evidence_warning:
        result["warning"] = evidence_warning

    return result
