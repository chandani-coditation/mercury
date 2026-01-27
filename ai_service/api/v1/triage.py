"""Triage endpoints."""

import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from ai_service.models import Alert
from ai_service.agents import triage_agent
from ai_service.agents.triager_state import triage_agent_state
from ai_service.core import get_logger, ValidationError
from ai_service.api.error_utils import format_user_friendly_error
from ai_service.services import IncidentService
from ai_service.utils.log_processing import process_ticket_logs_for_triage

logger = get_logger(__name__)
router = APIRouter()

USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "false").lower() == "true"


def _record_triage_latency_and_update_incident(result: dict, start_time: datetime) -> float:
    """Attach end-to-end API latency to triage output and persist to the incident."""
    latency = (datetime.utcnow() - start_time).total_seconds()

    try:
        incident_id = result.get("incident_id")
        triage_output = result.get("triage") or {}
        triage_output["api_latency_secs"] = latency
        result["triage"] = triage_output

        if incident_id:
            IncidentService().update_triage_output(incident_id, triage_output)
    except Exception as e:
        logger.warning(
            f"Failed to record triage API latency/update incident: {e}",
            exc_info=True,
        )

    return latency


@router.post("/triage")
async def triage(
    alert: Alert,
    use_state: bool = Query(False, description="Use state-based HITL workflow"),
    use_langgraph: bool = Query(None, description="Use LangGraph framework (overrides env var)"),
):
    """
    Triage an alert.

    This endpoint uses the Triager Agent to:
    1. Retrieve context from knowledge base
    2. Call LLM for triage
    3. Validate output with guardrails
    4. Apply policy gate
    5. Store incident in database
    6. Return triage output

    **Request Body:**
    - Alert object with title, description, labels, etc.

    **Response:**
    - incident_id: Unique incident identifier
    - triage: Triage assessment with severity, category, confidence
    - evidence_chunks: Retrieved context chunks used for triage
    - policy_band: Policy decision (AUTO/PROPOSE/REVIEW)
    """
    use_lg = use_langgraph if use_langgraph is not None else USE_LANGGRAPH

    start_time = datetime.utcnow()
    try:
        alert_dict = alert.model_dump(mode="json", exclude_none=True)
        if alert.ts:
            alert_dict["ts"] = alert.ts.isoformat() if isinstance(alert.ts, datetime) else alert.ts
        else:
            alert_dict["ts"] = datetime.utcnow().isoformat()
        if hasattr(alert, "affected_services") and alert.affected_services is not None:
            alert_dict["affected_services"] = alert.affected_services
        if "affected_services" not in alert_dict and hasattr(alert, "__dict__"):
            if hasattr(alert, "affected_services"):
                logger.debug(f"Alert.affected_services attribute: {alert.affected_services}")

        # Process and add ticket logs to alert context for triage
        process_ticket_logs_for_triage(alert_dict)

        # Call triager agent (LangGraph, state-based, or synchronous)
        if use_lg:
            # Use LangGraph
            from ai_service.agents.langgraph_wrapper import run_triage_graph

            result = run_triage_graph(alert_dict)
        elif use_state:
            # Use state-based HITL workflow
            result = await triage_agent_state(alert_dict, use_state_bus=True)
        else:
            # Use synchronous agent (backward compatible)
            result = triage_agent(alert_dict)

        # Compute latency and persist triage output in a helper
        latency = _record_triage_latency_and_update_incident(result=result, start_time=start_time)

        return result

    except ValueError as e:
        # Handle validation errors (e.g., guardrail validation failures)
        error_msg = format_user_friendly_error(e, error_type="validation")
        logger.warning(f"Triage validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=error_msg)
    except ValidationError as e:
        error_msg = format_user_friendly_error(e, error_type="validation")
        logger.warning(f"Triage validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        friendly_detail = format_user_friendly_error(e)
        logger.error(f"Triage error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=friendly_detail,
        )
