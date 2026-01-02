#!/usr/bin/env python3
"""Validate triage agent output against ARCHITECTURE_LOCK.md requirements.

This script validates that the triage agent:
1. Follows the output contract (Section 5.5)
2. Does NOT violate constraints (Section 5.4)
3. Correctly classifies incidents with proper evidence
4. Matches expected values from historical tickets

Per ARCHITECTURE_LOCK.md Section 5:
- Triage agent ONLY classifies incidents
- Output must include: incident_signature, matched_evidence, severity, confidence, policy
- MUST NOT generate resolution steps, rank actions, or invent causes
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
import requests
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ai_service.core import get_field_mappings_config, get_logger, setup_logging
from ai_service.models import Alert

# Setup logging
setup_logging(log_level="INFO", service_name="triage_architecture_validation")
logger = get_logger(__name__)

# Default service URLs
TRIAGE_SERVICE_URL = "http://localhost:8001"


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse ServiceNow date format."""
    if not date_str or date_str.strip() == "":
        return None

    formats = [
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def csv_row_to_alert(row: Dict, field_mappings: Dict) -> Alert:
    """Convert CSV row to Alert object."""
    mappings = field_mappings.get("field_mappings", {})

    incident_id = row.get(mappings.get("incident_id", {}).get("source_column", "number"), "")
    title = row.get(mappings.get("title", {}).get("source_column", "short_description"), "")
    description = row.get(mappings.get("description", {}).get("source_column", "description"), "")
    category = row.get(mappings.get("category", {}).get("source_column", "category"), "")

    # Parse timestamp
    timestamp = None
    timestamp_col = mappings.get("timestamp", {}).get("source_column", "opened_at")
    if timestamp_col in row:
        timestamp = parse_date(row[timestamp_col])

    # Extract affected services
    affected_services = []
    cmdb_ci = row.get(mappings.get("affected_services", {}).get("source_column", "cmdb_ci"), "")
    if cmdb_ci:
        affected_services = [cmdb_ci]

    # Build labels (for routing extraction)
    labels = {
        "type": "historical_incident",
        "ticket_id": incident_id,
        "category": category,
        "assignment_group": row.get(
            mappings.get("assignment_group", {}).get("source_column", "assignment_group"), ""
        ),
        "impact": row.get(mappings.get("impact", {}).get("source_column", "impact"), ""),
        "urgency": row.get(mappings.get("urgency", {}).get("source_column", "urgency"), ""),
    }

    return Alert(
        alert_id=incident_id,
        title=title,
        description=description,
        severity=None,  # Will be determined by triage agent
        category=category,
        affected_services=affected_services,
        labels=labels,
        ts=timestamp,
        source="servicenow",
    )


def call_triage_agent(alert: Alert) -> Dict:
    """Call triage agent API."""
    try:
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/triage",
            json=alert.model_dump(mode="json", exclude_none=True),
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        # Extract triage output from nested structure if present
        if "triage" in result:
            return result["triage"]
        return result
    except Exception as e:
        logger.error(f"Failed to call triage agent: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
        raise


def validate_architecture_compliance(triage_output: Dict) -> Dict:
    """
    Validate triage output against ARCHITECTURE_LOCK.md Section 5.5.
    
    Required fields per architecture:
    - incident_signature: {failure_type, error_class}
    - matched_evidence: {incident_signatures[], runbook_refs[]}
    - severity: string
    - confidence: float (0.0-1.0)
    - policy: string (AUTO|PROPOSE|REVIEW)
    """
    violations = []
    warnings = []
    evidence = {}

    # Check required structure (Section 5.5)
    if "incident_signature" not in triage_output:
        violations.append("Missing required field: incident_signature")
    else:
        sig = triage_output["incident_signature"]
        if "failure_type" not in sig:
            violations.append("Missing required field: incident_signature.failure_type")
        else:
            evidence["failure_type"] = sig["failure_type"]
        
        if "error_class" not in sig:
            violations.append("Missing required field: incident_signature.error_class")
        else:
            evidence["error_class"] = sig["error_class"]

    if "matched_evidence" not in triage_output:
        violations.append("Missing required field: matched_evidence")
    else:
        ev = triage_output["matched_evidence"]
        if "incident_signatures" not in ev:
            violations.append("Missing required field: matched_evidence.incident_signatures")
        else:
            sig_ids = ev["incident_signatures"]
            if not isinstance(sig_ids, list):
                violations.append("matched_evidence.incident_signatures must be a list")
            elif len(sig_ids) == 0:
                warnings.append("No incident signatures matched (empty list)")
            else:
                evidence["matched_signatures"] = f"✓ Matched {len(sig_ids)} signature(s)"
        
        if "runbook_refs" not in ev:
            warnings.append("No runbook_refs in matched_evidence (optional but recommended)")
        else:
            runbook_refs = ev["runbook_refs"]
            if isinstance(runbook_refs, list) and len(runbook_refs) > 0:
                evidence["runbook_refs"] = f"✓ Matched {len(runbook_refs)} runbook(s)"

    if "severity" not in triage_output:
        violations.append("Missing required field: severity")
    else:
        severity = triage_output["severity"]
        if severity not in ["critical", "high", "medium", "low"]:
            violations.append(f"Invalid severity value: {severity} (must be critical|high|medium|low)")
        else:
            evidence["severity"] = f"✓ Severity: {severity}"

    if "confidence" not in triage_output:
        violations.append("Missing required field: confidence")
    else:
        confidence = triage_output["confidence"]
        if not isinstance(confidence, (int, float)):
            violations.append(f"Confidence must be a number, got: {type(confidence)}")
        elif confidence < 0.0 or confidence > 1.0:
            violations.append(f"Confidence out of range: {confidence} (must be 0.0-1.0)")
        else:
            if confidence >= 0.7:
                evidence["confidence"] = f"✓ High confidence: {confidence:.2f}"
            elif confidence >= 0.5:
                warnings.append(f"Moderate confidence: {confidence:.2f}")
            else:
                warnings.append(f"Low confidence: {confidence:.2f}")

    if "policy" not in triage_output:
        violations.append("Missing required field: policy")
    else:
        policy = triage_output["policy"]
        if policy not in ["AUTO", "PROPOSE", "REVIEW", "PENDING"]:
            violations.append(f"Invalid policy value: {policy} (must be AUTO|PROPOSE|REVIEW|PENDING)")
        else:
            evidence["policy"] = f"✓ Policy: {policy}"

    # Check for forbidden content (Section 5.4)
    forbidden_fields = ["recommendations", "steps", "actions", "root_cause", "fixes"]
    for field in forbidden_fields:
        if field in triage_output:
            violations.append(f"FORBIDDEN: Triage agent must not output '{field}' (Section 5.4)")

    # Check routing (optional but should be present if assignment_group in alert)
    if "routing" in triage_output:
        evidence["routing"] = f"✓ Routing: {triage_output['routing']}"

    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "evidence": evidence,
    }


def validate_against_expected(
    triage_output: Dict, expected_assignment_group: str, expected_impact: str, expected_urgency: str
) -> Dict:
    """Validate triage output matches expected values from ticket."""
    results = {
        "passed": True,
        "errors": [],
        "warnings": [],
    }

    # Check routing matches expected assignment_group
    routing = triage_output.get("routing", "")
    if routing:
        if routing.lower() != expected_assignment_group.lower():
            results["errors"].append(
                f"Routing mismatch: expected '{expected_assignment_group}', got '{routing}'"
            )
            results["passed"] = False
    else:
        results["warnings"].append("No routing (assignment_group) provided")

    # Check severity is reasonable (derived from impact/urgency)
    severity = triage_output.get("severity", "")
    if severity:
        # High impact + high urgency should be critical or high
        if "1 - High" in expected_impact and "1 - High" in expected_urgency:
            if severity not in ["critical", "high"]:
                results["warnings"].append(
                    f"Severity '{severity}' seems low for impact/urgency 1-1"
                )
    else:
        results["errors"].append("Missing severity")
        results["passed"] = False

    return results


def validate_ticket(
    row: Dict, field_mappings: Dict, row_num: int
) -> Dict:
    """Validate a single ticket against architecture requirements."""
    incident_id = row.get("number", f"row_{row_num}")
    title = row.get("short_description", "")[:60]
    expected_assignment_group = row.get("assignment_group", "")
    expected_impact = row.get("impact", "")
    expected_urgency = row.get("urgency", "")

    try:
        # Convert to Alert
        alert = csv_row_to_alert(row, field_mappings)

        # Call triage agent
        triage_output = call_triage_agent(alert)

        # Validate architecture compliance
        arch_validation = validate_architecture_compliance(triage_output)

        # Validate against expected values
        expected_validation = validate_against_expected(
            triage_output, expected_assignment_group, expected_impact, expected_urgency
        )

        # Combine results
        passed = arch_validation["compliant"] and expected_validation["passed"]
        all_errors = arch_validation["violations"] + expected_validation["errors"]
        all_warnings = arch_validation["warnings"] + expected_validation["warnings"]

        return {
            "incident_id": incident_id,
            "title": title,
            "passed": passed,
            "architecture_compliant": arch_validation["compliant"],
            "expected_match": expected_validation["passed"],
            "errors": all_errors,
            "warnings": all_warnings,
            "evidence": arch_validation["evidence"],
            "triage_output": triage_output,
        }

    except Exception as e:
        return {
            "incident_id": incident_id,
            "title": title,
            "passed": False,
            "architecture_compliant": False,
            "expected_match": False,
            "errors": [f"Error calling triage agent: {str(e)}"],
            "warnings": [],
            "evidence": {},
            "triage_output": None,
        }


def main():
    global TRIAGE_SERVICE_URL
    
    parser = argparse.ArgumentParser(
        description="Validate triage agent against ARCHITECTURE_LOCK.md requirements"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="CSV file to validate (default: both ticket files)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=10,
        help="Number of sample tickets to test (default: 10)",
    )
    parser.add_argument(
        "--triage-url",
        type=str,
        default=TRIAGE_SERVICE_URL,
        help=f"Triage service URL (default: {TRIAGE_SERVICE_URL})",
    )

    args = parser.parse_args()

    if args.triage_url:
        TRIAGE_SERVICE_URL = args.triage_url

    print("=" * 70)
    print("Triage Agent Architecture Validation")
    print("Validating against ARCHITECTURE_LOCK.md Section 5")
    print("=" * 70)

    # Load field mappings
    try:
        print("\n Loading field mappings configuration...")
        field_mappings_config = get_field_mappings_config()
        servicenow_mappings = field_mappings_config.get("servicenow_csv", {})
        print(" Configuration loaded successfully\n")
    except Exception as e:
        print(f" Failed to load field mappings: {str(e)}")
        logger.error(f"Failed to load field mappings: {str(e)}")
        sys.exit(1)

    # Determine which files to validate
    if args.file:
        csv_files = [Path(args.file)]
    else:
        tickets_dir = project_root / "tickets_data"
        csv_files = [
            tickets_dir / "updated high disk filtered - Sheet1.csv",
            tickets_dir / "updated database alerts filtered - Sheet1.csv",
        ]

    all_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "architecture_violations": 0,
        "expected_mismatches": 0,
        "details": [],
    }

    for csv_file in csv_files:
        if not csv_file.exists():
            print(f"\n⚠ CSV file not found: {csv_file}")
            continue

        print(f"\n{'='*70}")
        print(f"Validating: {csv_file.name}")
        print(f"{'='*70}\n")

        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                total_rows = len(rows)

                # Select sample tickets
                sample_indices = list(range(min(args.num_samples, total_rows)))
                samples = [rows[i] for i in sample_indices]

                print(f"  Processing {len(samples)} sample ticket(s) from {total_rows} total...\n")

                for idx, row in enumerate(samples, 1):
                    result = validate_ticket(row, servicenow_mappings, idx)
                    all_results["total"] += 1

                    print(f"  [{idx}/{len(samples)}] {result['incident_id']}: {result['title']}...")

                    if result["passed"]:
                        all_results["passed"] += 1
                        print(f"      ✓ PASSED (Architecture compliant + Expected match)")
                    else:
                        all_results["failed"] += 1
                        if not result["architecture_compliant"]:
                            all_results["architecture_violations"] += 1
                        if not result["expected_match"]:
                            all_results["expected_mismatches"] += 1
                        print(f"      ✗ FAILED")

                    # Print evidence
                    if result["evidence"]:
                        print(f"      Evidence:")
                        for key, value in result["evidence"].items():
                            print(f"        {value}")

                    # Print errors
                    if result["errors"]:
                        print(f"      Errors:")
                        for error in result["errors"]:
                            print(f"        ✗ {error}")

                    # Print warnings
                    if result["warnings"]:
                        print(f"      Warnings:")
                        for warning in result["warnings"]:
                            print(f"        ⚠ {warning}")

                    print()

                    all_results["details"].append(result)

        except Exception as e:
            logger.error(f"Error reading CSV file {csv_file}: {str(e)}")
            print(f"  ✗ Error: {str(e)}\n")

    # Print summary
    print(f"\n{'='*70}")
    print("Validation Summary")
    print(f"{'='*70}")
    print(f"  Total tickets tested: {all_results['total']}")
    print(f"  Passed: {all_results['passed']}")
    print(f"  Failed: {all_results['failed']}")
    if all_results["total"] > 0:
        success_rate = (all_results["passed"] / all_results["total"]) * 100
        print(f"  Success rate: {success_rate:.1f}%")
    print(f"\n  Architecture violations: {all_results['architecture_violations']}")
    print(f"  Expected value mismatches: {all_results['expected_mismatches']}")
    print(f"{'='*70}\n")

    # Save detailed results
    output_file = (
        project_root
        / "validation_results"
        / f"architecture_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Detailed results saved to: {output_file}\n")

    if all_results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

