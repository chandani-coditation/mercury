#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Robusta integration flow without K8s.

This simulates:
1. Prometheus alert → Robusta Playbook
2. Triager Agent (Custom Action) → /api/v1/triage endpoint
3. Resolution Copilot Agent (Custom Action) → /api/v1/resolution endpoint
4. Alert enrichment with AI outputs

No K8s or Robusta installation required!
"""
import sys
import os
import json
import requests
import argparse
from datetime import datetime, timezone
from typing import Dict, Any

# Add project root to path (go up 3 levels: scripts/test -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")


class MockPrometheusAlert:
    """Mock Prometheus alert object (simulates Robusta's PrometheusAlert)."""
    def __init__(self, alert_data: Dict[str, Any]):
        self.fingerprint = alert_data.get("fingerprint", f"alert-{datetime.now().timestamp()}")
        self.name = alert_data.get("name", alert_data.get("title", "Unknown Alert"))
        self.description = alert_data.get("description", "")
        self.summary = alert_data.get("summary", alert_data.get("description", ""))
        self.labels = alert_data.get("labels", {})
        self.annotations = alert_data.get("annotations", {})
        self.starts_at = alert_data.get("starts_at", datetime.now(timezone.utc).isoformat())
        self.ends_at = alert_data.get("ends_at")


class MockRobustaEvent:
    """Mock Robusta event object (simulates Robusta's event with attributes)."""
    def __init__(self, alert: MockPrometheusAlert, action_params: Dict[str, Any] = None):
        self.alert = alert
        self.action_params = action_params or {}
        self.attributes = {}  # For storing data between actions (like incident_id)
        self.enrichments = []  # For storing enrichment messages
    
    def add_enrichment(self, enrichment: list):
        """Add enrichment message (simulates Robusta's alert enrichment)."""
        self.enrichments.extend(enrichment)


def build_canonical_alert(alert: MockPrometheusAlert) -> Dict:
    """
    Build canonical alert format from Prometheus alert.
    This matches the logic in Robusta Custom Action.
    """
    return {
        "alert_id": alert.fingerprint,
        "source": "prometheus",
        "title": alert.name,
        "description": alert.description or alert.summary or "",
        "labels": alert.labels or {},
        "ts": datetime.now(timezone.utc).isoformat()
    }


def call_noc_triager(event: MockRobustaEvent) -> Dict:
    """
    Triager Agent Custom Action (simulated).
    This matches the logic in scripts/robusta/create_robusta_playbook.sh
    """
    print("\n" + "="*80)
    print(" TRIAGER AGENT (Robusta Custom Action - Simulated)")
    print("="*80)
    
    ai_service_url = event.action_params.get("ai_service_url", AI_SERVICE_URL)
    payload = build_canonical_alert(event.alert)
    
    print(f"\n📨 Alert Received:")
    print(f"   Title: {event.alert.name}")
    print(f"   Description: {event.alert.description[:100]}...")
    print(f"   Labels: {event.alert.labels}")
    
    print(f"\n🔗 Calling AI Service: {ai_service_url}/api/v1/triage")
    
    try:
        resp = requests.post(f"{ai_service_url}/api/v1/triage", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        incident_id = data.get("incident_id")
        triage = data.get("triage", {})
        evidence = data.get("evidence_chunks", {})
        policy_band = data.get("policy_band", "UNKNOWN")
        policy_decision = data.get("policy_decision", {})
        
        # Store incident_id in event for next action (Robusta behavior)
        event.attributes["noc_incident_id"] = incident_id
        
        # Build enrichment message (what Robusta would show)
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
**Policy Band:** {policy_band}
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
        
        # Print enrichment (what would appear in Robusta/Slack)
        print(f"\n Triage Complete:")
        print(f"   Incident ID: {incident_id}")
        print(f"   Severity: {triage.get('severity')}")
        print(f"   Category: {triage.get('category')}")
        print(f"   Confidence: {triage.get('confidence'):.2f}")
        print(f"   Policy Band: {policy_band}")
        print(f"   Evidence Chunks: {evidence.get('chunks_used', 0)}")
        
        return {
            "success": True,
            "incident_id": incident_id,
            "triage": triage,
            "policy_band": policy_band
        }
        
    except Exception as e:
        error_msg = f"Failed to call AI service: {str(e)}"
        event.add_enrichment([
            {
                "title": " Triager Agent Error",
                "content": error_msg
            }
        ])
        print(f"\n Error: {error_msg}")
        return {"success": False, "error": error_msg}


def call_noc_resolution_copilot(event: MockRobustaEvent) -> Dict:
    """
    Resolution Copilot Agent Custom Action (simulated).
    This matches the logic in scripts/robusta/create_robusta_playbook.sh
    """
    print("\n" + "="*80)
    print(" RESOLUTION COPILOT AGENT (Robusta Custom Action - Simulated)")
    print("="*80)
    
    ai_service_url = event.action_params.get("ai_service_url", AI_SERVICE_URL)
    use_incident_id = event.action_params.get("use_incident_id_from_triage", True)
    
    # Get incident_id from previous triage action (Robusta behavior)
    incident_id = event.attributes.get("noc_incident_id")
    
    if not incident_id and use_incident_id:
        print("\n No incident_id from triage step. Skipping resolution.")
        event.add_enrichment([
            {
                "title": " Resolution Copilot Skipped",
                "content": "No incident_id from triage step. Skipping resolution."
            }
        ])
        return {"success": False, "error": "No incident_id from triage"}
    
    print(f"\n🔗 Using Incident ID: {incident_id}")
    print(f"🔗 Calling AI Service: {ai_service_url}/api/v1/resolution?incident_id={incident_id}")
    
    try:
        # Call resolution endpoint (matches Robusta behavior)
        if incident_id:
            resp = requests.post(
                f"{ai_service_url}/api/v1/resolution?incident_id={incident_id}",
                timeout=30
            )
        else:
            # Fallback: create from alert (will triage first)
            payload = build_canonical_alert(event.alert)
            resp = requests.post(f"{ai_service_url}/api/v1/resolution", json=payload, timeout=30)
        
        resp.raise_for_status()
        data = resp.json()
        
        # Handle case where resolution is skipped (policy_band is REVIEW)
        if data.get("resolution") is None:
            # Resolution was skipped - this is expected for REVIEW policy band
            message = data.get("message", "Resolution generation skipped")
            policy_band = data.get("policy_band", "UNKNOWN")
            
            enrichment = [
                {
                    "title": " Resolution Copilot Skipped",
                    "content": f"**Policy Band:** {policy_band}\n**Reason:** {message}"
                }
            ]
            event.add_enrichment(enrichment)
            
            print(f"\n Resolution Skipped:")
            print(f"   Policy Band: {policy_band}")
            print(f"   Reason: {message}")
            
            return {
                "success": True,
                "incident_id": incident_id,
                "resolution": None,
                "policy_band": policy_band,
                "skipped": True,
                "message": message
            }
        
        resolution = data.get("resolution") or {}
        policy = data.get("policy") or {}
        policy_band = data.get("policy_band", "UNKNOWN")
        evidence = data.get("evidence_chunks") or {}
        
        # Build enrichment message (what Robusta would show)
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
        if policy:
            policy_reason = policy.get("policy_reason", "N/A")
            enrichment.append({
                "title": "Policy Decision",
                "content": f"**Reason:** {policy_reason}\n**Can Auto Apply:** {policy.get('can_auto_apply', False)}\n**Notification Required:** {policy.get('notification_required', False)}"
            })
        
        event.add_enrichment(enrichment)
        
        # Print enrichment (what would appear in Robusta/Slack)
        print(f"\n Resolution Complete:")
        print(f"   Policy Band: {policy_band}")
        if resolution:
            print(f"   Risk Level: {resolution.get('risk_level', 'unknown')}")
            print(f"   Estimated Time: {resolution.get('estimated_time_minutes', 'N/A')} minutes")
            print(f"   Requires Approval: {resolution.get('requires_approval', False)}")
            print(f"   Resolution Steps: {len(resolution.get('resolution_steps', []))}")
            print(f"   Evidence Chunks: {evidence.get('chunks_used', 0) if evidence else 0}")
            
            if resolution.get("resolution_steps"):
                print(f"\n📋 Resolution Steps:")
                for i, step in enumerate(resolution.get("resolution_steps", []), 1):
                    print(f"   {i}. {step[:80]}...")
        
        return {
            "success": True,
            "incident_id": incident_id,
            "resolution": resolution,
            "policy_band": policy_band
        }
        
    except Exception as e:
        error_msg = f"Failed to call AI service: {str(e)}"
        event.add_enrichment([
            {
                "title": " Resolution Copilot Error",
                "content": error_msg
            }
        ])
        print(f"\n Error: {error_msg}")
        return {"success": False, "error": error_msg}


def _prompt_triage_edits(triage_output: Dict) -> Dict:
    """Interactive prompt to accept/edit/reject triage. Returns edited triage dict or None if rejected."""
    print("\n--- TRIAGE FEEDBACK ---")
    print("[a] Accept  [e] Edit  [r] Reject")
    choice = input("Choose (a/e/r): ").strip().lower() or "a"
    if choice == "r":
        return None
    if choice == "a":
        return triage_output.copy()
    # Edit selected: prompt a few common fields
    edited = triage_output.copy()
    try:
        new_sev = input(f"Severity [{edited.get('severity','')}]: ").strip()
        if new_sev:
            edited["severity"] = new_sev
        new_cat = input(f"Category [{edited.get('category','')}]: ").strip()
        if new_cat:
            edited["category"] = new_cat
        new_sum = input("Summary (leave blank to keep): ")
        if new_sum:
            edited["summary"] = new_sum
        new_cause = input("Likely cause (leave blank to keep): ")
        if new_cause:
            edited["likely_cause"] = new_cause
    except KeyboardInterrupt:
        print("\n(keeping original triage)")
        return triage_output.copy()
    return edited


def call_noc_feedback_triage(event: MockRobustaEvent, incident_id: str, triage_output: Dict, interactive: bool = False) -> Dict:
    """
    Feedback Collection for Triage (simulated Robusta Custom Action).
    This would prompt user in Slack for triage feedback.
    """
    print("\n" + "="*80)
    print("💬 FEEDBACK COLLECTION: TRIAGE (Robusta Custom Action - Simulated)")
    print("="*80)
    
    ai_service_url = event.action_params.get("ai_service_url", AI_SERVICE_URL)
    
    print(f"\n📋 Triage Output (System Generated):")
    print(f"   Severity: {triage_output.get('severity')}")
    print(f"   Category: {triage_output.get('category')}")
    print(f"   Summary: {triage_output.get('summary', '')[:100]}...")
    print(f"   Likely Cause: {triage_output.get('likely_cause', '')[:100]}...")
    
    # In real Robusta, this would show Slack buttons/forms
    # For testing, we can simulate or run interactive
    if interactive:
        user_edited = _prompt_triage_edits(triage_output)
        if user_edited is None:
            print("\n Triage rejected by user. Storing feedback and stopping flow before policy.")
            notes = "Triage rejected via interactive workflow"
        else:
            notes = "Triage accepted/edited via interactive workflow"
    else:
        print(f"\n Simulating user feedback (would be Slack interactive component in real Robusta)")
        user_edited = triage_output.copy()
        notes = "Triage accepted via automated workflow (simulated)"
    
    try:
        feedback_payload = {
            "feedback_type": "triage",
            "user_edited": user_edited if user_edited is not None else triage_output,
            "notes": notes
        }
        
        resp = requests.put(
            f"{ai_service_url}/api/v1/incidents/{incident_id}/feedback",
            json=feedback_payload,
            timeout=10
        )
        resp.raise_for_status()
        feedback_data = resp.json()
        
        print(f"\n Triage Feedback Stored:")
        print(f"   Feedback ID: {feedback_data.get('feedback_id')}")
        print(f"   Feedback Type: {feedback_data.get('feedback_type')}")
        print(f"   Status: {feedback_data.get('status')}")
        
        event.add_enrichment([
            {
                "title": " Triage Feedback Collected",
                "content": f"Feedback stored: {notes}"
            }
        ])
        
        return {"success": True, "feedback_id": feedback_data.get("feedback_id")}
        
    except Exception as e:
        error_msg = f"Failed to store triage feedback: {str(e)}"
        print(f"\n Error: {error_msg}")
        return {"success": False, "error": error_msg}


def _prompt_resolution_edits(resolution_output: Dict) -> Dict:
    """Interactive prompt for resolution approval/edits. Returns edited resolution dict or None if rejected."""
    print("\n--- RESOLUTION FEEDBACK ---")
    print("[a] Approve  [e] Edit  [r] Reject")
    choice = input("Choose (a/e/r): ").strip().lower() or "a"
    if choice == "r":
        return None
    if choice == "a":
        return resolution_output.copy()
    edited = resolution_output.copy()
    try:
        new_risk = input(f"Risk level [{edited.get('risk_level','')}]: ").strip()
        if new_risk:
            edited["risk_level"] = new_risk
        new_time = input(f"Estimated time minutes [{edited.get('estimated_time_minutes','')}]: ").strip()
        if new_time:
            try:
                edited["estimated_time_minutes"] = int(new_time)
            except ValueError:
                pass
        print("Add/override first step (blank to skip):")
        step = input("")
        if step:
            steps = edited.get("resolution_steps", [])
            if steps:
                steps[0] = step
            else:
                steps = [step]
            edited["resolution_steps"] = steps
    except KeyboardInterrupt:
        print("\n(keeping original resolution)")
        return resolution_output.copy()
    return edited


def call_noc_feedback_resolution(event: MockRobustaEvent, incident_id: str, resolution_output: Dict, interactive: bool = False) -> Dict:
    """
    Feedback Collection for Resolution (simulated Robusta Custom Action).
    This would prompt user in Slack for resolution approval/edits.
    """
    print("\n" + "="*80)
    print("💬 FEEDBACK COLLECTION: RESOLUTION (Robusta Custom Action - Simulated)")
    print("="*80)
    
    ai_service_url = event.action_params.get("ai_service_url", AI_SERVICE_URL)
    
    print(f"\n📋 Resolution Output (System Generated):")
    print(f"   Risk Level: {resolution_output.get('risk_level')}")
    print(f"   Estimated Time: {resolution_output.get('estimated_time_minutes')} minutes")
    print(f"   Resolution Steps: {len(resolution_output.get('resolution_steps', []))}")
    if resolution_output.get("resolution_steps"):
        for i, step in enumerate(resolution_output.get("resolution_steps", [])[:3], 1):
            print(f"      {i}. {step[:80]}...")
    
    # In real Robusta, this would show Slack buttons: "Approve", "Edit", "Reject"
    if interactive:
        user_edited = _prompt_resolution_edits(resolution_output)
        if user_edited is None:
            notes = "Resolution rejected via interactive workflow"
        else:
            notes = "Resolution accepted/edited via interactive workflow"
    else:
        print(f"\n Simulating user feedback (would be Slack interactive component in real Robusta)")
        user_edited = resolution_output.copy()
        notes = "Resolution accepted via automated workflow (simulated)"
    
    try:
        feedback_payload = {
            "feedback_type": "resolution",
            "user_edited": user_edited if user_edited is not None else resolution_output,
            "notes": notes
        }
        
        resp = requests.put(
            f"{ai_service_url}/api/v1/incidents/{incident_id}/feedback",
            json=feedback_payload,
            timeout=10
        )
        resp.raise_for_status()
        feedback_data = resp.json()
        
        print(f"\n Resolution Feedback Stored:")
        print(f"   Feedback ID: {feedback_data.get('feedback_id')}")
        print(f"   Feedback Type: {feedback_data.get('feedback_type')}")
        print(f"   Status: {feedback_data.get('status')}")
        print(f"   Resolution marked as accepted")
        
        event.add_enrichment([
            {
                "title": " Resolution Feedback Collected",
                "content": f"Feedback stored and resolution accepted: {notes}"
            }
        ])
        
        return {"success": True, "feedback_id": feedback_data.get("feedback_id")}
        
    except Exception as e:
        error_msg = f"Failed to store resolution feedback: {str(e)}"
        print(f"\n Error: {error_msg}")
        return {"success": False, "error": error_msg}


def simulate_robusta_playbook(alert_data: Dict, ai_service_url: str = None, collect_feedback: bool = True, interactive: bool = False) -> Dict:
    """
    Simulate the complete Robusta playbook flow.
    
    This mimics:
    1. Prometheus alert triggers playbook
    2. Playbook runs Triager Agent (Custom Action)
    3. Playbook runs Resolution Copilot Agent (Custom Action)
    4. Alert is enriched with AI outputs
    """
    print("\n" + "="*80)
    print("🚀 SIMULATING ROBUSTA PLAYBOOK FLOW")
    print("="*80)
    print("\nThis simulates the exact flow that would happen in Robusta:")
    print("  1. Prometheus Alert → Robusta Playbook")
    print("  2. Triager Agent (Custom Action) → /triage")
    print("  3. Feedback Collection (Custom Action) → Prompt for triage feedback")
    print("  4. Resolution Copilot Agent (Custom Action) → /resolution")
    print("  5. Feedback Collection (Custom Action) → Prompt for resolution feedback")
    print("  6. Alert Enrichment with AI Outputs")
    print("="*80)
    
    # Create mock Prometheus alert
    alert = MockPrometheusAlert(alert_data)
    
    # Create mock Robusta event (simulates event passed between actions)
    event = MockRobustaEvent(
        alert=alert,
        action_params={
            "ai_service_url": ai_service_url or AI_SERVICE_URL,
            "use_incident_id_from_triage": True
        }
    )
    
    # Step 1: Run Triager Agent (Custom Action)
    print("\n📋 Step 1: Running Triager Agent (Custom Action)")
    triage_result = call_noc_triager(event)
    
    if not triage_result.get("success"):
        print("\n Playbook stopped: Triager Agent failed")
        return {"success": False, "triage": triage_result}
    
    incident_id = triage_result.get("incident_id")
    triage_output = triage_result.get("triage", {})
    
    # Step 2: Collect Feedback for Triage (Custom Action)
    feedback_triage_result = None
    if collect_feedback:
        print("\n📋 Step 2: Collecting Feedback for Triage (Custom Action)")
        feedback_triage_result = call_noc_feedback_triage(event, incident_id, triage_output, interactive=interactive)
    else:
        print("\n📋 Step 2: Skipping feedback collection (--no-feedback flag)")
    
    # Step 3: Run Resolution Copilot Agent (Custom Action)
    print("\n📋 Step 3: Running Resolution Copilot Agent (Custom Action)")
    resolution_result = call_noc_resolution_copilot(event)
    
    if not resolution_result.get("success"):
        print("\n Resolution Agent failed, but triage completed")
        return {
            "success": True,
            "incident_id": incident_id,
            "triage": triage_result,
            "feedback_triage": feedback_triage_result,
            "resolution": resolution_result,
            "enrichments": event.enrichments
        }
    
    resolution_output = resolution_result.get("resolution")
    
    # Step 4: Collect Feedback for Resolution (Custom Action)
    feedback_resolution_result = None
    if collect_feedback and resolution_output:
        # Only collect feedback if resolution was actually generated (not skipped)
        print("\n📋 Step 4: Collecting Feedback for Resolution (Custom Action)")
        feedback_resolution_result = call_noc_feedback_resolution(event, incident_id, resolution_output, interactive=interactive)
    elif collect_feedback and not resolution_output:
        print("\n📋 Step 4: Skipping resolution feedback (resolution was skipped due to REVIEW policy band)")
    else:
        print("\n📋 Step 4: Skipping feedback collection (--no-feedback flag)")
    
    # Step 5: Show final enrichment (what Robusta would display)
    print("\n" + "="*80)
    print("📊 FINAL ALERT ENRICHMENT (What Robusta Would Show)")
    print("="*80)
    print(f"\nAlert: {alert.name}")
    print(f"Incident ID: {event.attributes.get('noc_incident_id')}")
    print(f"\nEnrichments ({len(event.enrichments)}):")
    for i, enrichment in enumerate(event.enrichments, 1):
        print(f"\n  [{i}] {enrichment.get('title', 'Enrichment')}")
        print(f"      {enrichment.get('content', '')[:200]}...")
    
    return {
        "success": True,
        "incident_id": event.attributes.get("noc_incident_id"),
        "triage": triage_result,
        "feedback_triage": feedback_triage_result,
        "resolution": resolution_result,
        "feedback_resolution": feedback_resolution_result,
        "enrichments": event.enrichments
    }


def main():
    parser = argparse.ArgumentParser(
        description="Test Robusta integration flow without K8s",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with default alert
  python scripts/test/test_robusta_flow.py

  # Test with custom alert
  python scripts/test/test_robusta_flow.py \\
    --title "High CPU Usage" \\
    --service "api-gateway" \\
    --severity "critical"

  # Test with alert from file
  python scripts/test/test_robusta_flow.py --alert-file alert.json

  # Use different AI service URL
  python scripts/test/test_robusta_flow.py --url http://localhost:8001
        """
    )
    parser.add_argument("--title", type=str, help="Alert title")
    parser.add_argument("--description", type=str, help="Alert description")
    parser.add_argument("--service", type=str, help="Service name (for labels)")
    parser.add_argument("--component", type=str, help="Component name (for labels)")
    parser.add_argument("--severity", type=str, choices=["low", "medium", "high", "critical"], help="Alert severity")
    parser.add_argument("--url", type=str, default=AI_SERVICE_URL, help="AI service URL")
    parser.add_argument("--alert-file", type=str, help="JSON file with alert data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--no-feedback", action="store_true", help="Skip feedback collection steps")
    parser.add_argument("--interactive", action="store_true", help="Prompt for triage/resolution feedback interactively")
    
    args = parser.parse_args()
    
    # Load alert data
    if args.alert_file:
        try:
            with open(args.alert_file, 'r') as f:
                alert_data = json.load(f)
        except Exception as e:
            print(f" Error loading alert file: {e}")
            sys.exit(1)
    else:
        # Create default alert
        alert_data = {
            "name": args.title or "High CPU Usage",
            "description": args.description or "CPU usage on api-gateway exceeded 90% for the last 15 minutes.",
            "labels": {
                "service": args.service or "api-gateway",
                "component": args.component or "api",
                "environment": "production",
                "severity": args.severity or "critical",
                "alertname": (args.title or "HighCPUUsage").replace(" ", "")
            },
            "fingerprint": f"alert-{datetime.now().timestamp()}",
            "summary": args.description or "CPU usage on api-gateway exceeded 90% for the last 15 minutes."
        }
    
    # Check AI service health
    print("\n Checking AI service health...")
    try:
        health_resp = requests.get(f"{args.url}/api/v1/health", timeout=5)
        if health_resp.status_code != 200:
            print(f" AI service not healthy: {health_resp.status_code}")
            sys.exit(1)
        print(f" AI service is healthy at {args.url}")
    except requests.exceptions.ConnectionError:
        print(f" Cannot connect to AI service at {args.url}")
        print("   Make sure AI service is running:")
        print("   python -m uvicorn ai_service.main:app --port 8001 --reload")
        sys.exit(1)
    
    # Run simulated Robusta playbook
    collect_feedback = not args.no_feedback
    result = simulate_robusta_playbook(
        alert_data,
        ai_service_url=args.url,
        collect_feedback=collect_feedback,
        interactive=args.interactive,
    )
    
    if result.get("success"):
        print("\n" + "="*80)
        print(" ROBUSTA PLAYBOOK FLOW COMPLETE")
        print("="*80)
        print("\nThis simulated the exact flow that would happen in Robusta:")
        print("   Prometheus alert received")
        print("   Triager Agent executed (Custom Action)")
        if collect_feedback:
            print("   Triage feedback collected (Custom Action)")
        print("   Resolution Copilot Agent executed (Custom Action)")
        if collect_feedback:
            print("   Resolution feedback collected (Custom Action)")
        print("   Alert enriched with AI outputs")
        print("   All feedback stored in database")
        
        if collect_feedback:
            print("\n📊 Feedback Summary:")
            if result.get("feedback_triage"):
                print(f"   Triage feedback: {result.get('feedback_triage', {}).get('feedback_id', 'N/A')}")
            if result.get("feedback_resolution"):
                print(f"   Resolution feedback: {result.get('feedback_resolution', {}).get('feedback_id', 'N/A')}")
        
        print("\n💡 To deploy to real Robusta, run:")
        print("   1. bash scripts/setup/setup_robusta.sh")
        print("   2. bash scripts/robusta/create_robusta_playbook.sh")
        sys.exit(0)
    else:
        print("\n" + "="*80)
        print(" ROBUSTA PLAYBOOK FLOW FAILED")
        print("="*80)
        sys.exit(1)


if __name__ == "__main__":
    main()

