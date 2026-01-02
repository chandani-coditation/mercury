#!/usr/bin/env python3
"""Test triage agent with a sample alert."""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ai_service.agents.triager import triage_agent
from ai_service.models import Alert

def test_triage_agent():
    """Test triage agent with a database alert."""
    
    # Sample alert based on the database alerts CSV
    alert_data = {
        "alert_id": "test-db-alert-001",
        "title": "SentryOne Monitoring/Alert",
        "description": "The job failed. The Job was invoked by Schedule 1056 (Sch1 Capture DB Connections to Table). The last step to run was step 1 (Capture PC DB Connections to UserConnection Table).",
        "source": "prometheus",
        "category": "database",
        "labels": {
            "service": "Database",
            "component": "Database",
            "cmdb_ci": "Database-SQL",
            "category": "database",
            "environment": "production",
            "severity": "high",
            "alertname": "DatabaseDiskUsageHigh",
            "assignment_group": "SE DBA SQL"
        },
        "ts": "2026-01-01T18:07:33.200Z"
    }
    
    print("="*80)
    print("Testing Triage Agent")
    print("="*80)
    print()
    print("Alert:")
    print(json.dumps(alert_data, indent=2))
    print()
    print("Running triage agent...")
    print("-"*80)
    
    try:
        result = triage_agent(alert_data)
        
        print()
        print("Triage Result:")
        print("="*80)
        print(json.dumps(result, indent=2))
        print()
        
        # Validate key fields
        if "triage" in result:
            triage = result["triage"]
            print("Validation:")
            print("-"*80)
            
            required_fields = ["incident_signature", "matched_evidence", "severity", "confidence", "policy"]
            for field in required_fields:
                if field in triage:
                    print(f"  ✅ {field}: {triage[field]}")
                else:
                    print(f"  ❌ Missing {field}")
            
            # Check evidence
            if "matched_evidence" in triage:
                evidence = triage["matched_evidence"]
                sig_count = len(evidence.get("incident_signatures", []))
                rb_count = len(evidence.get("runbook_refs", []))
                print(f"  📊 Evidence: {sig_count} incident signatures, {rb_count} runbook refs")
            
            # Check confidence
            confidence = triage.get("confidence", 0.0)
            if confidence > 0.0:
                print(f"  ✅ Confidence: {confidence:.2f}")
            else:
                print(f"  ⚠️  Confidence is 0.0 - no evidence found")
        
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_triage_agent()

