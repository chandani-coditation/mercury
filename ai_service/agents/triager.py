"""Triager Agent - Analyzes and triages alerts."""

from datetime import datetime
from typing import Dict, Any
from ai_service.llm_client import call_llm_for_triage
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import (
    validate_triage_output,
    validate_triage_no_hallucination,
    validate_triage_retrieval_boundaries,
)
from ai_service.core import get_retrieval_config, get_workflow_config, get_logger
from retrieval.hybrid_search import triage_retrieval

logger = get_logger(__name__)


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

    # Retrieve evidence (incident signatures and runbook metadata only)
    query_text = f"{alert.get('title', '')} {alert.get('description', '')}"
    labels = alert.get("labels", {}) or {}
    service_val = labels.get("service") if isinstance(labels, dict) else None
    component_val = labels.get("component") if isinstance(labels, dict) else None

    logger.info(
        f"Starting triage: query_text='{query_text[:100]}...', "
        f"service={service_val}, component={component_val}"
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
        
        triage_output = {
            "incident_signature": {
                "failure_type": "UNKNOWN_FAILURE",
                "error_class": "UNKNOWN_ERROR"
            },
            "matched_evidence": {
                "incident_signatures": [],
                "runbook_refs": []
            },
            "severity": "medium",
            "confidence": 0.0,
            "policy": "REVIEW"
        }

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
