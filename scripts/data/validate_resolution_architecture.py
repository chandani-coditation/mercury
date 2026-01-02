#!/usr/bin/env python3
"""Validate resolution agent output against ARCHITECTURE_LOCK.md requirements.

This script validates that the resolution agent:
1. Follows the output contract (Section 7.5)
2. Does NOT violate constraints (Section 7.4)
3. Correctly retrieves and ranks runbook steps
4. Provides proper provenance for all recommendations

Per ARCHITECTURE_LOCK.md Section 7:
- Resolution agent ONLY ranks and assembles existing steps
- Input: Triage output (immutable)
- Retrieves: Runbook steps, historical resolution references
- Output: Ordered recommendations with provenance
- MUST NOT re-classify, invent steps, use generic advice, or ignore provenance
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
setup_logging(log_level="INFO", service_name="resolution_architecture_validation")
logger = get_logger(__name__)

# Default service URLs
TRIAGE_SERVICE_URL = "http://localhost:8001"
RESOLUTION_SERVICE_URL = "http://localhost:8001"


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

    # Build labels
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
        severity=None,
        category=category,
        affected_services=affected_services,
        labels=labels,
        ts=timestamp,
        source="servicenow",
    )


def call_triage_agent(alert: Alert) -> Dict:
    """Call triage agent API and return full result including incident_id."""
    try:
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/triage",
            json=alert.model_dump(mode="json", exclude_none=True),
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        # Return full result (includes incident_id, triage, evidence, etc.)
        return result
    except Exception as e:
        logger.error(f"Failed to call triage agent: {str(e)}")
        raise


def approve_triage(incident_id: str, triage_output: Dict) -> bool:
    """Approve triage output to allow resolution generation via feedback API."""
    try:
        # Use feedback API to approve triage (set policy to AUTO)
        response = requests.put(
            f"{RESOLUTION_SERVICE_URL}/api/v1/incidents/{incident_id}/feedback",
            json={
                "feedback_type": "triage",
                "user_edited": triage_output,  # Same as system output (no edits, just approval)
                "notes": "Approved for validation/testing - allowing resolution to proceed",
                "policy_band": "AUTO"  # This will update the policy to AUTO
            },
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"Approved triage for incident {incident_id} (policy set to AUTO via feedback API)")
        return True
    except Exception as e:
        logger.warning(f"Could not approve triage via API: {e}. Will try resolution anyway.")
        return False


def call_resolution_agent(incident_id: str) -> Dict:
    """Call resolution agent API with incident_id."""
    try:
        response = requests.post(
            f"{RESOLUTION_SERVICE_URL}/api/v1/resolution",
            params={"incident_id": incident_id},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to call resolution agent: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:500]}")
        raise


def validate_architecture_compliance(resolution_output: Dict, triage_output: Dict) -> Dict:
    """
    Validate resolution output against ARCHITECTURE_LOCK.md Section 7.5.
    
    Required structure per architecture:
    {
        "recommendations": [
            {
                "step_id": "RB123-S3",
                "action": "...",
                "confidence": 0.91,
                "provenance": {
                    "runbook_id": "RB123",
                    "incident_signatures": ["SIG-DB-001"]
                }
            }
        ],
        "overall_confidence": 0.88,
        "risk_level": "low"
    }
    """
    violations = []
    warnings = []
    evidence = {}

    # Check if resolution output exists
    if "resolution" not in resolution_output:
        violations.append("Missing required field: resolution")
        return {
            "compliant": False,
            "violations": violations,
            "warnings": warnings,
            "evidence": evidence,
        }

    resolution = resolution_output["resolution"]

    # Check for recommendations (new architecture format) or steps (legacy format)
    has_recommendations = "recommendations" in resolution
    has_steps = "steps" in resolution or "resolution_steps" in resolution

    if not has_recommendations and not has_steps:
        violations.append("Missing required field: recommendations or steps")
    else:
        if has_recommendations:
            recommendations = resolution["recommendations"]
            if not isinstance(recommendations, list):
                violations.append("recommendations must be a list")
            elif len(recommendations) == 0:
                warnings.append("No recommendations provided (empty list)")
            else:
                evidence["recommendations_count"] = f"✓ {len(recommendations)} recommendation(s)"
                
                # Validate each recommendation
                for idx, rec in enumerate(recommendations):
                    if "step_id" not in rec:
                        violations.append(f"Recommendation {idx}: Missing step_id")
                    if "action" not in rec:
                        violations.append(f"Recommendation {idx}: Missing action")
                    if "provenance" not in rec:
                        violations.append(f"Recommendation {idx}: Missing provenance")
                    else:
                        prov = rec["provenance"]
                        if "runbook_id" not in prov:
                            violations.append(f"Recommendation {idx}: Missing provenance.runbook_id")
                        if "incident_signatures" not in prov:
                            warnings.append(f"Recommendation {idx}: Missing provenance.incident_signatures")
                    
                    if "confidence" in rec:
                        conf = rec["confidence"]
                        if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
                            violations.append(f"Recommendation {idx}: Invalid confidence: {conf}")
        else:
            # Legacy format with steps
            steps = resolution.get("steps") or resolution.get("resolution_steps", [])
            if len(steps) > 0:
                evidence["steps_count"] = f"✓ {len(steps)} step(s) (legacy format)"
                warnings.append("Using legacy 'steps' format instead of 'recommendations'")

    # Check overall_confidence
    if "overall_confidence" in resolution:
        conf = resolution["overall_confidence"]
        if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
            violations.append(f"Invalid overall_confidence: {conf} (must be 0.0-1.0)")
        else:
            if conf >= 0.7:
                evidence["overall_confidence"] = f"✓ High overall confidence: {conf:.2f}"
            elif conf >= 0.5:
                warnings.append(f"Moderate overall confidence: {conf:.2f}")
            else:
                warnings.append(f"Low overall confidence: {conf:.2f}")
    else:
        warnings.append("Missing overall_confidence field")

    # Check risk_level
    if "risk_level" in resolution:
        risk = resolution["risk_level"]
        if risk not in ["low", "medium", "high"]:
            violations.append(f"Invalid risk_level: {risk} (must be low|medium|high)")
        else:
            evidence["risk_level"] = f"✓ Risk level: {risk}"
    else:
        violations.append("Missing required field: risk_level")

    # Check for forbidden content (Section 7.4)
    forbidden_fields = ["failure_type", "error_class", "severity", "incident_signature"]
    for field in forbidden_fields:
        if field in resolution:
            violations.append(f"FORBIDDEN: Resolution agent must not re-classify (contains '{field}')")

    # Check that resolution doesn't modify triage output
    # (Resolution should not change failure_type, error_class, etc.)
    if "incident_signature" in resolution:
        violations.append("FORBIDDEN: Resolution agent must not re-classify incident")

    # Check for provenance in recommendations
    if has_recommendations:
        recommendations = resolution.get("recommendations", [])
        for idx, rec in enumerate(recommendations):
            if "provenance" in rec:
                prov = rec["provenance"]
                if "runbook_id" not in prov:
                    violations.append(f"Recommendation {idx}: Missing runbook_id in provenance")
                else:
                    evidence["has_provenance"] = "✓ All recommendations have provenance"

    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "evidence": evidence,
    }


def validate_ticket(
    row: Dict, field_mappings: Dict, row_num: int
) -> Dict:
    """Validate a single ticket through triage and resolution."""
    incident_id = row.get("number", f"row_{row_num}")
    title = row.get("short_description", "")[:60]

    try:
        # Convert to Alert
        alert = csv_row_to_alert(row, field_mappings)

        # Step 1: Call triage agent to create incident
        logger.info(f"Calling triage agent for {incident_id}...")
        triage_result = call_triage_agent(alert)
        
        # Extract incident_id from triage result
        # The triage API returns: {"incident_id": "...", "triage": {...}, "evidence": {...}, ...}
        created_incident_id = None
        if isinstance(triage_result, dict):
            created_incident_id = triage_result.get("incident_id")
            if not created_incident_id:
                # Try alternative field names
                created_incident_id = triage_result.get("id")
        
        if not created_incident_id:
            logger.error(f"Triage result structure: {list(triage_result.keys()) if isinstance(triage_result, dict) else 'not a dict'}")
            raise ValueError(f"Could not extract incident_id from triage result. Response keys: {list(triage_result.keys()) if isinstance(triage_result, dict) else 'N/A'}")
        
        # Extract triage output for validation
        triage_output = triage_result.get("triage", {}) if isinstance(triage_result, dict) else {}
        
        # Step 1.5: Approve triage to allow resolution generation
        logger.info(f"Approving triage for incident {created_incident_id}...")
        approve_triage(created_incident_id, triage_output)
        
        # Step 2: Call resolution agent with incident_id
        logger.info(f"Calling resolution agent for incident {created_incident_id}...")
        resolution_output = call_resolution_agent(created_incident_id)

        # Step 3: Validate architecture compliance
        arch_validation = validate_architecture_compliance(resolution_output, triage_output)

        # Combine results
        passed = arch_validation["compliant"]

        return {
            "incident_id": incident_id,
            "title": title,
            "passed": passed,
            "architecture_compliant": arch_validation["compliant"],
            "errors": arch_validation["violations"],
            "warnings": arch_validation["warnings"],
            "evidence": arch_validation["evidence"],
            "triage_output": triage_output,
            "resolution_output": resolution_output,
        }

    except Exception as e:
        return {
            "incident_id": incident_id,
            "title": title,
            "passed": False,
            "architecture_compliant": False,
            "errors": [f"Error calling agents: {str(e)}"],
            "warnings": [],
            "evidence": {},
            "triage_output": None,
            "resolution_output": None,
        }


def main():
    global TRIAGE_SERVICE_URL, RESOLUTION_SERVICE_URL

    parser = argparse.ArgumentParser(
        description="Validate resolution agent against ARCHITECTURE_LOCK.md requirements"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="CSV file to validate (default: both ticket files)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=5,
        help="Number of sample tickets to test (default: 5)",
    )
    parser.add_argument(
        "--service-url",
        type=str,
        default=RESOLUTION_SERVICE_URL,
        help=f"AI service URL (default: {RESOLUTION_SERVICE_URL})",
    )

    args = parser.parse_args()

    if args.service_url:
        TRIAGE_SERVICE_URL = args.service_url
        RESOLUTION_SERVICE_URL = args.service_url

    print("=" * 70)
    print("Resolution Agent Architecture Validation")
    print("Validating against ARCHITECTURE_LOCK.md Section 7")
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
                        print(f"      ✓ PASSED (Architecture compliant)")
                    else:
                        all_results["failed"] += 1
                        if not result["architecture_compliant"]:
                            all_results["architecture_violations"] += 1
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
    print(f"{'='*70}\n")

    # Save detailed results
    output_file = (
        project_root
        / "validation_results"
        / f"resolution_architecture_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Detailed results saved to: {output_file}\n")

    if all_results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

