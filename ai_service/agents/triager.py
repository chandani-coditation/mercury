"""Triager Agent - Analyzes and triages alerts."""
from datetime import datetime
from typing import Dict, Any
from ai_service.llm_client import call_llm_for_triage
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import validate_triage_output
from ai_service.core import (
    get_retrieval_config, get_workflow_config, get_logger
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
    return _triage_agent_internal(alert)


def _triage_agent_internal(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Internal triage agent implementation."""
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
    
    # Retrieve context (primary pass: service/component filtered, all doc types, runbook-preferred via config)
    context_chunks = hybrid_search(
        query_text=query_text,
        service=service_val,
        component=component_val,
        limit=retrieval_limit,
        vector_weight=vector_weight,
        fulltext_weight=fulltext_weight
    )
    
    # Apply retrieval preferences (prefer_types, max_per_type)
    context_chunks = apply_retrieval_preferences(context_chunks, retrieval_cfg)
    
    # Optionally retrieve logs from InfluxDB if configured
    try:
        from retrieval.influxdb_client import get_influxdb_client
        influxdb_client = get_influxdb_client()
        if influxdb_client.is_configured():
            logs = influxdb_client.get_logs_for_context(
                query_text=query_text,
                service=service_val,
                component=component_val,
                limit=5  # Small limit for logs
            )
            # Convert logs to chunk-like format for consistency
            for log_content in logs:
                if log_content:
                    context_chunks.append({
                        "chunk_id": f"influxdb_log_{len(context_chunks)}",
                        "content": f"[Log Entry]\n{log_content}",
                        "doc_type": "log",
                        "source": "influxdb"
                    })
    except Exception as e:
        logger.debug(f"InfluxDB log retrieval not available or failed: {str(e)}")
    
    logger.debug(f"Retrieved {len(context_chunks)} context chunks for triage (primary search)")
    
    # If no context found, attempt a broader runbook-focused fallback search before giving up
    # This ensures we still try to propose a resolution grounded in runbooks when possible.
    fallback_used = False
    if not context_chunks:
        logger.info(
            "No context found in primary triage search; attempting runbook-focused fallback search "
            "with relaxed service/component filters."
        )
        try:
            # Broaden search by dropping service/component filters, but keep query text the same.
            fallback_chunks = hybrid_search(
                query_text=query_text,
                service=None,
                component=None,
                limit=retrieval_limit * 2,
                vector_weight=vector_weight,
                fulltext_weight=fulltext_weight
            )
            # Re-apply retrieval preferences (runbooks will be preferred if configured)
            fallback_chunks = apply_retrieval_preferences(fallback_chunks, retrieval_cfg)
            # Keep only runbook chunks for this fallback; incidents/logs are still useful but
            # runbooks are the primary source of resolution steps.
            runbook_chunks = [
                ch for ch in fallback_chunks
                if (ch.get("doc_type") or (ch.get("metadata") or {}).get("doc_type")) == "runbook"
            ]
            if runbook_chunks:
                context_chunks = runbook_chunks
                fallback_used = True
                logger.info(
                    f"Runbook-focused fallback search succeeded; using {len(context_chunks)} "
                    "runbook chunk(s) as context for triage."
                )
            else:
                logger.info(
                    "Runbook-focused fallback search did not find any matching runbooks; "
                    "proceeding with empty context and generic REVIEW."
                )
        except Exception as e:
            logger.warning(f"Runbook-focused fallback search failed: {e}")
    
    # Check if we have evidence - allow REVIEW fallback when missing
    evidence_warning = None
    MIN_REQUIRED_CHUNKS = 1
    context_missing = len(context_chunks) < MIN_REQUIRED_CHUNKS

    doc_count = None
    if context_missing:
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

        if doc_count is None:
            evidence_warning = "No matching context found (could not verify database). Manual review required."
        elif doc_count == 0:
            evidence_warning = (
                "No historical data found in knowledge base. Please ingest runbooks/incidents/logs. "
                "Proceeding with REVIEW and confidence=0.0."
            )
        else:
            evidence_warning = (
                f"No matching evidence found. Database has {doc_count} documents, but none match the alert context. "
                "Proceeding with REVIEW and confidence=0.0. Please align service/component metadata or ingest matching data."
            )

    # If we have context (primary or runbook-fallback), go through normal LLM path
    if not context_missing:
        logger.info(f"Context validation passed: {len(context_chunks)} chunks retrieved for triage")

        # Call LLM for triage
        logger.debug("Calling LLM for triage...")
        triage_output = call_llm_for_triage(alert, context_chunks)
        logger.debug(
            f"LLM triage completed: severity={triage_output.get('severity')}, "
            f"confidence={triage_output.get('confidence')}"
        )

        # Validate triage output with guardrails
        is_valid, validation_errors = validate_triage_output(triage_output)
        if not is_valid:
            logger.error(f"Triage validation failed: {validation_errors}")
            raise ValueError(f"Triage output validation failed: {', '.join(validation_errors)}")

        workflow_cfg = get_workflow_config() or {}
        feedback_before_policy = bool(workflow_cfg.get("feedback_before_policy", False))
        if feedback_before_policy:
            policy_decision = None
            policy_band = "PENDING"
            logger.info("Policy evaluation deferred until feedback received")
        else:
            # If we had to rely on the runbook-only fallback context, force REVIEW band and approval
            # even if policy.json would otherwise allow AUTO/PROPOSE. This keeps fallback-driven
            # resolutions under human-in-the-loop control.
            if fallback_used:
                policy_decision = {
                    "policy_band": "REVIEW",
                    "can_auto_apply": False,
                    "requires_approval": True,
                    "notification_required": False,
                    "rollback_required": False,
                    "policy_reason": "Runbook-only fallback context used; manual review required."
                }
                policy_band = "REVIEW"
                logger.info("Policy decision overridden to REVIEW due to runbook-only fallback context")
            else:
                policy_decision = get_policy_from_config(triage_output)
                policy_band = policy_decision.get("policy_band", "REVIEW")
                logger.info(f"Policy decision: {policy_band}")

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
    else:
        # Fallback triage output with REVIEW band and confidence 0.0
        labels = alert.get("labels", {}) if isinstance(alert, dict) else {}
        service_hint = labels.get("service") or "unknown"
        category_hint = labels.get("category") or "other"
        title = alert.get("title", "Unknown alert") if isinstance(alert, dict) else "Unknown alert"

        triage_output = {
            "severity": "medium",
            "category": category_hint,
            "summary": f"No context found for alert: {title}. Manual review required.",
            "likely_cause": "Unknown (no matching context evidence).",
            "routing": "UNKNOWN",
            "affected_services": [service_hint] if service_hint else [],
            "recommended_actions": [
                "Review alert details manually.",
                "Ingest or align historical data for this service/component.",
                "Retry triage after data alignment."
            ],
            "confidence": 0.0
        }

        # Force REVIEW policy band to reflect HITL requirement
        policy_decision = {
            "policy_band": "REVIEW",
            "can_auto_apply": False,
            "requires_approval": True,
            "notification_required": False,
            "rollback_required": False,
            "policy_reason": "No matching context; manual review required."
        }
        policy_band = "REVIEW"

        triage_evidence = format_evidence_chunks(
            context_chunks,  # empty list
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

    result = {
        "incident_id": incident_id,
        "triage": triage_output,
        "context_chunks_used": len(context_chunks),
        "evidence_chunks": triage_evidence,
        "policy_band": policy_band,
        "policy_decision": policy_decision
    }

    if evidence_warning:
        result["warning"] = evidence_warning

    return result

