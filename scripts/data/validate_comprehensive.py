#!/usr/bin/env python3
"""Comprehensive validation of all fixes - Triage, Resolution, and UI data structures."""

import json
import requests
import sys
from typing import Dict, Any, List

TRIAGE_SERVICE_URL = "http://localhost:8001"

def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "="*80)
    print(title)
    print("="*80)

def print_test(name: str, passed: bool, details: str = ""):
    """Print a test result."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n{status}: {name}")
    if details:
        print(f"  {details}")

def validate_triage_agent() -> Dict[str, Any]:
    """Comprehensive validation of triage agent fixes."""
    print_section("TRIAGE AGENT - Comprehensive Validation")
    
    alert = {
        "alert_id": "test-comprehensive-1",
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
    
    results = {
        "tests": {},
        "all_pass": False,
        "result": None
    }
    
    try:
        print("\nCalling triage agent...")
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/triage",
            json=alert,
            timeout=90
        )
        response.raise_for_status()
        result = response.json()
        results["result"] = result
        
        triage = result.get("triage", {})
        evidence = result.get("evidence", {})
        incident_id = result.get("incident_id")
        
        # Test 1: matched_evidence.incident_signatures populated
        matched_evidence = triage.get("matched_evidence", {})
        incident_signatures = matched_evidence.get("incident_signatures", [])
        test1_pass = len(incident_signatures) > 0
        print_test(
            "matched_evidence.incident_signatures populated",
            test1_pass,
            f"Found {len(incident_signatures)} signatures: {incident_signatures[:3]}..."
        )
        results["tests"]["matched_evidence_populated"] = test1_pass
        
        # Test 2: likely_cause generated
        likely_cause = triage.get("likely_cause", "")
        test2_pass = likely_cause and likely_cause != "Unknown (no matching context evidence)."
        print_test(
            "likely_cause generated from evidence",
            test2_pass,
            f"Value: {likely_cause[:100]}..." if len(likely_cause) > 100 else f"Value: {likely_cause}"
        )
        results["tests"]["likely_cause_generated"] = test2_pass
        
        # Test 3: confidence calculated correctly
        confidence = triage.get("confidence", 0)
        test3_pass = confidence > 0 if len(incident_signatures) > 0 else True
        print_test(
            "confidence calculated (not 0 when signatures found)",
            test3_pass,
            f"Value: {confidence} (expected > 0 when {len(incident_signatures)} signatures found)"
        )
        results["tests"]["confidence_calculated"] = test3_pass
        
        # Test 4: incident_signature structure
        incident_signature = triage.get("incident_signature", {})
        has_failure_type = "failure_type" in incident_signature
        has_error_class = "error_class" in incident_signature
        test4_pass = has_failure_type and has_error_class
        print_test(
            "incident_signature structure",
            test4_pass,
            f"failure_type: {incident_signature.get('failure_type')}, error_class: {incident_signature.get('error_class')}"
        )
        results["tests"]["incident_signature_structure"] = test4_pass
        
        # Test 5: impact and urgency
        impact = triage.get("impact")
        urgency = triage.get("urgency")
        test5_pass = impact is not None and urgency is not None
        print_test(
            "impact and urgency present",
            test5_pass,
            f"impact: {impact}, urgency: {urgency}"
        )
        results["tests"]["impact_urgency_present"] = test5_pass
        
        # Test 6: routing
        routing = triage.get("routing")
        test6_pass = routing is not None
        print_test(
            "routing present",
            test6_pass,
            f"routing: {routing}"
        )
        results["tests"]["routing_present"] = test6_pass
        
        # Test 7: severity derived from impact/urgency
        severity = triage.get("severity")
        test7_pass = severity in ["critical", "high", "medium", "low"]
        print_test(
            "severity derived correctly",
            test7_pass,
            f"severity: {severity}"
        )
        results["tests"]["severity_derived"] = test7_pass
        
        # Test 8: Evidence chunks structure
        chunks = evidence.get("chunks", [])
        test8_pass = len(chunks) > 0
        print_test(
            "evidence chunks present",
            test8_pass,
            f"Found {len(chunks)} chunks"
        )
        results["tests"]["evidence_chunks_present"] = test8_pass
        
        # Test 9: Runbook steps in evidence
        has_runbook_steps = any(
            chunk.get("provenance", {}).get("source_type") == "runbook_step"
            for chunk in chunks
        )
        print_test(
            "runbook steps in evidence chunks",
            has_runbook_steps,
            f"Found: {'Yes' if has_runbook_steps else 'No'}"
        )
        results["tests"]["runbook_steps_in_evidence"] = has_runbook_steps
        
        # Test 10: Incident signatures in evidence
        has_incident_sigs = any(
            chunk.get("provenance", {}).get("source_type") == "incident_signature"
            for chunk in chunks
        )
        print_test(
            "incident signatures in evidence chunks",
            has_incident_sigs,
            f"Found: {'Yes' if has_incident_sigs else 'No'}"
        )
        results["tests"]["incident_signatures_in_evidence"] = has_incident_sigs
        
        # Test 11: Chunk content structure
        chunk_content_valid = True
        for chunk in chunks[:3]:  # Check first 3 chunks
            if not chunk.get("content"):
                chunk_content_valid = False
                break
        print_test(
            "chunk content structure valid",
            chunk_content_valid,
            f"All chunks have content field"
        )
        results["tests"]["chunk_content_valid"] = chunk_content_valid
        
        # Test 12: Metadata in chunks
        chunk_metadata_valid = True
        for chunk in chunks[:3]:
            if not chunk.get("metadata"):
                chunk_metadata_valid = False
                break
        print_test(
            "chunk metadata structure valid",
            chunk_metadata_valid,
            f"All chunks have metadata field"
        )
        results["tests"]["chunk_metadata_valid"] = chunk_metadata_valid
        
        # Test 13: Source incident IDs in metadata
        has_source_ids = False
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            if metadata.get("source_incident_ids"):
                has_source_ids = True
                break
        print_test(
            "source_incident_ids in chunk metadata",
            has_source_ids,
            f"Found: {'Yes' if has_source_ids else 'No'}"
        )
        results["tests"]["source_incident_ids_present"] = has_source_ids
        
        # Test 14: Scores in chunks
        has_scores = any(
            chunk.get("scores") is not None
            for chunk in chunks
        )
        print_test(
            "scores in chunks",
            has_scores,
            f"Found: {'Yes' if has_scores else 'No'}"
        )
        results["tests"]["scores_in_chunks"] = has_scores
        
        # Test 15: Runbook metadata structure
        runbook_metadata = evidence.get("runbook_metadata", [])
        test15_pass = len(runbook_metadata) > 0
        print_test(
            "runbook_metadata present",
            test15_pass,
            f"Found {len(runbook_metadata)} runbook metadata entries"
        )
        results["tests"]["runbook_metadata_present"] = test15_pass
        
        # Test 16: Policy band
        policy = triage.get("policy")
        test16_pass = policy in ["AUTO", "PROPOSE", "REVIEW", "PENDING"]
        print_test(
            "policy band set",
            test16_pass,
            f"policy: {policy}"
        )
        results["tests"]["policy_band_set"] = test16_pass
        
        results["all_pass"] = all(results["tests"].values())
        results["incident_id"] = incident_id
        
        return results
        
    except Exception as e:
        print(f"\n✗ TRIAGE VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e), "tests": {}, "all_pass": False}


def validate_resolution_agent(incident_id: str) -> Dict[str, Any]:
    """Comprehensive validation of resolution agent fixes."""
    print_section("RESOLUTION AGENT - Comprehensive Validation")
    
    results = {
        "tests": {},
        "all_pass": False,
        "result": None
    }
    
    try:
        # First, approve the triage
        print("\nApproving triage...")
        incident_response = requests.get(
            f"{TRIAGE_SERVICE_URL}/api/v1/incidents/{incident_id}",
            timeout=30
        )
        incident_response.raise_for_status()
        incident_data = incident_response.json()
        triage_output = incident_data.get("triage_output", {})
        
        user_edited = triage_output.copy()
        user_edited["policy"] = "AUTO"
        
        feedback_response = requests.put(
            f"{TRIAGE_SERVICE_URL}/api/v1/incidents/{incident_id}/feedback",
            json={
                "feedback_type": "triage",
                "user_edited": user_edited,
                "policy_band": "AUTO"
            },
            timeout=30
        )
        feedback_response.raise_for_status()
        print("✓ Triage approved")
        
        # Call resolution agent
        print("\nCalling resolution agent...")
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/resolution?incident_id={incident_id}",
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        results["result"] = result
        
        resolution = result.get("resolution", {})
        recommendations = resolution.get("recommendations", [])
        overall_confidence = resolution.get("overall_confidence", 0)
        risk_level = resolution.get("risk_level", "")
        reasoning = resolution.get("reasoning", "")
        evidence = result.get("evidence", {})
        runbook_steps_count = evidence.get("runbook_steps", 0)
        
        # Test 1: Recommendations generated
        test1_pass = len(recommendations) > 0
        print_test(
            "recommendations generated",
            test1_pass,
            f"Found {len(recommendations)} recommendations"
        )
        results["tests"]["recommendations_generated"] = test1_pass
        
        # Test 2: Overall confidence
        test2_pass = overall_confidence > 0 if len(recommendations) > 0 else True
        print_test(
            "overall_confidence calculated",
            test2_pass,
            f"Value: {overall_confidence}"
        )
        results["tests"]["overall_confidence_calculated"] = test2_pass
        
        # Test 3: Runbook steps retrieved
        test3_pass = runbook_steps_count > 0
        print_test(
            "runbook steps retrieved",
            test3_pass,
            f"Retrieved {runbook_steps_count} runbook steps"
        )
        results["tests"]["runbook_steps_retrieved"] = test3_pass
        
        # Test 4: Recommendation structure
        if recommendations:
            first_rec = recommendations[0]
            has_step_id = "step_id" in first_rec
            has_action = "action" in first_rec
            has_condition = "condition" in first_rec
            has_confidence = "confidence" in first_rec
            has_provenance = "provenance" in first_rec
            has_risk_level = "risk_level" in first_rec
            
            test4_pass = all([has_step_id, has_action, has_confidence, has_provenance])
            print_test(
                "recommendation structure valid",
                test4_pass,
                f"Has: step_id={has_step_id}, action={has_action}, confidence={has_confidence}, provenance={has_provenance}"
            )
        else:
            test4_pass = False
            print_test(
                "recommendation structure valid",
                False,
                "No recommendations to validate"
            )
        results["tests"]["recommendation_structure_valid"] = test4_pass
        
        # Test 5: Risk level
        test5_pass = risk_level in ["low", "medium", "high"]
        print_test(
            "risk_level set",
            test5_pass,
            f"Value: {risk_level}"
        )
        results["tests"]["risk_level_set"] = test5_pass
        
        # Test 6: Reasoning
        test6_pass = len(reasoning) > 0
        print_test(
            "reasoning provided",
            test6_pass,
            f"Length: {len(reasoning)} chars"
        )
        results["tests"]["reasoning_provided"] = test6_pass
        
        # Test 7: Provenance in recommendations
        if recommendations:
            has_provenance = all("provenance" in rec for rec in recommendations)
            test7_pass = has_provenance
            print_test(
                "provenance in all recommendations",
                test7_pass,
                f"All {len(recommendations)} recommendations have provenance"
            )
        else:
            test7_pass = False
            print_test(
                "provenance in all recommendations",
                False,
                "No recommendations"
            )
        results["tests"]["provenance_in_recommendations"] = test7_pass
        
        # Test 8: Confidence values in recommendations
        if recommendations:
            confidences = [rec.get("confidence", 0) for rec in recommendations]
            all_positive = all(c > 0 for c in confidences)
            test8_pass = all_positive
            print_test(
                "confidence values in recommendations",
                test8_pass,
                f"Confidences: {confidences[:3]}..."
            )
        else:
            test8_pass = False
            print_test(
                "confidence values in recommendations",
                False,
                "No recommendations"
            )
        results["tests"]["confidence_in_recommendations"] = test8_pass
        
        results["all_pass"] = all(results["tests"].values())
        
        return results
        
    except Exception as e:
        print(f"\n✗ RESOLUTION VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e), "tests": {}, "all_pass": False}


def validate_ui_data_structure(triage_result: Dict, resolution_result: Dict = None) -> Dict[str, Any]:
    """Validate that data structures are UI-ready."""
    print_section("UI DATA STRUCTURE - Validation")
    
    results = {
        "tests": {},
        "all_pass": False
    }
    
    try:
        triage = triage_result.get("triage", {})
        evidence = triage_result.get("evidence", {})
        
        # Test 1: All required triage fields for UI
        required_triage_fields = [
            "incident_signature", "matched_evidence", "severity", 
            "confidence", "policy", "likely_cause", "impact", "urgency", "routing"
        ]
        missing_fields = [f for f in required_triage_fields if f not in triage]
        test1_pass = len(missing_fields) == 0
        print_test(
            "all required triage fields present",
            test1_pass,
            f"Missing: {missing_fields}" if missing_fields else "All fields present"
        )
        results["tests"]["triage_fields_complete"] = test1_pass
        
        # Test 2: Evidence chunks structure for UI
        chunks = evidence.get("chunks", [])
        chunk_structure_valid = True
        for chunk in chunks[:5]:
            required_chunk_fields = ["chunk_id", "content", "provenance", "metadata"]
            missing = [f for f in required_chunk_fields if f not in chunk]
            if missing:
                chunk_structure_valid = False
                break
        print_test(
            "chunk structure valid for UI",
            chunk_structure_valid,
            f"All chunks have required fields"
        )
        results["tests"]["chunk_structure_valid"] = chunk_structure_valid
        
        # Test 3: Provenance structure
        provenance_valid = True
        for chunk in chunks[:5]:
            provenance = chunk.get("provenance", {})
            if not provenance.get("source_type"):
                provenance_valid = False
                break
        print_test(
            "provenance structure valid",
            provenance_valid,
            f"All chunks have source_type in provenance"
        )
        results["tests"]["provenance_structure_valid"] = provenance_valid
        
        if resolution_result:
            resolution = resolution_result.get("resolution", {})
            recommendations = resolution.get("recommendations", [])
            
            # Test 4: Recommendation structure for UI
            if recommendations:
                rec_structure_valid = True
                for rec in recommendations[:3]:
                    required_rec_fields = ["action", "confidence", "provenance", "risk_level"]
                    missing = [f for f in required_rec_fields if f not in rec]
                    if missing:
                        rec_structure_valid = False
                        break
                print_test(
                    "recommendation structure valid for UI",
                    rec_structure_valid,
                    f"All recommendations have required fields"
                )
            else:
                rec_structure_valid = False
                print_test(
                    "recommendation structure valid for UI",
                    False,
                    "No recommendations"
                )
            results["tests"]["recommendation_structure_ui"] = rec_structure_valid
        
        results["all_pass"] = all(results["tests"].values())
        
        return results
        
    except Exception as e:
        print(f"\n✗ UI VALIDATION FAILED: {e}")
        return {"success": False, "error": str(e), "tests": {}, "all_pass": False}


def main():
    """Run comprehensive validation."""
    print("\n" + "="*80)
    print("COMPREHENSIVE VALIDATION - All Fixes")
    print("="*80)
    
    # Validate Triage Agent
    triage_results = validate_triage_agent()
    
    if not triage_results.get("all_pass", False):
        print_section("VALIDATION FAILED")
        print("Triage agent validation failed. Cannot proceed with resolution validation.")
        sys.exit(1)
    
    incident_id = triage_results.get("incident_id")
    if not incident_id:
        print_section("VALIDATION FAILED")
        print("No incident_id returned from triage.")
        sys.exit(1)
    
    # Validate Resolution Agent
    resolution_results = validate_resolution_agent(incident_id)
    
    # Validate UI Data Structure
    ui_results = validate_ui_data_structure(
        triage_results.get("result", {}),
        resolution_results.get("result") if resolution_results.get("success", True) else None
    )
    
    # Final Summary
    print_section("FINAL VALIDATION SUMMARY")
    
    print("\nTriage Agent Tests:")
    triage_tests = triage_results.get("tests", {})
    for test_name, passed in triage_tests.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
    
    print("\nResolution Agent Tests:")
    resolution_tests = resolution_results.get("tests", {})
    for test_name, passed in resolution_tests.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
    
    print("\nUI Data Structure Tests:")
    ui_tests = ui_results.get("tests", {})
    for test_name, passed in ui_tests.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
    
    all_triage_pass = triage_results.get("all_pass", False)
    all_resolution_pass = resolution_results.get("all_pass", False)
    all_ui_pass = ui_results.get("all_pass", False)
    
    print("\n" + "="*80)
    total_tests = len(triage_tests) + len(resolution_tests) + len(ui_tests)
    passed_tests = sum(triage_tests.values()) + sum(resolution_tests.values()) + sum(ui_tests.values())
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print("="*80)
    
    if all_triage_pass and all_resolution_pass and all_ui_pass:
        print("\n✓ ALL VALIDATIONS PASSED")
        print("="*80)
        return 0
    else:
        print("\n✗ SOME VALIDATIONS FAILED")
        print("="*80)
        if not all_triage_pass:
            print("  - Triage agent: Some tests failed")
        if not all_resolution_pass:
            print("  - Resolution agent: Some tests failed")
        if not all_ui_pass:
            print("  - UI data structure: Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

