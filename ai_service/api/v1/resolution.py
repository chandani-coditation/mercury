"""Resolution endpoints."""

import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from ai_service.models import Alert
from ai_service.agents import resolution_copilot_agent, resolution_agent
from ai_service.agents.resolution_copilot_state import resolution_agent_state
from ai_service.core import (
    get_logger,
    ValidationError,
    IncidentNotFoundError,
    ApprovalRequiredError,
)
from ai_service.repositories import IncidentRepository
from ai_service.api.error_utils import format_user_friendly_error

logger = get_logger(__name__)
router = APIRouter()

# Feature flag for LangGraph (can be enabled via environment variable)
USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "false").lower() == "true"


@router.post("/resolution")
async def resolution(
    incident_id: str = None,
    alert: Alert = None,
    use_state: bool = Query(False, description="Use state-based HITL workflow"),
    use_langgraph: bool = Query(None, description="Use LangGraph framework (overrides env var)"),
):
    """
    Generate resolution for an incident.

    This endpoint uses the Resolution Copilot Agent to:
    1. Get incident (or create from alert)
    2. Retrieve runbook-heavy context
    3. Apply policy gate
    4. Call LLM for resolution
    5. Validate with guardrails
    6. Store resolution
    7. Return resolution output

    If incident_id is provided, fetch the incident and use its alert/triage.
    Otherwise, use the provided alert and perform triage first.

    **Query Parameters:**
    - incident_id: Optional incident ID to fetch existing incident

    **Request Body:**
    - alert: Optional Alert object (used if incident_id not provided)

    **Response:**
    - incident_id: Incident identifier
    - resolution: Resolution steps, commands, rollback plan
    - policy_band: Policy decision
    - evidence_chunks: Retrieved context chunks
    """
    # Determine if LangGraph should be used
    use_lg = use_langgraph if use_langgraph is not None else USE_LANGGRAPH

    logger.info(
        f"Resolution request received: incident_id={incident_id}, use_state={use_state}, use_langgraph={use_lg}"
    )

    try:
        # Convert alert to dict if provided
        alert_dict = None
        if alert:
            alert_dict = alert.model_dump()
            alert_dict["ts"] = alert.ts.isoformat() if isinstance(alert.ts, datetime) else alert.ts

        # Call resolution agent (LangGraph, state-based, or synchronous)
        if use_lg:
            # Use LangGraph
            from ai_service.agents.langgraph_wrapper import run_resolution_graph

            result = run_resolution_graph(incident_id=incident_id, alert=alert_dict)
        elif use_state:
            if not incident_id:
                raise HTTPException(
                    status_code=400,
                    detail="State-based resolution requires an incident_id. "
                    "Please triage the alert first.",
                )
            result = await resolution_agent_state(
                incident_id=incident_id,
                alert=alert_dict,
                use_state_bus=True,
            )
        else:
            # Use new architecture-compliant resolution_agent
            # It requires triage_output, so fetch incident first
            if incident_id:
                repository = IncidentRepository()
                try:
                    incident = repository.get_by_id(incident_id)
                    triage_output = incident.get("triage_output")
                    if not triage_output:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Incident {incident_id} has no triage output. Please triage the alert first."
                        )
                    # Call new resolution_agent with triage_output
                    resolution_result = resolution_agent(triage_output)
                    # Format response to match expected structure
                    result = {
                        "incident_id": incident_id,
                        "resolution": resolution_result,
                        "policy_band": incident.get("policy_band"),
                        "policy_decision": incident.get("policy_decision"),
                        "evidence": {
                            "retrieval_method": "resolution_retrieval",
                            "runbook_steps": len(resolution_result.get("recommendations", [])),
                        }
                    }
                except IncidentNotFoundError:
                    raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
            else:
                # No incident_id - use old copilot agent (backward compatibility)
                result = resolution_copilot_agent(incident_id=incident_id, alert=alert_dict)

        logger.info(
            f"Resolution completed: incident_id={result['incident_id']}, "
            f"risk_level={result['resolution'].get('risk_level')}, "
            f"steps={len(result['resolution'].get('steps', result['resolution'].get('resolution_steps', [])))}"
        )

        return result

    except ApprovalRequiredError as e:
        logger.info(f"Resolution requires approval: {str(e)}")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "approval_required",
                "message": str(e),
                "incident_id": incident_id if incident_id else None,
            },
        )
    except ValueError as e:
        # Handle validation errors (e.g., guardrail validation failures)
        error_msg = str(e)
        logger.warning(f"Resolution validation error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except IncidentNotFoundError as e:
        logger.warning(f"Resolution error - incident not found: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        logger.warning(f"Resolution validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        friendly_detail = format_user_friendly_error(e)
        logger.error(f"Resolution error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=friendly_detail,
        )
