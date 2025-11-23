"""Agent state and action endpoints for state-based HITL."""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional
from datetime import datetime
from ai_service.state import AgentState, ActionResponse, get_state_bus
from ai_service.core import get_logger, ValidationError
from ai_service.services import IncidentService
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import validate_triage_output, validate_resolution_output

logger = get_logger(__name__)
router = APIRouter()
state_bus = get_state_bus()


@router.websocket("/agents/{incident_id}/state")
async def websocket_state_stream(websocket: WebSocket, incident_id: str):
    """
    WebSocket endpoint for real-time agent state streaming.
    
    Clients connect to receive state updates for a specific incident.
    """
    await websocket.accept()
    logger.info(f"WebSocket connection opened: incident_id={incident_id}")
    
    # Send current state if available
    current_state = state_bus.get_state(incident_id)
    if current_state:
        await websocket.send_json(current_state.model_dump(mode="json"))
    
    # Subscribe to state updates
    async def state_callback(state: AgentState):
        try:
            await websocket.send_json(state.model_dump(mode="json"))
        except Exception as e:
            logger.error(f"Error sending state update: {e}", exc_info=True)
    
    state_bus.subscribe_state(incident_id, state_callback)
    
    try:
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            # Echo back or handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed: incident_id={incident_id}")
    finally:
        state_bus.unsubscribe_state(incident_id, state_callback)


@router.get("/agents/{incident_id}/state")
def get_agent_state(incident_id: str):
    """
    Get current agent state for an incident.
    
    Returns:
        Current AgentState or 404 if not found
    """
    state = state_bus.get_state(incident_id)
    if not state:
        raise HTTPException(status_code=404, detail="Agent state not found")
    return state.model_dump(mode="json")


@router.post("/agents/{incident_id}/actions/{action_name}/respond")
async def respond_to_action(
    incident_id: str,
    action_name: str,
    response: ActionResponse
):
    """
    Respond to a pending HITL action.
    
    This resumes agent execution after human review/approval.
    
    **Request Body:**
    - approved: Whether action was approved
    - user_edited: Optional user-edited data (triage/resolution output)
    - notes: Optional notes
    - policy_band: Optional policy band override (AUTO, PROPOSE, REVIEW)
    
    **Response:**
    - Updated agent state
    """
    logger.info(
        f"Action response received: incident_id={incident_id}, "
        f"action={action_name}, approved={response.approved}"
    )
    
    # Verify incident exists
    try:
        incident_service = IncidentService()
        incident = incident_service.get_incident(incident_id)
    except Exception as e:
        logger.warning(f"Incident not found: {incident_id}")
        raise HTTPException(status_code=404, detail="Incident not found")
    
    # Get pending action
    pending_action = state_bus.get_pending_action(incident_id)
    if not pending_action or pending_action.action_name != action_name:
        raise HTTPException(
            status_code=400,
            detail=f"No pending action found: {action_name}"
        )
    
    # Validate user_edited if provided
    if response.user_edited:
        if pending_action.action_type == "review_triage":
            # Validate triage output
            is_valid, validation_errors = validate_triage_output(response.user_edited)
            if not is_valid:
                raise ValidationError(
                    f"Triage output validation failed: {', '.join(validation_errors)}"
                )
            
            # Update incident with user-edited triage
            try:
                incident_service.update_triage_output(incident_id, response.user_edited)
            except Exception as e:
                logger.error(f"Failed to update triage output: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update triage output: {str(e)}"
                )
        
        elif pending_action.action_type == "review_resolution":
            is_valid, validation_errors = validate_resolution_output(response.user_edited)
            if not is_valid:
                raise ValidationError(
                    f"Resolution output validation failed: {', '.join(validation_errors)}"
                )

            try:
                incident_service.update_resolution(
                    incident_id=incident_id,
                    resolution_output=response.user_edited,
                    resolution_evidence=incident.get("resolution_evidence"),
                    policy_band=incident.get("policy_band"),
                    policy_decision=incident.get("policy_decision"),
                )
            except Exception as e:
                logger.error(f"Failed to update resolution output: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update resolution output: {str(e)}",
                )
    
    # Update policy if policy_band provided
    if response.policy_band:
        if response.policy_band not in ["AUTO", "PROPOSE", "REVIEW"]:
            raise ValidationError(
                f"Invalid policy_band: {response.policy_band}. Must be AUTO, PROPOSE, or REVIEW"
            )
        
        # Get triage output (use user_edited if provided, otherwise from incident)
        triage_output = response.user_edited if response.user_edited else incident.get("triage_output")
        if not triage_output:
            raise ValidationError("Cannot update policy without triage output")
        
        # Recompute policy decision
        policy_decision = get_policy_from_config(triage_output)
        policy_decision["policy_band"] = response.policy_band
        if response.policy_band == "AUTO":
            policy_decision["can_auto_apply"] = True
            policy_decision["requires_approval"] = False
        else:
            policy_decision["can_auto_apply"] = False
            policy_decision["requires_approval"] = True
        
        # Update incident policy
        try:
            incident_service.update_policy(incident_id, response.policy_band, policy_decision)
        except Exception as e:
            logger.error(f"Failed to update policy: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update policy: {str(e)}"
            )
    
    # Resume agent from action
    updated_state = await state_bus.resume_from_action(
        incident_id=incident_id,
        action_name=action_name,
        approved=response.approved,
        user_edited=response.user_edited,
        notes=response.notes,
        policy_band=response.policy_band
    )
    
    if not updated_state:
        raise HTTPException(
            status_code=500,
            detail="Failed to resume agent from action"
        )
    
    logger.info(
        f"Action response processed: incident_id={incident_id}, "
        f"action={action_name}, state_step={updated_state.current_step}"
    )
    
    return {
        "status": "resumed",
        "incident_id": incident_id,
        "action_name": action_name,
        "state": updated_state.model_dump(mode="json")
    }


@router.get("/agents/{incident_id}/actions/pending")
def get_pending_action(incident_id: str):
    """
    Get pending action for an incident.
    
    Returns:
        PendingAction or 404 if none
    """
    pending_action = state_bus.get_pending_action(incident_id)
    if not pending_action:
        raise HTTPException(status_code=404, detail="No pending action found")
    return pending_action.model_dump(mode="json")

