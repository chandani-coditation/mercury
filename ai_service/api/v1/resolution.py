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
from ai_service.services import IncidentService

logger = get_logger(__name__)
router = APIRouter()

# Feature flag for LangGraph (can be enabled via environment variable)
USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "false").lower() == "true"


def _record_resolution_latency_and_update_incident(
    result: dict, incident_id: str | None, start_time: datetime
) -> float:
    """
    Attach end-to-end API latency to resolution output and persist to the incident.

    This helper is intentionally defensive: failures are logged but do not
    break the main /resolution flow.
    """
    latency = (datetime.utcnow() - start_time).total_seconds()

    try:
        incident_id_out = result.get("incident_id") or incident_id
        resolution_output = result.get("resolution") or {}
        resolution_output["api_latency_secs"] = latency
        result["resolution"] = resolution_output

        if incident_id_out:
            IncidentService().update_resolution(
                incident_id_out,
                resolution_output=resolution_output,
                resolution_evidence=result.get("evidence"),
            )
    except Exception as e:
        logger.warning(
            f"Failed to record resolution API latency/update incident: {e}",
            exc_info=True,
        )

    return latency


@router.post("/resolution")
async def resolution(
    incident_id: str = None,
    alert: Alert = None,
    use_state: bool = Query(False, description="Use state-based HITL workflow"),
    use_langgraph: bool = Query(None, description="Use LangGraph framework (overrides env var)"),
):
    """
    Generate resolution for an incident.

    Args:
        incident_id: Optional incident ID to fetch existing incident
        alert: Optional Alert object (used if incident_id not provided)
        use_state: Use state-based HITL workflow
        use_langgraph: Use LangGraph framework

    Returns:
        Dictionary with incident_id, resolution steps, and evidence
    """
    # Determine if LangGraph should be used
    use_lg = use_langgraph if use_langgraph is not None else USE_LANGGRAPH

    logger.info(
        f"Resolution request received: incident_id={incident_id}, use_state={use_state}, use_langgraph={use_lg}"
    )

    start_time = datetime.utcnow()

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
                error_msg = format_user_friendly_error(
                    ValueError("State-based resolution requires an incident_id. Please triage the alert first."),
                    error_type="validation"
                )
                raise HTTPException(status_code=400, detail=error_msg)
            result = await resolution_agent_state(
                incident_id=incident_id,
                alert=alert_dict,
                use_state_bus=True,
            )
        else:
            if incident_id:
                repository = IncidentRepository()
                try:
                    incident = repository.get_by_id(incident_id)
                    triage_output = incident.get("triage_output")
                    if not triage_output:
                        error_msg = format_user_friendly_error(
                            ValueError(f"Incident {incident_id} has no triage output. Please triage the alert first."),
                            error_type="validation"
                        )
                        raise HTTPException(status_code=400, detail=error_msg)
                    
                    # Parse JSON string if needed (psycopg may return JSONB as string)
                    import json
                    if isinstance(triage_output, str):
                        try:
                            triage_output = json.loads(triage_output)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse triage_output JSON: {e}")
                            raise ValueError(f"Invalid triage_output format: {e}")
                    
                    resolution_result = resolution_agent(triage_output)

                    metadata = resolution_result.get("_metadata", {})
                    original_runbook_steps_count = metadata.get("runbook_steps_retrieved", 0)

                    if "_metadata" in resolution_result:
                        del resolution_result["_metadata"]

                    result = {
                        "incident_id": incident_id,
                        "resolution": resolution_result,
                        "evidence": {
                            "retrieval_method": "resolution_retrieval",
                            "runbook_steps": original_runbook_steps_count,
                            "steps_retrieved": len(resolution_result.get("steps", [])),
                        },
                    }
                except IncidentNotFoundError as e:
                    error_msg = format_user_friendly_error(e, error_type="not_found")
                    raise HTTPException(status_code=404, detail=error_msg)
            else:
                result = resolution_copilot_agent(incident_id=incident_id, alert=alert_dict)

        # Compute latency and persist resolution output in a helper
        latency = _record_resolution_latency_and_update_incident(
            result=result, incident_id=incident_id, start_time=start_time
        )

        resolution_data = result.get("resolution") or {}
        steps = resolution_data.get("steps") or resolution_data.get("resolution_steps") or []


        return result

    except ApprovalRequiredError as e:
        error_msg = format_user_friendly_error(e, error_type="approval_required")
        logger.info(f"Resolution requires approval: {str(e)}")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "approval_required",
                "message": error_msg,
                "incident_id": incident_id if incident_id else None,
            },
        )
    except ValueError as e:
        error_msg = format_user_friendly_error(e, error_type="validation")
        logger.warning(f"Resolution validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=error_msg)
    except IncidentNotFoundError as e:
        error_msg = format_user_friendly_error(e, error_type="not_found")
        logger.warning(f"Resolution error - incident not found: {str(e)}")
        raise HTTPException(status_code=404, detail=error_msg)
    except ValidationError as e:
        error_msg = format_user_friendly_error(e, error_type="validation")
        logger.warning(f"Resolution validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        friendly_detail = format_user_friendly_error(e)
        logger.error(f"Resolution error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=friendly_detail,
        )
