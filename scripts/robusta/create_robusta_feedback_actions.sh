#!/bin/bash
# Ensure Homebrew binaries are on PATH for macOS (Apple Silicon default)
export PATH="/opt/homebrew/bin:$PATH"

# Create and deploy Robusta feedback collection custom actions

set -e

echo "📝 Creating Robusta Feedback Collection Custom Actions"
echo "======================================================"
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo " kubectl is not installed"
    exit 1
fi

# Get AI service URL
AI_SERVICE_URL=${AI_SERVICE_URL:-"http://noc-ai-service.noc.svc.cluster.local:8001"}

echo "AI Service URL: $AI_SERVICE_URL"
echo ""

# Create feedback custom actions YAML
FEEDBACK_ACTIONS=$(cat <<EOF
---
apiVersion: actions.robusta.dev/v1
kind: CustomAction
metadata:
  name: call-noc-feedback-triage
  namespace: robusta
spec:
  python_code: |
    from robusta.api import action, PrometheusAlert
    import requests
    
    @action
    def call_noc_feedback_triage(event: PrometheusAlert):
        """Feedback Collection: Prompt user for triage feedback."""
        ai_service_url = event.action_params.get("ai_service_url", "http://localhost:8001")
        incident_id = event.attributes.get("noc_incident_id")
        
        if not incident_id:
            event.add_enrichment([
                {
                    "title": " Feedback Collection Skipped",
                    "content": "No incident_id available for feedback collection"
                }
            ])
            return
        
        # Get triage output from incident
        try:
            resp = requests.get(f"{ai_service_url}/incidents/{incident_id}", timeout=10)
            resp.raise_for_status()
            incident = resp.json()
            triage_output = incident.get("triage_output", {})
        except Exception as e:
            event.add_enrichment([
                {
                    "title": " Feedback Collection Error",
                    "content": f"Failed to get incident: {str(e)}"
                }
            ])
            return
        
        # Build Slack message with interactive buttons
        enrichment = [
            {
                "title": "💬 Triage Feedback Request",
                "content": f"""
**Triage Output Review:**

**Severity:** {triage_output.get('severity', 'unknown')}
**Category:** {triage_output.get('category', 'unknown')}
**Summary:** {triage_output.get('summary', 'N/A')}
**Likely Cause:** {triage_output.get('likely_cause', 'N/A')}

**Please review and provide feedback:**
- Click "Accept" if triage is correct
- Click "Edit" to provide corrections
- Use "Notes" to add additional context
                """
            }
        ]
        
        # In real Robusta, you would add Slack interactive buttons here
        # For now, we just show the enrichment
        event.add_enrichment(enrichment)
        
        # Note: Actual feedback submission would be handled by
        # Slack button click handler that calls /incidents/{id}/feedback endpoint

---
apiVersion: actions.robusta.dev/v1
kind: CustomAction
metadata:
  name: call-noc-feedback-resolution
  namespace: robusta
spec:
  python_code: |
    from robusta.api import action, PrometheusAlert
    import requests
    
    @action
    def call_noc_feedback_resolution(event: PrometheusAlert):
        """Feedback Collection: Prompt user for resolution approval/edits."""
        ai_service_url = event.action_params.get("ai_service_url", "http://localhost:8001")
        incident_id = event.attributes.get("noc_incident_id")
        
        if not incident_id:
            event.add_enrichment([
                {
                    "title": " Feedback Collection Skipped",
                    "content": "No incident_id available for feedback collection"
                }
            ])
            return
        
        # Get resolution output from incident
        try:
            resp = requests.get(f"{ai_service_url}/incidents/{incident_id}", timeout=10)
            resp.raise_for_status()
            incident = resp.json()
            resolution_output = incident.get("resolution_output", {})
            policy_band = incident.get("policy_band", "UNKNOWN")
        except Exception as e:
            event.add_enrichment([
                {
                    "title": " Feedback Collection Error",
                    "content": f"Failed to get incident: {str(e)}"
                }
            ])
            return
        
        # Build Slack message with interactive buttons
        enrichment = [
            {
                "title": "💬 Resolution Feedback Request",
                "content": f"""
**Resolution Output Review:**

**Policy Band:** {policy_band}
**Risk Level:** {resolution_output.get('risk_level', 'unknown')}
**Estimated Time:** {resolution_output.get('estimated_time_minutes', 'N/A')} minutes
**Requires Approval:** {resolution_output.get('requires_approval', False)}

**Resolution Steps:**
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(resolution_output.get('resolution_steps', [])[:5]))}

**Please review and provide feedback:**
- Click "Approve" if resolution is correct
- Click "Edit" to modify resolution steps
- Click "Reject" if resolution is not suitable
- Use "Notes" to add additional context
                """
            }
        ]
        
        # In real Robusta, you would add Slack interactive buttons here
        # For now, we just show the enrichment
        event.add_enrichment(enrichment)
        
        # Note: Actual feedback submission would be handled by
        # Slack button click handler that calls /incidents/{id}/feedback endpoint
EOF
)

FEEDBACK_FILE="/tmp/robusta-feedback-actions.yaml"
echo "$FEEDBACK_ACTIONS" > "$FEEDBACK_FILE"

echo " Created feedback actions YAML: $FEEDBACK_FILE"
echo ""
echo "📋 Feedback Actions Created:"
echo "  - call-noc-feedback-triage: Prompts for triage feedback"
echo "  - call-noc-feedback-resolution: Prompts for resolution approval/edits"
echo ""
echo "📝 To deploy:"
echo "  kubectl apply -f $FEEDBACK_FILE"
echo ""
echo "📝 To update playbook to include feedback actions:"
echo "  Edit scripts/robusta/create_robusta_playbook.sh"
echo "  Add feedback actions after triage and resolution agents"
echo ""
echo "  Note: These actions show enrichment messages."
echo "   For full Slack integration, add interactive button handlers"
echo "   that call the /incidents/{id}/feedback endpoint."


