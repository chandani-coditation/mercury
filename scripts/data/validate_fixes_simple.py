#!/usr/bin/env python3
"""Simple validation of key fixes."""

import json
import requests
import sys

TRIAGE_SERVICE_URL = "http://localhost:8001"

def main():
    print("\n" + "="*80)
    print("VALIDATION - Key Fixes")
    print("="*80)
    
    alert = {
        "alert_id": "test-validation-simple",
        "title": "MATCHES_KB__Database_Alerts_High_Disk",
        "description": "Database disk usage on primary SQL server has exceeded 90% for the last 20 minutes.",
        "source": "prometheus",
        "labels": {
            "service": "Database",
            "component": "Database",
            "cmdb_ci": "Database-SQL",
            "category": "database"
        }
    }
    
    try:
        print("\nCalling triage agent...")
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/triage",
            json=alert,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        triage = result.get("triage", {})
        evidence = result.get("evidence", {})
        
        print("\n" + "="*80)
        print("VALIDATION RESULTS")
        print("="*80)
        
        # Test 1: matched_evidence.incident_signatures
        matched_evidence = triage.get("matched_evidence", {})
        incident_signatures = matched_evidence.get("incident_signatures", [])
        test1 = len(incident_signatures) > 0
        print(f"\n✓ Test 1: matched_evidence.incident_signatures populated")
        print(f"  Status: {'PASS' if test1 else 'FAIL'}")
        print(f"  Found: {len(incident_signatures)} signatures")
        if incident_signatures:
            print(f"  IDs: {incident_signatures[:3]}...")
        
        # Test 2: likely_cause
        likely_cause = triage.get("likely_cause", "")
        test2 = likely_cause and likely_cause != "Unknown (no matching context evidence)."
        print(f"\n✓ Test 2: likely_cause generated")
        print(f"  Status: {'PASS' if test2 else 'FAIL'}")
        print(f"  Value: {likely_cause[:80]}..." if len(likely_cause) > 80 else f"  Value: {likely_cause}")
        
        # Test 3: confidence
        confidence = triage.get("confidence", 0)
        test3 = confidence > 0 if len(incident_signatures) > 0 else True
        print(f"\n✓ Test 3: confidence calculated")
        print(f"  Status: {'PASS' if test3 else 'FAIL'}")
        print(f"  Value: {confidence}")
        
        # Test 4: runbook steps in evidence
        chunks = evidence.get("chunks", [])
        has_runbook_steps = any(
            chunk.get("provenance", {}).get("source_type") == "runbook_step"
            for chunk in chunks
        )
        print(f"\n✓ Test 4: runbook steps in evidence chunks")
        print(f"  Status: {'PASS' if has_runbook_steps else 'FAIL'}")
        print(f"  Found: {'Yes' if has_runbook_steps else 'No'}")
        
        # Test 5: Check if incident_signatures are in triage output
        has_incident_sigs_in_output = "incident_signatures" in matched_evidence
        print(f"\n✓ Test 5: incident_signatures in matched_evidence")
        print(f"  Status: {'PASS' if has_incident_sigs_in_output else 'FAIL'}")
        
        all_pass = all([test1, test2, test3, has_runbook_steps, has_incident_sigs_in_output])
        
        print("\n" + "="*80)
        if all_pass:
            print("✓ ALL KEY TESTS PASSED")
            print("="*80)
            print("\nSummary:")
            print(f"  - matched_evidence.incident_signatures: {'✓' if test1 else '✗'}")
            print(f"  - likely_cause generation: {'✓' if test2 else '✗'}")
            print(f"  - confidence calculation: {'✓' if test3 else '✗'}")
            print(f"  - runbook steps in evidence: {'✓' if has_runbook_steps else '✗'}")
            print(f"  - incident_signatures in output: {'✓' if has_incident_sigs_in_output else '✗'}")
            return 0
        else:
            print("✗ SOME TESTS FAILED")
            print("="*80)
            return 1
            
    except Exception as e:
        print(f"\n✗ VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

