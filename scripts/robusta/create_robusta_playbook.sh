#!/bin/bash
# Ensure Homebrew binaries are on PATH for macOS (Apple Silicon default)
export PATH="/opt/homebrew/bin:$PATH"

# Create and deploy Robusta playbook for NOC AI integration

set -e

echo "📝 Creating Robusta Playbook for NOC AI"
echo "======================================="
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

# Create playbook YAML with both triager and resolution copilot agents
PLAYBOOK=$(cat <<EOF
apiVersion: actions.robusta.dev/v1
kind: Playbook
metadata:
  name: noc-ai-agents
  namespace: robusta
spec:
  triggers:
    - on_prometheus_alert:
        alert_name: ".*"
  actions:
    # Step 1: Triager Agent - Analyze and triage the alert
    - custom_action:
        action_name: call_noc_triager
        action_params:
          ai_service_url: "$AI_SERVICE_URL"
    # Step 2: Collect Feedback for Triage
    - custom_action:
        action_name: call_noc_feedback_triage
        action_params:
          ai_service_url: "$AI_SERVICE_URL"
    # Step 3: Resolution Copilot Agent - Generate resolution steps
    - custom_action:
        action_name: call_noc_resolution_copilot
        action_params:
          ai_service_url: "$AI_SERVICE_URL"
          use_incident_id_from_triage: true
    # Step 4: Collect Feedback for Resolution
    - custom_action:
        action_name: call_noc_feedback_resolution
        action_params:
          ai_service_url: "$AI_SERVICE_URL"
---
apiVersion: actions.robusta.dev/v1
kind: CustomAction
metadata:
  name: call-noc-triager
  namespace: robusta
spec:
  python_code: |
    from robusta.api import action, PrometheusAlert
    import requests
    from datetime import datetime, timezone
    
    def build_canonical_alert(event: PrometheusAlert):
        alert = event.alert
        return {
            "alert_id": alert.fingerprint,
            "source": "prometheus",
            "title": alert.name,
            "description": alert.description or alert.summary or "",
            "labels": alert.labels or {},
            "ts": datetime.now(timezone.utc).isoformat()
        }
    
    @action
    def call_noc_triager(event: PrometheusAlert):
        """Triager Agent: Analyzes alert with context from historical data."""
        ai_service_url = event.action_params.get("ai_service_url", "http://localhost:8001")
        payload = build_canonical_alert(event)
        
        try:
            resp = requests.post(f"{ai_service_url}/triage", json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            incident_id = data.get("incident_id")
            triage = data.get("triage", {})
            evidence = data.get("evidence_chunks", {})
            
            # Store incident_id in event for next action
            event.attributes["noc_incident_id"] = incident_id
            
            # Build enrichment message
            enrichment = [
                {
                    "title": " Triager Agent Output",
                    "content": f"""
**Severity:** {triage.get('severity', 'unknown')}
**Category:** {triage.get('category', 'unknown')}
**Confidence:** {triage.get('confidence', 0):.2f}
**Likely Cause:** {triage.get('likely_cause', 'N/A')}
**Summary:** {triage.get('summary', 'N/A')}
**Affected Services:** {', '.join(triage.get('affected_services', []))}
**Incident ID:** {incident_id}
**Evidence Chunks Used:** {evidence.get('chunks_used', 0)}
                    """
                }
            ]
            
            # Add recommended actions if available
            if triage.get("recommended_actions"):
                enrichment.append({
                    "title": "Recommended Actions",
                    "content": "\n".join(f"- {action}" for action in triage.get("recommended_actions", []))
                })
            
            event.add_enrichment(enrichment)
            
        except Exception as e:
            event.add_enrichment([
                {
                    "title": " Triager Agent Error",
                    "content": f"Failed to call AI service: {str(e)}"
                }
            ])
---
apiVersion: actions.robusta.dev/v1
kind: CustomAction
metadata:
  name: call-noc-resolution-copilot
  namespace: robusta
spec:
  python_code: |
    from robusta.api import action, PrometheusAlert
    import requests
    
    @action
    def call_noc_resolution_copilot(event: PrometheusAlert):
        """Resolution Copilot Agent: Generates resolution steps with policy gates."""
        ai_service_url = event.action_params.get("ai_service_url", "http://localhost:8001")
        use_incident_id = event.action_params.get("use_incident_id_from_triage", True)
        
        try:
            # Get incident_id from previous triage action
            incident_id = event.attributes.get("noc_incident_id")
            
            if not incident_id and use_incident_id:
                event.add_enrichment([
                    {
                        "title": " Resolution Copilot Skipped",
                        "content": "No incident_id from triage step. Skipping resolution."
                    }
                ])
                return
            
            # Call resolution endpoint
            if incident_id:
                resp = requests.post(
                    f"{ai_service_url}/resolution?incident_id={incident_id}",
                    timeout=30
                )
            else:
                # Fallback: create from alert (will triage first)
                from datetime import datetime, timezone
                alert = event.alert
                payload = {
                    "alert_id": alert.fingerprint,
                    "source": "prometheus",
                    "title": alert.name,
                    "description": alert.description or alert.summary or "",
                    "labels": alert.labels or {},
                    "ts": datetime.now(timezone.utc).isoformat()
                }
                resp = requests.post(f"{ai_service_url}/resolution", json=payload, timeout=30)
            
            resp.raise_for_status()
            data = resp.json()
            
            resolution = data.get("resolution", {})
            policy = data.get("policy", {})
            policy_band = data.get("policy_band", "UNKNOWN")
            evidence = data.get("evidence_chunks", {})
            
            # Build enrichment message
            enrichment = [
                {
                    "title": " Resolution Copilot Agent Output",
                    "content": f"""
**Policy Band:** {policy_band}
**Risk Level:** {resolution.get('risk_level', 'unknown')}
**Estimated Time:** {resolution.get('estimated_time_minutes', 'N/A')} minutes
**Requires Approval:** {resolution.get('requires_approval', False)}
**Evidence Chunks Used:** {evidence.get('chunks_used', 0)}
                    """
                }
            ]
            
            # Add resolution steps
            if resolution.get("resolution_steps"):
                enrichment.append({
                    "title": "Resolution Steps",
                    "content": "\n".join(f"{i+1}. {step}" for i, step in enumerate(resolution.get("resolution_steps", [])))
                })
            
            # Add commands if available
            if resolution.get("commands"):
                enrichment.append({
                    "title": "Commands",
                    "content": "\n".join(f"```bash\n{cmd}\n```" for cmd in resolution.get("commands", []))
                })
            
            # Add rollback plan if available
            if resolution.get("rollback_plan"):
                enrichment.append({
                    "title": "Rollback Plan",
                    "content": "\n".join(f"- {step}" for step in resolution.get("rollback_plan", []))
                })
            
            # Add policy decision details
            if policy.get("policy_reason"):
                enrichment.append({
                    "title": "Policy Decision",
                    "content": f"**Reason:** {policy.get('policy_reason', 'N/A')}\n**Can Auto Apply:** {policy.get('can_auto_apply', False)}\n**Notification Required:** {policy.get('notification_required', False)}"
                })
            
            event.add_enrichment(enrichment)
            
        except Exception as e:
            event.add_enrichment([
                {
                    "title": " Resolution Copilot Error",
                    "content": f"Failed to call AI service: {str(e)}"
                }
            ])
EOF
)

# Save to file
PLAYBOOK_FILE="/tmp/robusta-noc-playbook.yaml"
echo "$PLAYBOOK" > $PLAYBOOK_FILE

echo " Playbook created: $PLAYBOOK_FILE"
echo ""
echo "This playbook includes:"
echo "   Triager Agent - Analyzes alerts with historical context"
echo "   Feedback Collection (Triage) - Prompts for triage feedback"
echo "   Resolution Copilot Agent - Generates resolution steps with policy gates"
echo "   Feedback Collection (Resolution) - Prompts for resolution approval/edits"
echo ""
echo "To deploy:"
echo "  kubectl apply -f $PLAYBOOK_FILE"
echo ""
echo "Note: Make sure AI service is accessible from Robusta:"
echo "  - Deploy AI service to K8s, OR"
echo "  - Use port-forward: kubectl port-forward svc/noc-ai-service 8001:8001"
echo ""
read -p "Deploy now? (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl apply -f $PLAYBOOK_FILE
    echo ""
    echo " Playbook deployed!"
    echo ""
    echo "Check status:"
    echo "  kubectl get playbooks -n robusta"
    echo "  kubectl get customactions -n robusta"
    echo ""
    echo "View playbook:"
    echo "  kubectl get playbook noc-ai-agents -n robusta -o yaml"
    echo ""
    echo "📝 To add feedback actions, run:"
    echo "  bash scripts/robusta/create_robusta_feedback_actions.sh"
    echo "  kubectl apply -f /tmp/robusta-feedback-actions.yaml"
else
    echo "Playbook saved to $PLAYBOOK_FILE"
    echo "Deploy manually with: kubectl apply -f $PLAYBOOK_FILE"
fi


