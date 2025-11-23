"""Calibration endpoints."""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ai_service.services import FeedbackService
from ai_service.core import get_logger

logger = get_logger(__name__)
router = APIRouter()


class CalibrationRequest(BaseModel):
    """Calibration request model."""
    start_date: Optional[str] = None    # ISO8601
    end_date: Optional[str] = None    # ISO8601


@router.post("/calibrate")
def calibrate(req: CalibrationRequest):
    """
    Analyze feedback patterns and suggest configuration improvements.
    
    **Query Parameters:**
    - start_date (optional, ISO8601): Start date for feedback analysis (default: 7 days ago)
    - end_date (optional, ISO8601): End date for feedback analysis (default: now)
    
    **Response:**
    - summary: Feedback statistics
    - suggestions: Configuration improvement suggestions
    """
    try:
        # Parse dates
        if req.start_date:
            start_ts = datetime.fromisoformat(req.start_date.replace('Z', '+00:00'))
        else:
            start_ts = datetime.utcnow() - timedelta(days=7)
        
        if req.end_date:
            end_ts = datetime.fromisoformat(req.end_date.replace('Z', '+00:00'))
        else:
            end_ts = datetime.utcnow()
        
        # Get feedback
        feedback_service = FeedbackService()
        feedback_list = feedback_service.list_feedback_between(start_ts, end_ts)
        
        # Analyze feedback
        triage_feedback = [f for f in feedback_list if f.get("feedback_type") == "triage"]
        resolution_feedback = [f for f in feedback_list if f.get("feedback_type") == "resolution"]
        
        # Generate suggestions (simplified)
        suggestions = {
            "retrieval": {
                "prefer_types": ["runbook", "incident"],
                "max_per_type": {"runbook": 3, "incident": 2}
            },
            "prompt_hints": [],
            "policy_notes": []
        }
        
        # Analyze patterns
        if resolution_feedback:
            # Check if users frequently add rollback steps
            rollback_added = sum(
                1 for f in resolution_feedback
                if "rollback" in str(f.get("user_edited", {})).lower()
                and "rollback" not in str(f.get("system_output", {})).lower()
            )
            if rollback_added > len(resolution_feedback) * 0.3:
                suggestions["prompt_hints"].append(
                    "Users frequently add rollback steps to resolution outputs"
                )
        
        if triage_feedback:
            # Check if users frequently modify affected_services
            services_modified = sum(
                1 for f in triage_feedback
                if f.get("user_edited", {}).get("affected_services")
                != f.get("system_output", {}).get("affected_services")
            )
            if services_modified > len(triage_feedback) * 0.3:
                suggestions["prompt_hints"].append(
                    "Triage outputs often need more specific affected_services"
                )
            
            # Check if users frequently modify likely_cause
            cause_modified = sum(
                1 for f in triage_feedback
                if f.get("user_edited", {}).get("likely_cause")
                and f.get("user_edited", {}).get("likely_cause")
                != f.get("system_output", {}).get("likely_cause")
            )
            if cause_modified > len(triage_feedback) * 0.3:
                suggestions["prompt_hints"].append(
                    "Triage outputs often need more accurate likely_cause analysis"
                )
            
            # Check if users frequently modify confidence
            confidence_adjusted = sum(
                1 for f in triage_feedback
                if f.get("user_edited", {}).get("confidence")
                and abs(f.get("user_edited", {}).get("confidence", 0) - f.get("system_output", {}).get("confidence", 0)) > 0.1
            )
            if confidence_adjusted > len(triage_feedback) * 0.3:
                suggestions["prompt_hints"].append(
                    "Triage confidence scores often need adjustment - consider recalibrating confidence thresholds"
                )
            
            # Note: Updated triage_output is stored in incidents table
            # For future similar incidents to use updated triage_output, resolved incidents should be ingested as documents
            suggestions["policy_notes"].append(
                "Note: User-edited triage_output is stored in incidents table. "
                "To enable future similar alerts to benefit from these updates, consider ingesting resolved incidents as documents."
            )
        
        return {
            "summary": {
                "total_feedback": len(feedback_list),
                "triage_feedback": len(triage_feedback),
                "resolution_feedback": len(resolution_feedback),
                "date_range": {
                    "start": start_ts.isoformat(),
                    "end": end_ts.isoformat()
                }
            },
            "suggestions": suggestions
        }
    
    except ValueError as e:
        logger.warning(f"Calibration validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.error(f"Calibration error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

