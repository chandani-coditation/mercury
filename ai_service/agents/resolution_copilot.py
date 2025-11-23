"""Resolution Copilot Agent - Generates resolution steps for incidents."""
from datetime import datetime
from typing import Dict, Any, Optional
from ai_service.llm_client import call_llm_for_triage, call_llm_for_resolution
from ai_service.repositories import IncidentRepository
from ai_service.core import IncidentNotFoundError
from ai_service.policy import get_policy_from_config, get_resolution_policy
from ai_service.guardrails import validate_triage_output, validate_resolution_output
from ai_service.core import (
    get_retrieval_config, get_workflow_config, get_logger, ApprovalRequiredError,
    resolution_requests_total, resolution_duration_seconds,
    retrieval_requests_total, retrieval_duration_seconds, retrieval_chunks_returned,
    llm_requests_total, llm_request_duration_seconds,
    policy_decisions_total, MetricsTimer
)
from retrieval.hybrid_search import hybrid_search
from ai_service.agents.triager import format_evidence_chunks, apply_retrieval_preferences

logger = get_logger(__name__)


def resolution_copilot_agent(
    incident_id: Optional[str] = None,
    alert: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Resolution Copilot Agent - Generates resolution steps for an incident.
    
    If incident_id is provided, fetch the incident and use its alert/triage.
    Otherwise, use the provided alert and perform triage first.
    
    Flow:
    1. Get incident (or create from alert)
    2. Retrieve runbook-heavy context
    3. Apply policy gate
    4. Call LLM for resolution
    5. Validate with guardrails
    6. Store resolution
    7. Return resolution output
    
    Args:
        incident_id: Optional incident ID to fetch existing incident
        alert: Optional alert dictionary (used if incident_id not provided)
    
    Returns:
        Dictionary with incident_id, resolution output, evidence, and policy information
    """
    # Track overall resolution duration
    with MetricsTimer(resolution_duration_seconds):
        return _resolution_copilot_agent_internal(incident_id, alert)


def _resolution_copilot_agent_internal(
    incident_id: Optional[str] = None,
    alert: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Internal resolution copilot agent implementation (called by resolution_copilot_agent with metrics)."""
    logger.info(f"Starting resolution: incident_id={incident_id}")
    
    # Initialize warning variables
    evidence_warning = None
    resolution_evidence_warning = None
    
    # Get incident
    repository = IncidentRepository()
    if incident_id:
        try:
            incident = repository.get_by_id(incident_id)
        except IncidentNotFoundError as e:
            logger.error(f"Incident not found: {incident_id}")
            resolution_requests_total.labels(status="not_found", policy_band="unknown").inc()
            raise
        alert_dict = incident["raw_alert"]
        triage_output = incident["triage_output"]
        existing_policy_band = incident.get("policy_band")
        logger.debug(f"Using existing incident: {incident_id}, policy_band={existing_policy_band}")
        # evidence_warning is not used in this path (only in triage-first path), but ensure it's None
        evidence_warning = None
    else:
        if not alert:
            logger.error("Resolution called without incident_id or alert")
            resolution_requests_total.labels(status="validation_error", policy_band="unknown").inc()
            raise ValueError("Either incident_id or alert required")
        alert_dict = alert.copy()
        if isinstance(alert_dict.get("ts"), datetime):
            alert_dict["ts"] = alert_dict["ts"].isoformat()
        elif "ts" not in alert_dict:
            alert_dict["ts"] = datetime.utcnow().isoformat()
        
        logger.info("Performing triage first (no incident_id provided)")
        
        # Get retrieval config for triage (when doing triage first)
        retrieval_config_all = get_retrieval_config()
        if retrieval_config_all is None:
            retrieval_config_all = {}
        triage_retrieval_cfg = retrieval_config_all.get("triage", {})
        triage_limit = triage_retrieval_cfg.get("limit", 5)
        triage_vector_weight = triage_retrieval_cfg.get("vector_weight", 0.7)
        triage_fulltext_weight = triage_retrieval_cfg.get("fulltext_weight", 0.3)
        
        # Perform triage first
        query_text = f"{alert.get('title', '')} {alert.get('description', '')}"
        labels = alert.get("labels", {}) or {}
        context_chunks = hybrid_search(
            query_text=query_text,
            service=labels.get("service") if isinstance(labels, dict) else None,
            component=labels.get("component") if isinstance(labels, dict) else None,
            limit=triage_limit,
            vector_weight=triage_vector_weight,
            fulltext_weight=triage_fulltext_weight
        )
        
        # Check if we have evidence - if not, proceed with warning
        # Note: evidence_warning already initialized at function start, but we reset it here for triage-first path
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
                        "Resolution generated without context. "
                        "Please ingest historical data (alerts, incidents, runbooks, logs) for better results. "
                        "Use: python scripts/data/generate_fake_data.py --all --count 20"
                    )
                    logger.warning(evidence_warning)
                    resolution_requests_total.labels(status="no_data", policy_band="unknown").inc()
                else:
                    # Data exists but no matching chunks found
                    evidence_warning = (
                        f"No matching evidence found for resolution. "
                        f"Database has {doc_count} documents, but none match the context. "
                        "Resolution generated without relevant historical evidence. "
                        "Please ensure relevant historical data is ingested for better results."
                    )
                    logger.warning(evidence_warning)
                    resolution_requests_total.labels(status="no_matching_context", policy_band="unknown").inc()
            except Exception as e:
                # If we can't check the database, proceed with warning
                evidence_warning = f"Cannot verify database state: {e}. Proceeding without evidence validation."
                logger.warning(evidence_warning)
                resolution_requests_total.labels(status="warning", policy_band="unknown").inc()
        
        triage_output = call_llm_for_triage(alert_dict, context_chunks)
        
        # Validate triage output
        is_valid, validation_errors = validate_triage_output(triage_output)
        if not is_valid:
            logger.error(f"Triage validation failed during resolution: {validation_errors}")
            resolution_requests_total.labels(status="validation_error", policy_band="unknown").inc()
            raise ValueError(f"Triage output validation failed: {', '.join(validation_errors)}")
        
        # Run policy gate after triage
        policy_decision = get_policy_from_config(triage_output)
        existing_policy_band = policy_decision.get("policy_band", "REVIEW")
        policy_decisions_total.labels(policy_band=existing_policy_band).inc()
        
        incident_id = repository.create(
            alert=alert_dict,
            triage_output=triage_output,
            policy_band=existing_policy_band,
            policy_decision=policy_decision
        )
        logger.info(f"Created new incident: {incident_id}, policy_band={existing_policy_band}")
    
    # Check policy handling and approval requirements
    workflow_cfg = get_workflow_config() or {}
    resolution_requires_approval = bool(workflow_cfg.get("resolution_requires_approval", False))
    
    # If policy was deferred and still pending, compute from stored triage now
    if not existing_policy_band or existing_policy_band == "PENDING":
        policy_decision = get_policy_from_config(triage_output)
        existing_policy_band = policy_decision.get("policy_band", "REVIEW")
        try:
            repository.update_policy(incident_id, existing_policy_band, policy_decision)
        except Exception as e:
            logger.warning(f"Failed to update policy: {str(e)}")
    
    # Get the full policy decision from configuration to check approval requirements
    # This is derived from config/policy.json, not hardcoded
    if existing_policy_band and existing_policy_band != "PENDING":
        # Get policy decision from stored incident or compute it
        # Fetch fresh incident data to get updated policy_band and triage_output (in case it was updated via feedback)
        incident = repository.get_by_id(incident_id)
        # Update existing_policy_band from fresh fetch (may have been updated via feedback)
        existing_policy_band = incident.get("policy_band") or existing_policy_band
        # Update triage_output from fresh fetch (may have been edited by user via feedback)
        triage_output = incident.get("triage_output") or triage_output
        stored_policy_decision = incident.get("policy_decision")
        if stored_policy_decision:
            can_auto_apply = stored_policy_decision.get("can_auto_apply", False)
            requires_approval = stored_policy_decision.get("requires_approval", True)
        else:
            # Re-compute policy decision from configuration (using updated triage_output)
            policy_decision = get_policy_from_config(triage_output)
            can_auto_apply = policy_decision.get("can_auto_apply", False)
            requires_approval = policy_decision.get("requires_approval", True)
    else:
        # Policy is PENDING or not set - compute from configuration
        policy_decision = get_policy_from_config(triage_output)
        can_auto_apply = policy_decision.get("can_auto_apply", False)
        requires_approval = policy_decision.get("requires_approval", True)
        existing_policy_band = policy_decision.get("policy_band", "REVIEW")
    
    # Check if approval is required before proceeding to resolution
    # Process: Triage → Policy (from config) → Check can_auto_apply/requires_approval → (STOP if approval needed) → Resolution
    # Decision is derived from config/policy.json, not hardcoded
    if not can_auto_apply or requires_approval:
        error_msg = (
            f"User approval required before generating resolution. "
            f"Policy band: {existing_policy_band} (from configuration), "
            f"can_auto_apply: {can_auto_apply}, requires_approval: {requires_approval}. "
            f"Please review the triage results for incident {incident_id} and approve before requesting resolution."
        )
        logger.info(error_msg)
        resolution_requests_total.labels(status="approval_required", policy_band=existing_policy_band or "unknown").inc()
        raise ApprovalRequiredError(error_msg)
    
    # Get retrieval config for resolution
    retrieval_config_all = get_retrieval_config()
    if retrieval_config_all is None:
        retrieval_config_all = {}
    retrieval_config = retrieval_config_all.get("resolution", {})
    retrieval_limit = retrieval_config.get("limit", 10)
    vector_weight = retrieval_config.get("vector_weight", 0.6)
    fulltext_weight = retrieval_config.get("fulltext_weight", 0.4)
    
    # Retrieve runbook context (prefer runbooks)
    query_text = f"{alert_dict.get('title', '')} {alert_dict.get('description', '')} resolution steps runbook"
    labels = alert_dict.get("labels") or {}
    
    logger.debug(
        f"Retrieving context for resolution: query='{query_text[:100]}...', "
        f"limit={retrieval_limit}, vector_weight={vector_weight}, fulltext_weight={fulltext_weight}"
    )
    
    # Retrieve context with metrics
    with MetricsTimer(retrieval_duration_seconds, {"agent_type": "resolution"}):
        context_chunks = hybrid_search(
            query_text=query_text,
            service=labels.get("service") if isinstance(labels, dict) else None,
            component=labels.get("component") if isinstance(labels, dict) else None,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight
        )
        retrieval_requests_total.labels(agent_type="resolution", status="success").inc()
        retrieval_chunks_returned.labels(agent_type="resolution").observe(len(context_chunks))
    
    # Apply retrieval preferences (prefer_types, max_per_type)
    context_chunks = apply_retrieval_preferences(context_chunks, retrieval_config)
    
    logger.debug(f"Retrieved {len(context_chunks)} context chunks for resolution")
    
    # Check if we have evidence for resolution - if not, proceed with warning
    resolution_evidence_warning = None
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
                resolution_evidence_warning = (
                    "No historical data found in knowledge base for resolution. "
                    "Resolution generated without context. "
                    "Please ingest historical data (alerts, incidents, runbooks, logs) for better results. "
                    "Use: python scripts/data/generate_fake_data.py --all --count 20"
                )
                logger.warning(resolution_evidence_warning)
                resolution_requests_total.labels(status="no_data", policy_band=existing_policy_band or "unknown").inc()
            else:
                # Data exists but no matching chunks found
                resolution_evidence_warning = (
                    f"No matching evidence found for resolution. "
                    f"Database has {doc_count} documents, but none match the resolution context. "
                    "Resolution generated without relevant historical evidence (runbooks, similar incidents). "
                    "Please ensure relevant historical data is ingested for better results."
                )
                logger.warning(resolution_evidence_warning)
                resolution_requests_total.labels(status="no_matching_context", policy_band=existing_policy_band or "unknown").inc()
        except Exception as e:
            # If we can't check the database, proceed with warning
            resolution_evidence_warning = f"Cannot verify database state: {e}. Proceeding without evidence validation."
            logger.warning(resolution_evidence_warning)
            resolution_requests_total.labels(status="warning", policy_band=existing_policy_band or "unknown").inc()
    
    # Call LLM for resolution with metrics
    with MetricsTimer(llm_request_duration_seconds, {"agent_type": "resolution", "model": "gpt-4-turbo-preview"}):
        resolution_output = call_llm_for_resolution(alert_dict, triage_output, context_chunks)
        llm_requests_total.labels(agent_type="resolution", model="gpt-4-turbo-preview", status="success").inc()
    
    logger.debug(
        f"LLM resolution completed: risk_level={resolution_output.get('risk_level')}, "
        f"steps={len(resolution_output.get('resolution_steps', []))}"
    )
    
    # Validate resolution output with guardrails
    is_valid, validation_errors = validate_resolution_output(resolution_output)
    if not is_valid:
        logger.error(f"Resolution validation failed: {validation_errors}")
        resolution_requests_total.labels(status="validation_error", policy_band=existing_policy_band or "unknown").inc()
        raise ValueError(f"Resolution output validation failed: {', '.join(validation_errors)}")
    
    # Policy decision already exists from triage
    if incident_id:
        # Get existing policy decision from database
        incident = repository.get_by_id(incident_id)
        policy_decision = incident.get("policy_decision", {}) if incident else {}
    
    if not policy_decision:
        # Fallback: compute policy from severity and risk level
        severity = triage_output.get("severity", "medium")
        risk_level = resolution_output.get("risk_level", "medium")
        policy_decision = get_resolution_policy(severity, risk_level)
    
    policy_band = existing_policy_band or policy_decision.get("policy_band", "REVIEW")
    
    # Format evidence chunks for storage
    resolution_evidence = format_evidence_chunks(
        context_chunks,
        retrieval_method="hybrid_search",
        retrieval_params={
            "query_text": query_text,
            "service": labels.get("service") if isinstance(labels, dict) else None,
            "component": labels.get("component") if isinstance(labels, dict) else None,
            "limit": retrieval_limit
        }
    )
    
    # Store resolution with evidence (policy_band already stored from triage)
    repository.update_resolution(
        incident_id=incident_id,
        resolution_output=resolution_output,
        resolution_evidence=resolution_evidence,
        policy_band=policy_band,
        policy_decision=policy_decision
    )
    
    logger.info(
        f"Resolution completed successfully: incident_id={incident_id}, "
        f"risk_level={resolution_output.get('risk_level')}, "
        f"steps={len(resolution_output.get('resolution_steps', []))}, "
        f"policy_band={policy_band}"
    )
    resolution_requests_total.labels(status="success", policy_band=policy_band).inc()
    
    result = {
        "incident_id": incident_id,
        "resolution": resolution_output,
        "policy": policy_decision,
        "policy_band": policy_band,
        "context_chunks_used": len(context_chunks),
        "evidence_chunks": resolution_evidence
    }
    
    # Add warning if no evidence was found (for triage or resolution)
    # Note: evidence_warning is only set in triage-first path (when incident_id not provided)
    # resolution_evidence_warning is set in the normal resolution path (when incident_id is provided)
    # Both are initialized to None at function start, so safe to check
    if resolution_evidence_warning is not None:
        result["warning"] = resolution_evidence_warning
    elif evidence_warning is not None:
        result["warning"] = evidence_warning
    
    return result

