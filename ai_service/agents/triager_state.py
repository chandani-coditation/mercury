"""State-based Triager Agent - Emits state and pauses for HITL."""

from datetime import datetime
from typing import Dict, Any
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import validate_triage_output
from ai_service.state import AgentState, AgentStep, get_state_bus
from ai_service.core import get_retrieval_config, get_workflow_config, get_logger
from ai_service.agents.triager import (
    format_evidence_chunks,
    apply_retrieval_preferences,
)

logger = get_logger(__name__)
state_bus = get_state_bus()


async def triage_agent_state(
    alert: Dict[str, Any], use_state_bus: bool = True
) -> Dict[str, Any]:
    """
    State-based Triager Agent - Emits state snapshots and pauses for HITL.

    Flow:
    1. Initialize state
    2. Retrieve context → emit state
    3. Call LLM → emit state
    4. Validate → emit state
    5. Apply policy → emit state
    6. If requires_approval: pause for HITL action
    7. Store incident → emit state
    8. Return result

    Args:
        alert: Alert dictionary
        use_state_bus: Whether to use state bus (default: True)

    Returns:
        Dictionary with incident_id, triage output, evidence, policy
    """
    return await _triage_agent_state_internal(alert, use_state_bus)


async def _triage_agent_state_internal(
    alert: Dict[str, Any], use_state_bus: bool = True
) -> Dict[str, Any]:
    """Internal state-based triage agent implementation."""
    # Initialize state
    state = AgentState(
        agent_type="triage",
        current_step=AgentStep.INITIALIZED,
        alert=alert,
        alert_id=alert.get("alert_id"),
        started_at=datetime.utcnow(),
    )

    # Convert alert timestamp if needed
    if isinstance(alert.get("ts"), datetime):
        alert["ts"] = alert["ts"].isoformat()
    elif "ts" not in alert:
        alert["ts"] = datetime.utcnow().isoformat()

    # Retrieve context
    # Enhance query text for better retrieval
    try:
        from retrieval.query_enhancer import enhance_query

        query_text = enhance_query(alert)
    except Exception as e:
        logger.warning(f"Query enhancement failed, using basic query: {e}")
        query_text = f"{alert.get('title', '')} {alert.get('description', '')}"
    labels = alert.get("labels", {}) or {}
    service_val = labels.get("service") if isinstance(labels, dict) else None
    component_val = labels.get("component") if isinstance(labels, dict) else None

    logger.info(
        f"Starting state-based triage: query_text='{query_text[:100]}...', "
        f"service={service_val}, component={component_val}"
    )

    # Update state: retrieving context
    state.current_step = AgentStep.RETRIEVING_CONTEXT
    if use_state_bus:
        await state_bus.emit_state(state)

    # Get retrieval config
    retrieval_cfg = (get_retrieval_config() or {}).get("triage", {})
    retrieval_limit = retrieval_cfg.get("limit", 5)
    vector_weight = retrieval_cfg.get("vector_weight", 0.7)
    fulltext_weight = retrieval_cfg.get("fulltext_weight", 0.3)

    # Retrieve context
    from retrieval.hybrid_search import hybrid_search

    context_chunks = hybrid_search(
        query_text=query_text,
        service=service_val,
        component=component_val,
        limit=retrieval_limit,
        vector_weight=vector_weight,
        fulltext_weight=fulltext_weight,
    )
    context_chunks = apply_retrieval_preferences(context_chunks, retrieval_cfg)

    # Update state: context retrieved
    state.current_step = AgentStep.CONTEXT_RETRIEVED
    state.context_chunks = context_chunks
    state.context_chunks_count = len(context_chunks)

    # Check for evidence warnings
    evidence_warning = None
    if len(context_chunks) == 0:
        from db.connection import get_db_connection_context

        try:
            with get_db_connection_context() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as count FROM documents")
                result = cur.fetchone()
                doc_count = (
                    result["count"] if isinstance(result, dict) else result[0]
                )
                cur.close()

            if doc_count == 0:
                evidence_warning = (
                    "No historical data found in knowledge base. "
                    "Triage performed without context. "
                    "Please ingest historical data for better results."
                )
            else:
                evidence_warning = (
                    f"No matching evidence found. "
                    f"Database has {doc_count} documents, but none match the alert context."
                )
            state.warning = evidence_warning
            logger.warning(evidence_warning)
        except Exception as e:
            evidence_warning = f"Cannot verify database state: {e}"
            state.warning = evidence_warning
            logger.warning(evidence_warning)

    if use_state_bus:
        await state_bus.emit_state(state)

    # Update state: calling LLM
    state.current_step = AgentStep.CALLING_LLM
    if use_state_bus:
        await state_bus.emit_state(state)

    # Call LLM
    from ai_service.llm_client import call_llm_for_triage

    triage_output = call_llm_for_triage(alert, context_chunks)
    state.current_step = AgentStep.LLM_COMPLETED
    state.triage_output = triage_output
    if use_state_bus:
        await state_bus.emit_state(state)

    # Update state: validating
    state.current_step = AgentStep.VALIDATING
    if use_state_bus:
        await state_bus.emit_state(state)

    # Validate triage output
    is_valid, validation_errors = validate_triage_output(triage_output)
    if not is_valid:
        logger.error(f"Triage validation failed: {validation_errors}")
        state.current_step = AgentStep.ERROR
        state.error = f"Validation failed: {', '.join(validation_errors)}"
        if use_state_bus:
            await state_bus.emit_state(state)
        raise ValueError(
            f"Triage output validation failed: {', '.join(validation_errors)}"
        )

    # Update state: validation complete
    state.current_step = AgentStep.VALIDATION_COMPLETE
    if use_state_bus:
        await state_bus.emit_state(state)

    # Update state: evaluating policy
    state.current_step = AgentStep.POLICY_EVALUATING
    if use_state_bus:
        await state_bus.emit_state(state)

    # Determine if policy should be deferred
    workflow_cfg = get_workflow_config() or {}
    feedback_before_policy = bool(
        workflow_cfg.get("feedback_before_policy", False)
    )

    if feedback_before_policy:
        policy_decision = None
        policy_band = "PENDING"
        logger.info("Policy evaluation deferred until feedback received")
    else:
        # Run policy gate
        policy_decision = get_policy_from_config(triage_output)
        policy_band = policy_decision.get("policy_band", "REVIEW")
        logger.info(f"Policy decision: {policy_band}")

    # Update state with policy
    state.policy_band = policy_band
    state.policy_decision = policy_decision
    if policy_decision:
        state.can_auto_apply = policy_decision.get("can_auto_apply", False)
        state.requires_approval = policy_decision.get("requires_approval", True)

    # Update state: policy evaluated
    state.current_step = AgentStep.POLICY_EVALUATED
    if use_state_bus:
        await state_bus.emit_state(state)

    # Format evidence chunks
    triage_evidence = format_evidence_chunks(
        context_chunks,
        retrieval_method="hybrid_search",
        retrieval_params={
            "query_text": query_text,
            "service": service_val,
            "component": component_val,
            "limit": 5,
        },
    )
    state.triage_evidence = triage_evidence

    # Check if we need to pause for HITL
    if use_state_bus and state.requires_approval and not state.can_auto_apply:
        # Pause for review
        action_name = f"review_triage_{state.incident_id or 'pending'}"
        state = await state_bus.pause_for_action(
            state=state,
            action_name=action_name,
            action_type="review_triage",
            description="Review and approve triage output before proceeding",
            payload={
                "triage_output": triage_output,
                "triage_evidence": triage_evidence,
                "policy_band": policy_band,
                "policy_decision": policy_decision,
            },
            timeout_minutes=30,
        )

        # Store incident first (so we have incident_id)
        repository = IncidentRepository()
        incident_id = repository.create(
            alert=alert,
            triage_output=triage_output,
            triage_evidence=triage_evidence,
            policy_band=policy_band,
            policy_decision=policy_decision,
        )
        state.incident_id = incident_id

        # Update state with incident_id and re-emit
        if use_state_bus:
            await state_bus.emit_state(state)

        # Return state with pending action (agent is paused)
        return {
            "incident_id": incident_id,
            "triage": triage_output,
            "context_chunks_used": len(context_chunks),
            "evidence_chunks": triage_evidence,
            "policy_band": policy_band,
            "policy_decision": policy_decision,
            "pending_action": (
                state.pending_action.model_dump(mode="json")
                if state.pending_action
                else None
            ),
            "state": state.model_dump(mode="json"),
            "warning": evidence_warning,
        }

    # Update state: storing
    state.current_step = AgentStep.STORING
    if use_state_bus:
        await state_bus.emit_state(state)

    # Store incident
    repository = IncidentRepository()
    incident_id = repository.create(
        alert=alert,
        triage_output=triage_output,
        triage_evidence=triage_evidence,
        policy_band=policy_band,
        policy_decision=policy_decision,
    )
    state.incident_id = incident_id

    # Update state: completed
    state.current_step = AgentStep.COMPLETED
    state.completed_at = datetime.utcnow()
    if use_state_bus:
        await state_bus.emit_state(state)

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
        "policy_decision": policy_decision,
    }

    if use_state_bus:
        result["state"] = state.model_dump(mode="json")

    if evidence_warning:
        result["warning"] = evidence_warning

    return result
