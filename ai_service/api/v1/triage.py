"""Triage endpoints."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from ai_service.models import Alert
from ai_service.agents import triage_agent
from ai_service.agents.triager_state import triage_agent_state
from ai_service.core import get_logger, ValidationError
from ai_service.api.error_utils import format_user_friendly_error

logger = get_logger(__name__)
router = APIRouter()


@router.post("/triage")
async def triage(alert: Alert, use_state: bool = Query(False, description="Use state-based HITL workflow")):
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
    logger.info(f"Triage request received: alert={alert.title}, use_state={use_state}")
    
    try:
        # Convert alert to dict
        alert_dict = alert.model_dump()
        alert_dict["ts"] = alert.ts.isoformat() if isinstance(alert.ts, datetime) else alert.ts
        
        # Call triager agent (state-based or synchronous)
        if use_state:
            result = await triage_agent_state(alert_dict, use_state_bus=True)
        else:
            result = triage_agent(alert_dict)
        
        logger.info(
            f"Triage completed: incident_id={result['incident_id']}, "
            f"severity={result['triage'].get('severity')}, "
            f"policy_band={result['policy_band']}"
        )
        
        return result
    
    except ValueError as e:
        # Handle validation errors (e.g., guardrail validation failures)
        error_msg = str(e)
        logger.warning(f"Triage validation error: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except ValidationError as e:
        logger.warning(f"Triage validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        friendly_detail = format_user_friendly_error(e)
        logger.error(f"Triage error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=friendly_detail,
        )

