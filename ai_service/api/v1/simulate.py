"""Simulation endpoints for testing."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from ai_service.models import Alert, FeedbackInput
from ai_service.agents import triage_agent, resolution_copilot_agent
from ai_service.services import FeedbackService
from ai_service.core import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/simulate-robusta-flow")
def simulate_robusta_flow(
    alert_data: dict,
    collect_feedback: bool = True
):
    """
    Simulate complete Robusta playbook flow without K8s.
    
    This endpoint accepts Prometheus-style alert data and runs the complete flow:
    1. Triage Agent → /triage
    2. Feedback Collection (Triage) → /incidents/{id}/feedback
    3. Resolution Copilot Agent → /resolution
    4. Feedback Collection (Resolution) → /incidents/{id}/feedback
    
    This allows you to use the POC via API without needing Kubernetes or Robusta.
    
    **Request Body:**
    ```json
    {
        "name": "High CPU Usage",
        "description": "CPU usage exceeded 90%",
        "labels": {
            "service": "api-gateway",
            "component": "api",
            "severity": "critical"
        },
        "collect_feedback": true
    }
    ```
    
    **Response:**
    ```json
    {
        "success": true,
        "incident_id": "uuid",
        "triage": {...},
        "resolution": {...},
        "feedback_triage": {...},
        "feedback_resolution": {...},
        "enrichments": [...]
    }
    ```
    """
    try:
        # Build canonical alert format (same as Robusta Custom Action)
        canonical_alert = {
            "alert_id": alert_data.get("fingerprint", f"alert-{datetime.now(timezone.utc).timestamp()}"),
            "source": "prometheus",
            "title": alert_data.get("name", alert_data.get("title", "Unknown Alert")),
            "description": alert_data.get("description", alert_data.get("summary", "")),
            "labels": alert_data.get("labels", {}),
            "ts": datetime.now(timezone.utc).isoformat()
        }
        
        # Convert to Alert model
        alert = Alert(**canonical_alert)
        
        results = {
            "success": False,
            "incident_id": None,
            "triage": None,
            "resolution": None,
            "feedback_triage": None,
            "feedback_resolution": None,
            "enrichments": []
        }
        
        # Step 1: Triage Agent
        alert_dict = alert.model_dump()
        alert_dict["ts"] = alert.ts.isoformat() if isinstance(alert.ts, datetime) else alert.ts
        
        triage_result = triage_agent(alert_dict)
        incident_id = triage_result["incident_id"]
        triage_output = triage_result["triage"]
        policy_band = triage_result["policy_band"]
        policy_decision = triage_result["policy_decision"]
        
        results["incident_id"] = incident_id
        results["triage"] = triage_output
        results["enrichments"].append({
            "title": "🤖 Triager Agent Output",
            "content": f"Severity: {triage_output.get('severity')}, Category: {triage_output.get('category')}, Policy Band: {policy_band}"
        })
        
        # Step 2: Feedback Collection (Triage)
        if collect_feedback:
            feedback_service = FeedbackService()
            feedback_triage_input = FeedbackInput(
                feedback_type="triage",
                user_edited=triage_output.copy(),
                notes="Triage accepted via API simulation"
            )
            
            feedback_triage_result = feedback_service.create_feedback(
                incident_id=incident_id,
                feedback_type=feedback_triage_input.feedback_type,
                system_output=triage_output,
                user_edited=feedback_triage_input.user_edited,
                notes=feedback_triage_input.notes
            )
            
            results["feedback_triage"] = {
                "feedback_id": feedback_triage_result,
                "incident_id": incident_id,
                "feedback_type": "triage",
                "status": "feedback_stored"
            }
            results["enrichments"].append({
                "title": "✅ Triage Feedback Collected",
                "content": "Feedback stored successfully"
            })
        
        # Step 3: Resolution Copilot Agent (only if not REVIEW)
        if policy_band != "REVIEW":
            # Call resolution copilot agent
            resolution_result = resolution_copilot_agent(incident_id=incident_id)
            resolution_output = resolution_result["resolution"]
            
            results["resolution"] = resolution_output
            results["enrichments"].append({
                "title": "🛠️ Resolution Copilot Agent Output",
                "content": f"Risk Level: {resolution_output.get('risk_level')}, Steps: {len(resolution_output.get('resolution_steps', []))}"
            })
            
            # Step 4: Feedback Collection (Resolution)
            if collect_feedback:
                feedback_service = FeedbackService()
                feedback_resolution_input = FeedbackInput(
                    feedback_type="resolution",
                    user_edited=resolution_output.copy(),
                    notes="Resolution accepted via API simulation"
                )
                
                feedback_resolution_result = feedback_service.create_feedback(
                    incident_id=incident_id,
                    feedback_type=feedback_resolution_input.feedback_type,
                    system_output=resolution_output,
                    user_edited=feedback_resolution_input.user_edited,
                    notes=feedback_resolution_input.notes
                )
                
                results["feedback_resolution"] = {
                    "feedback_id": feedback_resolution_result,
                    "incident_id": incident_id,
                    "feedback_type": "resolution",
                    "status": "feedback_stored"
                }
                results["enrichments"].append({
                    "title": "✅ Resolution Feedback Collected",
                    "content": "Feedback stored and resolution accepted"
                })
        else:
            # Resolution was skipped (REVIEW policy band)
            results["enrichments"].append({
                "title": "⚠️ Resolution Copilot Skipped",
                "content": f"Policy Band: {policy_band}. Manual review required."
            })
        
        results["success"] = True
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simulation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

