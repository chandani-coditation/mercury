#!/usr/bin/env python3
"""Validate all fixes for triage and resolution agents."""

import json
import requests
import sys
from typing import Dict, Any

TRIAGE_SERVICE_URL = "http://localhost:8001"
RESOLUTION_SERVICE_URL = "http://localhost:8001"

def test_triage_agent() -> Dict[str, Any]:
    """Test triage agent with a sample alert."""
    print("\n" + "="*80)
    print("TEST 1: Triage Agent - Validating Fixes")
    print("="*80)
    
    alert = {
        "alert_id": "test-validation-1",
        "title": "MATCHES_KB__Database_Alerts_High_Disk",
        "description": "Database disk usage on primary SQL server has exceeded 90% for the last 20 minutes. Multiple I/O wait alerts observed on the database volume.",
        "source": "prometheus",
        "labels": {
            "service": "Database",
            "component": "Database",
            "cmdb_ci": "Database-SQL",
            "category": "database"
        }
    }
    
    try:
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/triage",
            json=alert,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        triage = result.get("triage", {})
        evidence = result.get("evidence", {})
        
        # Test 1.1: Check matched_evidence.incident_signatures is populated
        matched_evidence = triage.get("matched_evidence", {})
        incident_signatures = matched_evidence.get("incident_signatures", [])
        print(f"\n✓ Test 1.1: matched_evidence.incident_signatures")
        print(f"  Expected: Non-empty array")
        print(f"  Actual: {incident_signatures}")
        test1_1_pass = len(incident_signatures) > 0
        print(f"  Result: {'PASS' if test1_1_pass else 'FAIL'}")
        
        # Test 1.2: Check likely_cause is not empty or "Unknown"
        likely_cause = triage.get("likely_cause", "")
        print(f"\n✓ Test 1.2: likely_cause generation")
        print(f"  Expected: Non-empty string, not 'Unknown (no matching context evidence)'")
        print(f"  Actual: {likely_cause[:100]}..." if len(likely_cause) > 100 else f"  Actual: {likely_cause}")
        test1_2_pass = likely_cause and likely_cause != "Unknown (no matching context evidence)."
        print(f"  Result: {'PASS' if test1_2_pass else 'FAIL'}")
        
        # Test 1.3: Check confidence is not 0 when signatures are found
        confidence = triage.get("confidence", 0)
        print(f"\n✓ Test 1.3: confidence calculation")
        print(f"  Expected: > 0 when signatures are found")
        print(f"  Actual: {confidence}")
        test1_3_pass = confidence > 0 if len(incident_signatures) > 0 else True
        print(f"  Result: {'PASS' if test1_3_pass else 'FAIL'}")
        
        # Test 1.4: Check raw incident descriptions in evidence chunks
        # Note: This will only pass if incidents were ingested as documents, not just signatures
        chunks = evidence.get("chunks", [])
        has_raw_descriptions = False
        for chunk in chunks:
            content = chunk.get("content", "")
            if "Original Incident" in content and ("Title:" in content or "Description:" in content):
                has_raw_descriptions = True
                break
        
        print(f"\n✓ Test 1.4: Raw incident descriptions in chunks")
        print(f"  Expected: At least one chunk contains 'Original Incident' with title/description")
        print(f"  Actual: {'Found' if has_raw_descriptions else 'Not found (incidents may be ingested as signatures only)'}")
        print(f"  Result: {'PASS' if has_raw_descriptions else 'SKIP (expected if incidents ingested as signatures)'}")
        # Mark as pass if we have incident signatures (the important part)
        test1_4_pass = has_raw_descriptions or len(incident_signatures) > 0
        
        # Test 1.5: Check runbook steps in evidence chunks
        has_runbook_steps = False
        for chunk in chunks:
            provenance = chunk.get("provenance", {})
            if provenance.get("source_type") == "runbook_step":
                has_runbook_steps = True
                break
        
        print(f"\n✓ Test 1.5: Runbook steps in evidence chunks")
        print(f"  Expected: At least one chunk with source_type='runbook_step'")
        print(f"  Actual: {'Found' if has_runbook_steps else 'Not found'}")
        print(f"  Result: {'PASS' if has_runbook_steps else 'FAIL'}")
        
        all_tests_pass = all([test1_1_pass, test1_2_pass, test1_3_pass, test1_4_pass := has_raw_descriptions, test1_5_pass := has_runbook_steps])
        
        return {
            "success": True,
            "incident_id": result.get("incident_id"),
            "tests": {
                "matched_evidence_populated": test1_1_pass,
                "likely_cause_generated": test1_2_pass,
                "confidence_calculated": test1_3_pass,
                "raw_descriptions_included": test1_4_pass,
                "runbook_steps_included": test1_5_pass,
            },
            "all_pass": all_tests_pass,
            "result": result
        }
        
    except Exception as e:
        print(f"\n✗ Test 1 FAILED with error: {e}")
        return {"success": False, "error": str(e)}


def test_resolution_agent(incident_id: str) -> Dict[str, Any]:
    """Test resolution agent with incident_id from triage."""
    print("\n" + "="*80)
    print("TEST 2: Resolution Agent - Validating Fixes")
    print("="*80)
    
    try:
        # First, approve the triage to allow resolution
        # Get the current triage output first
        incident_response = requests.get(
            f"{RESOLUTION_SERVICE_URL}/api/v1/incidents/{incident_id}",
            timeout=30
        )
        incident_response.raise_for_status()
        incident_data = incident_response.json()
        triage_output = incident_data.get("triage_output", {})
        
        # Submit feedback with user_edited matching system output but with AUTO policy
        user_edited = triage_output.copy()
        user_edited["policy"] = "AUTO"
        
        feedback_response = requests.put(
            f"{RESOLUTION_SERVICE_URL}/api/v1/incidents/{incident_id}/feedback",
            json={
                "feedback_type": "triage",
                "user_edited": user_edited,
                "policy_band": "AUTO"
            },
            timeout=30
        )
        feedback_response.raise_for_status()
        print(f"\n✓ Approved triage for incident {incident_id}")
        
        # Now call resolution agent
        response = requests.post(
            f"{RESOLUTION_SERVICE_URL}/api/v1/resolution?incident_id={incident_id}",
            timeout=120  # Increased timeout for resolution agent
        )
        response.raise_for_status()
        result = response.json()
        
        resolution = result.get("resolution", {})
        recommendations = resolution.get("recommendations", [])
        overall_confidence = resolution.get("overall_confidence", 0)
        evidence = result.get("evidence", {})
        runbook_steps_count = evidence.get("runbook_steps", 0)
        
        # Test 2.1: Check recommendations are generated
        print(f"\n✓ Test 2.1: Recommendations generation")
        print(f"  Expected: Non-empty recommendations array")
        print(f"  Actual: {len(recommendations)} recommendations")
        test2_1_pass = len(recommendations) > 0
        print(f"  Result: {'PASS' if test2_1_pass else 'FAIL'}")
        
        # Test 2.2: Check overall_confidence is not 0
        print(f"\n✓ Test 2.2: Overall confidence")
        print(f"  Expected: > 0 when recommendations exist")
        print(f"  Actual: {overall_confidence}")
        test2_2_pass = overall_confidence > 0 if len(recommendations) > 0 else True
        print(f"  Result: {'PASS' if test2_2_pass else 'FAIL'}")
        
        # Test 2.3: Check runbook steps were retrieved
        print(f"\n✓ Test 2.3: Runbook steps retrieval")
        print(f"  Expected: > 0 runbook steps retrieved")
        print(f"  Actual: {runbook_steps_count} runbook steps")
        test2_3_pass = runbook_steps_count > 0
        print(f"  Result: {'PASS' if test2_3_pass else 'FAIL'}")
        
        # Test 2.4: Check recommendations have required fields
        if recommendations:
            first_rec = recommendations[0]
            has_step_id = "step_id" in first_rec
            has_action = "action" in first_rec
            has_confidence = "confidence" in first_rec
            has_provenance = "provenance" in first_rec
            
            print(f"\n✓ Test 2.4: Recommendation structure")
            print(f"  Expected: step_id, action, confidence, provenance")
            print(f"  Actual: step_id={has_step_id}, action={has_action}, confidence={has_confidence}, provenance={has_provenance}")
            test2_4_pass = all([has_step_id, has_action, has_confidence, has_provenance])
            print(f"  Result: {'PASS' if test2_4_pass else 'FAIL'}")
        else:
            test2_4_pass = False
            print(f"\n✓ Test 2.4: Recommendation structure")
            print(f"  Result: SKIP (no recommendations)")
        
        all_tests_pass = all([test2_1_pass, test2_2_pass, test2_3_pass, test2_4_pass])
        
        return {
            "success": True,
            "tests": {
                "recommendations_generated": test2_1_pass,
                "overall_confidence_calculated": test2_2_pass,
                "runbook_steps_retrieved": test2_3_pass,
                "recommendation_structure_valid": test2_4_pass,
            },
            "all_pass": all_tests_pass,
            "result": result
        }
        
    except Exception as e:
        print(f"\n✗ Test 2 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def main():
    """Run all validation tests."""
    print("\n" + "="*80)
    print("VALIDATION TEST SUITE - All Fixes")
    print("="*80)
    
    # Test 1: Triage Agent
    triage_result = test_triage_agent()
    
    if not triage_result.get("success"):
        print("\n" + "="*80)
        print("VALIDATION FAILED: Triage agent test failed")
        print("="*80)
        sys.exit(1)
    
    incident_id = triage_result.get("incident_id")
    if not incident_id:
        print("\n" + "="*80)
        print("VALIDATION FAILED: No incident_id returned from triage")
        print("="*80)
        sys.exit(1)
    
    # Test 2: Resolution Agent
    resolution_result = test_resolution_agent(incident_id)
    
    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    print("\nTriage Agent Tests:")
    triage_tests = triage_result.get("tests", {})
    for test_name, passed in triage_tests.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
    
    print("\nResolution Agent Tests:")
    resolution_tests = resolution_result.get("tests", {})
    for test_name, passed in resolution_tests.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
    
    all_triage_pass = triage_result.get("all_pass", False)
    all_resolution_pass = resolution_result.get("all_pass", False)
    
    print("\n" + "="*80)
    if all_triage_pass and all_resolution_pass:
        print("✓ ALL TESTS PASSED")
        print("="*80)
        sys.exit(0)
    else:
        print("✗ SOME TESTS FAILED")
        print("="*80)
        if not all_triage_pass:
            print("  - Triage agent tests failed")
        if not all_resolution_pass:
            print("  - Resolution agent tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

