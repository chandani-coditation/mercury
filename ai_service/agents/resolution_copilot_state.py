"""State-based Resolution Agent - emits state snapshots and pauses for HITL."""
from datetime import datetime
from typing import Dict, Any, Optional

from retrieval.hybrid_search import hybrid_search

from ai_service.agents.triager import format_evidence_chunks, apply_retrieval_preferences
from ai_service.core import (
    get_logger,
    get_retrieval_config,
    IncidentNotFoundError,
    resolution_requests_total,
    resolution_duration_seconds,
    retrieval_requests_total,
    retrieval_duration_seconds,
    retrieval_chunks_returned,
    llm_requests_total,
    llm_request_duration_seconds,
    policy_decisions_total,
    agent_state_emitted_total,
    hitl_actions_total,
    hitl_actions_pending,
    MetricsTimer,
)
from ai_service.guardrails import validate_resolution_output
from ai_service.llm_client import call_llm_for_resolution
from ai_service.policy import get_policy_from_config, get_resolution_policy
from ai_service.repositories import IncidentRepository
from ai_service.state import AgentState, AgentStep, get_state_bus

logger = get_logger(__name__)
state_bus = get_state_bus()


async def resolution_agent_state(
    incident_id: Optional[str] = None,
    alert: Optional[Dict[str, Any]] = None,
    use_state_bus: bool = True,
) -> Dict[str, Any]:
    """
    Resolution agent with state/HITL support.

    Args:
        incident_id: Existing incident ID (required for current workflow)
        alert: Optional alert payload (not supported for state mode yet)
        use_state_bus: Whether to emit state snapshots
    """

    if not incident_id:
        raise ValueError("State-based resolution requires an incident_id")

    with MetricsTimer(resolution_duration_seconds):
        return await _resolution_agent_state_internal(
            incident_id=incident_id,
            alert=alert,
            use_state_bus=use_state_bus,
        )


async def _resolution_agent_state_internal(
    incident_id: str,
    alert: Optional[Dict[str, Any]] = None,
    use_state_bus: bool = True,
) -> Dict[str, Any]:
    repository = IncidentRepository()

    try:
        incident = repository.get_by_id(incident_id)
    except IncidentNotFoundError:
        resolution_requests_total.labels(status="not_found", policy_band="unknown").inc()
        raise

    alert_dict = incident.get("raw_alert") or alert or {}
    triage_output = incident.get("triage_output")
    if not triage_output:
        raise ValueError("Incident is missing triage output; cannot generate resolution")

    state = AgentState(
        agent_type="resolution",
        current_step=AgentStep.INITIALIZED,
        incident_id=incident_id,
        alert_id=alert_dict.get("alert_id"),
        alert=alert_dict,
        triage_output=triage_output,
        policy_band=incident.get("policy_band"),
        policy_decision=incident.get("policy_decision"),
        started_at=datetime.utcnow(),
    )

    if use_state_bus:
        await state_bus.emit_state(state)

    # Resolve policy information (fallback to config if missing/pending)
    if not state.policy_decision or state.policy_band in (None, "PENDING"):
        policy_decision = get_policy_from_config(triage_output)
        state.policy_decision = policy_decision
        state.policy_band = policy_decision.get("policy_band", "REVIEW")
        try:
            repository.update_policy(incident_id, state.policy_band, policy_decision)
        except Exception as exc:  # pragma: no cover - best-effort update
            logger.warning("Failed to persist policy decision: %s", exc)
            policy_decision = state.policy_decision
        policy_decisions_total.labels(policy_band=state.policy_band).inc()
    else:
        policy_decision = state.policy_decision

    state.can_auto_apply = bool(policy_decision.get("can_auto_apply", False))
    state.requires_approval = bool(policy_decision.get("requires_approval", True))

    # Retrieve runbook context
    state.current_step = AgentStep.RETRIEVING_CONTEXT
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="retrieving_context").inc()

    retrieval_cfg_all = get_retrieval_config() or {}
    resolution_cfg = retrieval_cfg_all.get("resolution", {})
    retrieval_limit = resolution_cfg.get("limit", 10)
    vector_weight = resolution_cfg.get("vector_weight", 0.6)
    fulltext_weight = resolution_cfg.get("fulltext_weight", 0.4)

    query_text = (
        f"{alert_dict.get('title', '')} "
        f"{alert_dict.get('description', '')} resolution steps runbook"
    )
    labels = alert_dict.get("labels") or {}

    with MetricsTimer(retrieval_duration_seconds, {"agent_type": "resolution"}):
        context_chunks = hybrid_search(
            query_text=query_text,
            service=labels.get("service") if isinstance(labels, dict) else None,
            component=labels.get("component") if isinstance(labels, dict) else None,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight,
        )
        retrieval_requests_total.labels(agent_type="resolution", status="success").inc()
        retrieval_chunks_returned.labels(agent_type="resolution").observe(len(context_chunks))

    context_chunks = apply_retrieval_preferences(context_chunks, resolution_cfg)
    state.context_chunks = context_chunks
    state.context_chunks_count = len(context_chunks)
    state.current_step = AgentStep.CONTEXT_RETRIEVED

    resolution_warning = None
    if len(context_chunks) == 0:
        from db.connection import get_db_connection  # lazy import to avoid cycles

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM documents")
            result = cur.fetchone()
            doc_count = result["count"] if isinstance(result, dict) else result[0]
            conn.close()

            if doc_count == 0:
                resolution_warning = (
                    "No historical data found in knowledge base for resolution. "
                    "Generated without contextual evidence."
                )
                resolution_requests_total.labels(
                    status="no_data",
                    policy_band=state.policy_band or "unknown",
                ).inc()
            else:
                resolution_warning = (
                    "No matching runbooks/incidents found. "
                    "Resolution generated without relevant evidence."
                )
                resolution_requests_total.labels(
                    status="no_matching_context",
                    policy_band=state.policy_band or "unknown",
                ).inc()
        except Exception as exc:  # pragma: no cover - diagnostic path
            resolution_warning = f"Cannot verify database state: {exc}"
            resolution_requests_total.labels(
                status="warning",
                policy_band=state.policy_band or "unknown",
            ).inc()
        state.warning = resolution_warning

    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="context_retrieved").inc()

    # LLM call
    state.current_step = AgentStep.CALLING_LLM
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="calling_llm").inc()

    with MetricsTimer(
        llm_request_duration_seconds,
        {"agent_type": "resolution", "model": "gpt-4-turbo-preview"},
    ):
        resolution_output = call_llm_for_resolution(alert_dict, triage_output, context_chunks)
        llm_requests_total.labels(
            agent_type="resolution",
            model="gpt-4-turbo-preview",
            status="success",
        ).inc()

    state.current_step = AgentStep.LLM_COMPLETED
    state.resolution_output = resolution_output
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="llm_completed").inc()

    # Validation
    state.current_step = AgentStep.VALIDATING
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="validating").inc()

    is_valid, validation_errors = validate_resolution_output(resolution_output)
    if not is_valid:
        state.current_step = AgentStep.ERROR
        state.error = f"Resolution validation failed: {', '.join(validation_errors)}"
        if use_state_bus:
            await state_bus.emit_state(state)
        resolution_requests_total.labels(
            status="validation_error",
            policy_band=state.policy_band or "unknown",
        ).inc()
        raise ValueError(state.error)

    state.current_step = AgentStep.VALIDATION_COMPLETE
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="validation_complete").inc()

    # Policy evaluation (mostly informational for resolution stage)
    state.current_step = AgentStep.POLICY_EVALUATING
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="policy_evaluating").inc()

    if not policy_decision:
        policy_decision = get_resolution_policy(
            triage_output.get("severity", "medium"),
            resolution_output.get("risk_level", "medium"),
        )
        state.policy_decision = policy_decision
        state.policy_band = policy_decision.get("policy_band", state.policy_band or "REVIEW")
        policy_decisions_total.labels(policy_band=state.policy_band).inc()

    state.can_auto_apply = bool(state.policy_decision.get("can_auto_apply", False))
    state.requires_approval = bool(state.policy_decision.get("requires_approval", True))

    state.current_step = AgentStep.POLICY_EVALUATED
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="policy_evaluated").inc()

    # Evidence packaging
    resolution_evidence = format_evidence_chunks(
        context_chunks,
        retrieval_method="hybrid_search",
        retrieval_params={
            "query_text": query_text,
            "service": labels.get("service") if isinstance(labels, dict) else None,
            "component": labels.get("component") if isinstance(labels, dict) else None,
            "limit": retrieval_limit,
        },
    )
    state.resolution_evidence = resolution_evidence

    # Persist resolution
    state.current_step = AgentStep.STORING
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="storing").inc()

    repository.update_resolution(
        incident_id=incident_id,
        resolution_output=resolution_output,
        resolution_evidence=resolution_evidence,
        policy_band=state.policy_band,
        policy_decision=state.policy_decision,
    )

    if use_state_bus and state.requires_approval and not state.can_auto_apply:
        action_name = f"review_resolution_{incident_id}"
        state = await state_bus.pause_for_action(
            state=state,
            action_name=action_name,
            action_type="review_resolution",
            description="Review and approve resolution output before execution",
            payload={
                "resolution_output": resolution_output,
                "resolution_evidence": resolution_evidence,
                "policy_band": state.policy_band,
                "policy_decision": state.policy_decision,
            },
            timeout_minutes=30,
        )
        hitl_actions_total.labels(action_type="review_resolution", status="created").inc()
        hitl_actions_pending.labels(action_type="review_resolution").inc()

        result = {
            "incident_id": incident_id,
            "resolution": resolution_output,
            "policy": state.policy_decision,
            "policy_band": state.policy_band,
            "context_chunks_used": len(context_chunks),
            "evidence_chunks": resolution_evidence,
            "pending_action": state.pending_action.model_dump(mode="json")
            if state.pending_action
            else None,
        }
        if resolution_warning:
            result["warning"] = resolution_warning
        if use_state_bus:
            result["state"] = state.model_dump(mode="json")
        return result

    # Completed flow (auto-apply)
    state.current_step = AgentStep.COMPLETED
    state.completed_at = datetime.utcnow()
    if use_state_bus:
        await state_bus.emit_state(state)
        agent_state_emitted_total.labels(agent_type="resolution", step="completed").inc()

    resolution_requests_total.labels(
        status="success",
        policy_band=state.policy_band or "unknown",
    ).inc()

    result = {
        "incident_id": incident_id,
        "resolution": resolution_output,
        "policy": state.policy_decision,
        "policy_band": state.policy_band,
        "context_chunks_used": len(context_chunks),
        "evidence_chunks": resolution_evidence,
    }
    if resolution_warning:
        result["warning"] = resolution_warning
    if use_state_bus:
        result["state"] = state.model_dump(mode="json")
    return result

