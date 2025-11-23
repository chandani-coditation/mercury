"""Triager Agent - Analyzes and triages alerts."""
from datetime import datetime
from typing import Dict, Any
from ai_service.llm_client import call_llm_for_triage
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import validate_triage_output
from ai_service.core import (
    get_retrieval_config, get_workflow_config, get_logger,
    triage_requests_total, triage_duration_seconds,
    retrieval_requests_total, retrieval_duration_seconds, retrieval_chunks_returned,
    llm_requests_total, llm_request_duration_seconds,
    policy_decisions_total, MetricsTimer
)
from retrieval.hybrid_search import hybrid_search

logger = get_logger(__name__)


def format_evidence_chunks(context_chunks: list, retrieval_method: str = "hybrid_search", retrieval_params: dict = None) -> dict:
    """Format evidence chunks for storage with provenance fields."""
    formatted = {
        "chunks_used": len(context_chunks),
        "chunk_ids": [chunk.get("chunk_id") for chunk in context_chunks],
        "chunk_sources": [chunk.get("doc_title") for chunk in context_chunks],
        "chunks": [],
        "retrieval_method": retrieval_method,
        "retrieval_params": retrieval_params or {}
    }
    type_counts = {}
    for chunk in context_chunks:
        metadata = chunk.get("metadata") or {}
        source_type = chunk.get("doc_type") or metadata.get("doc_type") or metadata.get("source_type")
        if source_type:
            type_counts[source_type] = type_counts.get(source_type, 0) + 1
        formatted["chunks"].append({
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "doc_title": chunk.get("doc_title"),
            "content": chunk.get("content", "")[:500],
            "provenance": {
                "source_type": source_type,
                "source_id": chunk.get("document_id"),
                "service": metadata.get("service"),
                "component": metadata.get("component")
            },
            "metadata": metadata,
            "scores": {
                "vector_score": chunk.get("vector_score"),
                "fulltext_score": chunk.get("fulltext_score"),
                "rrf_score": chunk.get("rrf_score")
            }
        })
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
        context_chunks = sorted(context_chunks, key=lambda c: c.get("rrf_score") or 0.0, reverse=True)
    
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
    # Track overall triage duration
    with MetricsTimer(triage_duration_seconds):
        return _triage_agent_internal(alert)


def _triage_agent_internal(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Internal triage agent implementation (called by triage_agent with metrics)."""
    # Convert alert timestamp if needed
    if isinstance(alert.get("ts"), datetime):
        alert["ts"] = alert["ts"].isoformat()
    elif "ts" not in alert:
        alert["ts"] = datetime.utcnow().isoformat()
    
    # Retrieve context
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
    
    # Retrieve context with metrics
    with MetricsTimer(retrieval_duration_seconds, {"agent_type": "triage"}):
        context_chunks = hybrid_search(
            query_text=query_text,
            service=service_val,
            component=component_val,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight
        )
        retrieval_requests_total.labels(agent_type="triage", status="success").inc()
        retrieval_chunks_returned.labels(agent_type="triage").observe(len(context_chunks))
    
    # Apply retrieval preferences (prefer_types, max_per_type)
    context_chunks = apply_retrieval_preferences(context_chunks, retrieval_cfg)
    
    logger.debug(f"Retrieved {len(context_chunks)} context chunks for triage")
    
    # Check if we have evidence - if not, proceed with warning but still create incident
    evidence_warning = None
    if len(context_chunks) == 0:
        from db.connection import get_db_connection
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM documents")
            result = cur.fetchone()
            doc_count = result["count"] if isinstance(result, dict) else result[0]
            conn.close()
            
            if doc_count == 0:
                # No data in database at all
                evidence_warning = (
                    "No historical data found in knowledge base. "
                    "Triage performed without context. "
                    "Please ingest historical data (alerts, incidents, runbooks, logs) for better results. "
                    "Use: python scripts/data/generate_fake_data.py --all --count 20"
                )
                logger.warning(evidence_warning)
                triage_requests_total.labels(status="no_data").inc()
            else:
                # Data exists but no matching chunks found
                evidence_warning = (
                    f"No matching evidence found for this alert. "
                    f"Database has {doc_count} documents, but none match the alert context. "
                    "Triage performed without relevant historical evidence. "
                    "Please ensure relevant historical data is ingested for better results."
                )
                logger.warning(evidence_warning)
                triage_requests_total.labels(status="no_matching_context").inc()
        except Exception as e:
            # If we can't check the database, proceed with warning
            evidence_warning = f"Cannot verify database state: {e}. Proceeding without evidence validation."
            logger.warning(evidence_warning)
            triage_requests_total.labels(status="warning").inc()
    
    # Call LLM for triage with metrics
    with MetricsTimer(llm_request_duration_seconds, {"agent_type": "triage", "model": "gpt-4-turbo-preview"}):
        triage_output = call_llm_for_triage(alert, context_chunks)
        llm_requests_total.labels(agent_type="triage", model="gpt-4-turbo-preview", status="success").inc()
    
    logger.debug(f"LLM triage completed: severity={triage_output.get('severity')}, confidence={triage_output.get('confidence')}")
    
    # Validate triage output with guardrails
    is_valid, validation_errors = validate_triage_output(triage_output)
    if not is_valid:
        logger.error(f"Triage validation failed: {validation_errors}")
        triage_requests_total.labels(status="validation_error").inc()
        raise ValueError(f"Triage output validation failed: {', '.join(validation_errors)}")
    
    # Determine if policy should be deferred until feedback
    workflow_cfg = get_workflow_config() or {}
    feedback_before_policy = bool(workflow_cfg.get("feedback_before_policy", False))
    if feedback_before_policy:
        policy_decision = None
        policy_band = "PENDING"
        logger.info("Policy evaluation deferred until feedback received")
    else:
        # Run policy gate AFTER triage (configuration-driven)
        policy_decision = get_policy_from_config(triage_output)
        policy_band = policy_decision.get("policy_band", "REVIEW")
        policy_decisions_total.labels(policy_band=policy_band).inc()
        logger.info(f"Policy decision: {policy_band}")
    
    # Format evidence chunks for storage
    triage_evidence = format_evidence_chunks(
        context_chunks,
        retrieval_method="hybrid_search",
        retrieval_params={
            "query_text": query_text,
            "service": service_val,
            "component": component_val,
            "limit": 5
        }
    )
    
    # Store incident with evidence and policy decision
    repository = IncidentRepository()
    incident_id = repository.create(
        alert=alert,
        triage_output=triage_output,
        triage_evidence=triage_evidence,
        policy_band=policy_band,
        policy_decision=policy_decision
    )
    
    logger.info(
        f"Triage completed successfully: incident_id={incident_id}, "
        f"severity={triage_output.get('severity')}, policy_band={policy_band}"
    )
    triage_requests_total.labels(status="success").inc()
    
    result = {
        "incident_id": incident_id,
        "triage": triage_output,
        "context_chunks_used": len(context_chunks),
        "evidence_chunks": triage_evidence,
        "policy_band": policy_band,
        "policy_decision": policy_decision
    }
    
    # Add warning if no evidence was found
    if evidence_warning:
        result["warning"] = evidence_warning
    
    return result

