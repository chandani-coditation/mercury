"""Feedback endpoints."""
from datetime import datetime
from fastapi import APIRouter, HTTPException
from ai_service.models import FeedbackInput
from ai_service.services import IncidentService, FeedbackService
from ai_service.core import (
    get_logger, get_workflow_config,
    IncidentNotFoundError, DatabaseError, ValidationError
)
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import validate_triage_output

logger = get_logger(__name__)
router = APIRouter()


@router.put("/incidents/{incident_id}/feedback")
def submit_feedback(incident_id: str, feedback: FeedbackInput):
    """
    Submit human feedback/edits for an incident.
    
    This stores the feedback and can update the policy band for approval.
    
    **Approval Workflow:**
    - To approve an incident, provide `policy_band: "AUTO"` in the request
    - This will update the policy to AUTO, allowing resolution to proceed
    - You can also provide `user_edited` with the same triage/resolution output and `notes` for context
    
    **Request Body:**
    - feedback_type: "triage" or "resolution"
    - user_edited: Edited version of triage/resolution output (or same as system output for approval)
    - notes: Optional notes about the feedback
    - policy_band: Optional policy band override (AUTO, PROPOSE, REVIEW) for approval
    """
    try:
        incident_service = IncidentService()
        feedback_service = FeedbackService()
        
        # Get incident to get system output
        try:
            incident = incident_service.get_incident(incident_id)
        except IncidentNotFoundError:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # Get system output based on feedback type
        if feedback.feedback_type == "resolution":
            system_output = incident.get("resolution_output")
        elif feedback.feedback_type == "triage":
            system_output = incident.get("triage_output")
        else:
            raise ValidationError("feedback_type must be 'triage' or 'resolution'")
        
        if not system_output:
            raise ValidationError(
                f"No {feedback.feedback_type} output to provide feedback on"
            )
        
        # Store feedback
        feedback_id = feedback_service.create_feedback(
            incident_id=incident_id,
            feedback_type=feedback.feedback_type,
            system_output=system_output,
            user_edited=feedback.user_edited,
            notes=feedback.notes
        )
        
        # If user provided user_edited triage_output, update the incident with it
        # This ensures resolution agent uses the user-edited version
        if feedback.feedback_type == "triage" and feedback.user_edited:
            try:
                # Validate user_edited triage output against guardrails before storing
                is_valid, validation_errors = validate_triage_output(feedback.user_edited)
                if not is_valid:
                    error_msg = f"Triage output validation failed: {', '.join(validation_errors)}"
                    logger.error(f"User-edited triage output validation failed: {error_msg}")
                    raise ValidationError(error_msg)
                
                # Validate that user_edited has the same structure (no new fields)
                # Check that all keys in user_edited exist in original system_output
                original_keys = set(system_output.keys())
                user_keys = set(feedback.user_edited.keys())
                if not user_keys.issubset(original_keys):
                    extra_keys = user_keys - original_keys
                    error_msg = f"Cannot add new fields to triage output. Extra fields: {', '.join(extra_keys)}"
                    logger.error(f"User tried to add new fields: {error_msg}")
                    raise ValidationError(error_msg)
                
                incident_service.update_triage_output(incident_id, feedback.user_edited)
                logger.info(f"Triage output updated via feedback: incident_id={incident_id}")
                
                # Verify the update by fetching the incident again
                try:
                    updated_incident = incident_service.get_incident(incident_id)
                    verified_triage_output = updated_incident.get("triage_output")
                    if verified_triage_output != feedback.user_edited:
                        logger.warning(
                            f"Triage output update verification: stored output may differ from user_edited. "
                            f"incident_id={incident_id}"
                        )
                    else:
                        logger.info(
                            f"Triage output update verified successfully: incident_id={incident_id}, "
                            f"updated fields: {list(feedback.user_edited.keys())}"
                        )
                except Exception as verify_err:
                    logger.warning(f"Could not verify triage output update: {str(verify_err)}")
            except ValidationError:
                raise  # Re-raise validation errors
            except Exception as e:
                logger.error(f"Failed to update triage_output after feedback: {str(e)}", exc_info=True)
                raise HTTPException(status_code=400, detail=f"Failed to update triage output: {str(e)}")
        
        # Update policy if:
        # 1. User explicitly provided policy_band (approval workflow)
        # 2. OR triage feedback with feedback_before_policy enabled
        if feedback.policy_band:
            # User is explicitly approving/changing policy band
            if feedback.policy_band not in ["AUTO", "PROPOSE", "REVIEW"]:
                raise ValidationError(f"Invalid policy_band: {feedback.policy_band}. Must be AUTO, PROPOSE, or REVIEW")
            
            # Get triage output (use user_edited if provided, otherwise original)
            triage_output = feedback.user_edited if (feedback.feedback_type == "triage" and feedback.user_edited) else incident.get("triage_output")
            if not triage_output:
                raise ValidationError("Cannot update policy without triage output")
            
            # Log current policy before update
            current_policy_band = incident.get("policy_band")
            current_policy_decision = incident.get("policy_decision")
            logger.info(
                f"Updating policy via feedback: incident_id={incident_id}, "
                f"current_policy_band={current_policy_band}, new_policy_band={feedback.policy_band}"
            )
            
            # Recompute policy decision with the new policy band
            policy_decision = get_policy_from_config(triage_output)
            policy_decision["policy_band"] = feedback.policy_band
            if feedback.policy_band == "AUTO":
                policy_decision["can_auto_apply"] = True
                policy_decision["requires_approval"] = False
            else:
                policy_decision["can_auto_apply"] = False
                policy_decision["requires_approval"] = True
            
            try:
                incident_service.update_policy(incident_id, feedback.policy_band, policy_decision)
                logger.info(
                    f"Policy updated via feedback: incident_id={incident_id}, "
                    f"policy_band={current_policy_band} -> {feedback.policy_band}, "
                    f"can_auto_apply={policy_decision.get('can_auto_apply')}, "
                    f"requires_approval={policy_decision.get('requires_approval')}"
                )
                
                # Verify the update by fetching the incident again
                try:
                    updated_incident = incident_service.get_incident(incident_id)
                    verified_policy_band = updated_incident.get("policy_band")
                    verified_policy_decision = updated_incident.get("policy_decision")
                    if verified_policy_band != feedback.policy_band:
                        logger.error(
                            f"Policy update verification failed: expected {feedback.policy_band}, "
                            f"got {verified_policy_band}"
                        )
                    else:
                        logger.info(
                            f"Policy update verified: policy_band={verified_policy_band}, "
                            f"can_auto_apply={verified_policy_decision.get('can_auto_apply') if verified_policy_decision else None}, "
                            f"requires_approval={verified_policy_decision.get('requires_approval') if verified_policy_decision else None}"
                        )
                except Exception as e:
                    logger.warning(f"Could not verify policy update: {str(e)}")
            except Exception as e:
                # Non-fatal; still return feedback stored
                logger.warning(f"Failed to update policy after feedback: {str(e)}")
        
        elif feedback.feedback_type == "triage":
            # Legacy: If triage feedback and policy was deferred, compute and store policy now
            workflow_cfg = get_workflow_config() or {}
            feedback_before_policy = bool(workflow_cfg.get("feedback_before_policy", False))
            if feedback_before_policy:
                # Evaluate policy on user-edited triage
                policy_decision = get_policy_from_config(feedback.user_edited)
                policy_band = policy_decision.get("policy_band", "REVIEW")
                try:
                    incident_service.update_policy(incident_id, policy_band, policy_decision)
                except Exception as e:
                    # Non-fatal; still return feedback stored
                    logger.warning(f"Failed to update policy after feedback: {str(e)}")
        
        return {
            "feedback_id": feedback_id,
            "incident_id": incident_id,
            "feedback_type": feedback.feedback_type,
            "status": "feedback_stored",
            "updated_at": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except ValidationError as e:
        logger.warning(f"Feedback validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error storing feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error storing feedback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

