#!/usr/bin/env python3
"""Validate triage agent output with test cases."""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ai_service.agents.triager import triage_agent
from ai_service.guardrails import validate_triage_output, validate_triage_no_hallucination, validate_triage_retrieval_boundaries

def validate_triage_result(result: Dict[str, Any], test_case: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a triage result against expected values."""
    validation = {
        "test_case": test_case.get("name", "Unknown"),
        "passed": True,
        "errors": [],
        "warnings": [],
        "details": {}
    }
    
    if "triage" not in result:
        validation["passed"] = False
        validation["errors"].append("Missing 'triage' field in result")
        return validation
    
    triage = result["triage"]
    
    # 1. Validate required fields
    required_fields = ["incident_signature", "matched_evidence", "severity", "confidence", "policy"]
    for field in required_fields:
        if field not in triage:
            validation["passed"] = False
            validation["errors"].append(f"Missing required field: {field}")
        else:
            validation["details"][field] = triage[field]
    
    # 2. Validate incident_signature structure
    if "incident_signature" in triage:
        sig = triage["incident_signature"]
        if not isinstance(sig, dict):
            validation["passed"] = False
            validation["errors"].append("incident_signature must be a dictionary")
        else:
            if "failure_type" not in sig or "error_class" not in sig:
                validation["passed"] = False
                validation["errors"].append("incident_signature must have 'failure_type' and 'error_class'")
            else:
                if sig["failure_type"] == "UNKNOWN_FAILURE":
                    validation["warnings"].append("failure_type is UNKNOWN_FAILURE - may indicate no matching signatures")
                if sig["error_class"] == "UNKNOWN_ERROR":
                    validation["warnings"].append("error_class is UNKNOWN_ERROR - may indicate no matching signatures")
    
    # 3. Validate matched_evidence structure
    if "matched_evidence" in triage:
        evidence = triage["matched_evidence"]
        if not isinstance(evidence, dict):
            validation["passed"] = False
            validation["errors"].append("matched_evidence must be a dictionary")
        else:
            sig_ids = evidence.get("incident_signatures", [])
            rb_refs = evidence.get("runbook_refs", [])
            
            if not isinstance(sig_ids, list):
                validation["passed"] = False
                validation["errors"].append("matched_evidence.incident_signatures must be a list")
            if not isinstance(rb_refs, list):
                validation["passed"] = False
                validation["errors"].append("matched_evidence.runbook_refs must be a list")
            
            validation["details"]["evidence_count"] = {
                "incident_signatures": len(sig_ids),
                "runbook_refs": len(rb_refs)
            }
            
            if len(sig_ids) == 0 and len(rb_refs) == 0:
                validation["warnings"].append("No evidence found - confidence should be 0.0")
    
    # 4. Validate severity
    if "severity" in triage:
        valid_severities = ["critical", "high", "medium", "low"]
        if triage["severity"] not in valid_severities:
            validation["passed"] = False
            validation["errors"].append(f"Invalid severity: {triage['severity']}. Must be one of {valid_severities}")
        
        # Check if severity matches expected (if provided)
        if "expected_severity" in test_case:
            if triage["severity"] != test_case["expected_severity"]:
                validation["warnings"].append(
                    f"Severity mismatch: got '{triage['severity']}', expected '{test_case['expected_severity']}'"
                )
    
    # 5. Validate confidence
    if "confidence" in triage:
        confidence = triage["confidence"]
        if not isinstance(confidence, (int, float)):
            validation["passed"] = False
            validation["errors"].append("confidence must be a number")
        elif confidence < 0.0 or confidence > 1.0:
            validation["passed"] = False
            validation["errors"].append(f"confidence must be between 0.0 and 1.0, got {confidence}")
        
        # Check if confidence matches evidence
        evidence_count = validation["details"].get("evidence_count", {})
        sig_count = evidence_count.get("incident_signatures", 0)
        if sig_count == 0 and confidence > 0.0:
            validation["warnings"].append("Confidence > 0.0 but no incident signatures found")
        elif sig_count > 0 and confidence == 0.0:
            validation["warnings"].append("Confidence is 0.0 but incident signatures were found")
    
    # 6. Validate policy
    if "policy" in triage:
        valid_policies = ["AUTO", "PROPOSE", "REVIEW"]
        if triage["policy"] not in valid_policies:
            validation["passed"] = False
            validation["errors"].append(f"Invalid policy: {triage['policy']}. Must be one of {valid_policies}")
        
        # Policy should be REVIEW if confidence is 0.0
        if triage.get("confidence", 1.0) == 0.0 and triage["policy"] != "REVIEW":
            validation["warnings"].append("Policy should be REVIEW when confidence is 0.0")
    
    # 7. Validate routing (optional but should be present)
    if "routing" in triage:
        if not triage["routing"]:
            validation["warnings"].append("routing field is empty")
    else:
        validation["warnings"].append("routing field is missing (optional but recommended)")
    
    # 8. Use guardrails validation
    try:
        guardrail_result = validate_triage_output(triage)
        # Guardrail functions return (bool, List[str]) tuples
        if isinstance(guardrail_result, tuple):
            is_valid, errors = guardrail_result
            if not is_valid:
                validation["passed"] = False
                validation["errors"].extend(errors)
        elif isinstance(guardrail_result, dict):
            if not guardrail_result.get("valid", False):
                validation["passed"] = False
                validation["errors"].extend(guardrail_result.get("errors", []))
    except Exception as e:
        validation["warnings"].append(f"Guardrail validation failed: {e}")
    
    # 9. Check for hallucination
    if "evidence" in result:
        evidence_data = result["evidence"]
        try:
            hallucination_check = validate_triage_no_hallucination(triage, evidence_data)
            # Guardrail functions return (bool, List[str]) tuples
            if isinstance(hallucination_check, tuple):
                is_valid, errors = hallucination_check
                if not is_valid:
                    validation["passed"] = False
                    validation["errors"].extend(errors)
            elif isinstance(hallucination_check, dict):
                if not hallucination_check.get("valid", False):
                    validation["passed"] = False
                    validation["errors"].extend(hallucination_check.get("errors", []))
        except Exception as e:
            validation["warnings"].append(f"Hallucination check failed: {e}")
        
        # Check retrieval boundaries
        try:
            boundary_check = validate_triage_retrieval_boundaries(evidence_data)
            # Guardrail functions return (bool, List[str]) tuples
            if isinstance(boundary_check, tuple):
                is_valid, errors = boundary_check
                if not is_valid:
                    validation["passed"] = False
                    validation["errors"].extend(errors)
            elif isinstance(boundary_check, dict):
                if not boundary_check.get("valid", False):
                    validation["passed"] = False
                    validation["errors"].extend(boundary_check.get("errors", []))
        except Exception as e:
            validation["warnings"].append(f"Retrieval boundary check failed: {e}")
    
    return validation

def run_test_cases() -> List[Dict[str, Any]]:
    """Run test cases and validate results."""
    
    test_cases = [
        {
            "name": "Database SQL Agent Job Failure",
            "alert": {
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
            },
            "expected_severity": "high"
        },
        {
            "name": "High Disk Usage Alert",
            "alert": {
                "alert_id": "test-disk-alert-001",
                "title": "Volume is Critical",
                "description": "Node: brprlgwc041.int.mgc.com\nVolume brprlgwc041.int.mgc.com-/apps/solr_data:\n  Total size: 132.7 G\n  Free space: 1.4 G\n  Percent used: 99 %",
                "source": "prometheus",
                "category": "disk",
                "labels": {
                    "service": "Server",
                    "component": "Storage",
                    "environment": "production",
                    "severity": "high",
                    "assignment_group": "NOC"
                },
                "ts": "2026-01-01T18:07:33.200Z"
            }
        },
        {
            "name": "Unknown Service Alert",
            "alert": {
                "alert_id": "test-unknown-001",
                "title": "Unknown Alert",
                "description": "This is a test alert for an unknown service that should not match anything",
                "source": "prometheus",
                "category": "unknown",
                "labels": {
                    "service": "UnknownService",
                    "component": "UnknownComponent",
                    "environment": "production",
                    "severity": "medium"
                },
                "ts": "2026-01-01T18:07:33.200Z"
            },
            "expected_confidence": 0.0,
            "expected_policy": "REVIEW"
        }
    ]
    
    results = []
    
    print("="*80)
    print("Triage Agent Validation")
    print("="*80)
    print()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}: {test_case['name']}")
        print("-"*80)
        
        try:
            result = triage_agent(test_case["alert"])
            validation = validate_triage_result(result, test_case)
            
            # Check expected values
            if "expected_confidence" in test_case:
                actual_confidence = result.get("triage", {}).get("confidence", None)
                if actual_confidence != test_case["expected_confidence"]:
                    validation["warnings"].append(
                        f"Confidence mismatch: got {actual_confidence}, expected {test_case['expected_confidence']}"
                    )
            
            if "expected_policy" in test_case:
                actual_policy = result.get("triage", {}).get("policy", None)
                if actual_policy != test_case["expected_policy"]:
                    validation["warnings"].append(
                        f"Policy mismatch: got {actual_policy}, expected {test_case['expected_policy']}"
                    )
            
            validation["result"] = result
            results.append(validation)
            
            # Print summary
            status = "✅ PASS" if validation["passed"] else "❌ FAIL"
            print(f"Status: {status}")
            
            if validation["errors"]:
                print("Errors:")
                for error in validation["errors"]:
                    print(f"  ❌ {error}")
            
            if validation["warnings"]:
                print("Warnings:")
                for warning in validation["warnings"]:
                    print(f"  ⚠️  {warning}")
            
            print(f"Details:")
            for key, value in validation["details"].items():
                print(f"  • {key}: {value}")
            
            print()
            
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "test_case": test_case["name"],
                "passed": False,
                "errors": [f"Exception: {str(e)}"],
                "warnings": [],
                "details": {}
            })
            print()
    
    return results

def generate_report(results: List[Dict[str, Any]]):
    """Generate validation report."""
    print("="*80)
    print("Validation Report Summary")
    print("="*80)
    print()
    
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    
    print(f"Total Test Cases: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print()
    
    if failed > 0:
        print("Failed Test Cases:")
        for result in results:
            if not result["passed"]:
                print(f"  • {result['test_case']}")
                for error in result["errors"]:
                    print(f"    - {error}")
        print()
    
    # Overall statistics
    total_errors = sum(len(r["errors"]) for r in results)
    total_warnings = sum(len(r["warnings"]) for r in results)
    
    print(f"Total Errors: {total_errors}")
    print(f"Total Warnings: {total_warnings}")
    print()
    
    # Evidence statistics
    evidence_stats = {
        "with_signatures": 0,
        "with_runbooks": 0,
        "with_both": 0,
        "with_none": 0
    }
    
    for result in results:
        if "result" in result:
            evidence = result["result"].get("triage", {}).get("matched_evidence", {})
            sig_count = len(evidence.get("incident_signatures", []))
            rb_count = len(evidence.get("runbook_refs", []))
            
            if sig_count > 0 and rb_count > 0:
                evidence_stats["with_both"] += 1
            elif sig_count > 0:
                evidence_stats["with_signatures"] += 1
            elif rb_count > 0:
                evidence_stats["with_runbooks"] += 1
            else:
                evidence_stats["with_none"] += 1
    
    print("Evidence Statistics:")
    print(f"  • Cases with incident signatures: {evidence_stats['with_signatures'] + evidence_stats['with_both']}")
    print(f"  • Cases with runbook refs: {evidence_stats['with_runbooks'] + evidence_stats['with_both']}")
    print(f"  • Cases with both: {evidence_stats['with_both']}")
    print(f"  • Cases with none: {evidence_stats['with_none']}")
    print()
    
    print("="*80)
    
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "evidence_stats": evidence_stats
    }

if __name__ == "__main__":
    results = run_test_cases()
    report = generate_report(results)
    
    # Exit with error code if any tests failed
    if report["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

