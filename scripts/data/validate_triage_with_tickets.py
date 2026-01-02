#!/usr/bin/env python3
"""Validate triage agent with sample tickets from CSV data.

This script:
1. Reads sample tickets from CSV files
2. Sends them to triage agent
3. Validates predictions match expected values
4. Provides evidence for triage decisions
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
setup_logging(log_level="INFO", service_name="triage_validation")
logger = get_logger(__name__)

# Default service URLs
TRIAGE_SERVICE_URL = "http://localhost:8001"
INGESTION_SERVICE_URL = "http://localhost:8002"


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
        source="servicenow",  # Required field
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


def validate_triage_output(
    triage_output: Dict, expected_assignment_group: str, expected_impact: str, expected_urgency: str
) -> Dict:
    """Validate triage output against expected values."""
    results = {
        "passed": True,
        "errors": [],
        "warnings": [],
        "evidence": {},
    }

    # Check routing (assignment_group)
    routing = triage_output.get("routing", "")
    if routing:
        if routing.lower() != expected_assignment_group.lower():
            results["errors"].append(
                f"Routing mismatch: expected '{expected_assignment_group}', got '{routing}'"
            )
            results["passed"] = False
        else:
            results["evidence"]["routing"] = f"✓ Correctly routed to '{routing}'"
    else:
        results["warnings"].append("No routing (assignment_group) provided in triage output")

    # Check severity
    severity = triage_output.get("severity", "")
    if severity:
        results["evidence"]["severity"] = f"✓ Severity: {severity}"
    else:
        results["warnings"].append("No severity provided in triage output")

    # Check incident signature
    incident_signature = triage_output.get("incident_signature", {})
    if incident_signature:
        failure_type = incident_signature.get("failure_type", "")
        error_class = incident_signature.get("error_class", "")
        results["evidence"]["failure_type"] = f"✓ Failure Type: {failure_type}"
        results["evidence"]["error_class"] = f"✓ Error Class: {error_class}"

    # Check affected services
    affected_services = triage_output.get("affected_services", [])
    if affected_services:
        results["evidence"]["affected_services"] = f"✓ Affected Services: {', '.join(affected_services)}"

    # Check confidence
    confidence = triage_output.get("confidence", 0.0)
    if confidence >= 0.7:
        results["evidence"]["confidence"] = f"✓ High confidence: {confidence:.2f}"
    elif confidence >= 0.5:
        results["warnings"].append(f"Moderate confidence: {confidence:.2f}")
    else:
        results["errors"].append(f"Low confidence: {confidence:.2f}")
        results["passed"] = False

    # Check matched evidence
    matched_evidence = triage_output.get("matched_evidence", {})
    if matched_evidence:
        signature_ids = matched_evidence.get("incident_signatures", [])
        if signature_ids:
            results["evidence"]["matched_signatures"] = f"✓ Matched {len(signature_ids)} signature(s)"
        else:
            results["warnings"].append("No matched incident signatures found")

    return results


def validate_tickets_from_csv(
    csv_file: Path, field_mappings: Dict, num_samples: int = 5
) -> Dict:
    """Validate triage agent with sample tickets from CSV."""
    print(f"\n{'='*70}")
    print(f"Validating Triage Agent with tickets from: {csv_file.name}")
    print(f"{'='*70}\n")

    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "details": [],
    }

    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total_rows = len(rows)

            # Select sample tickets (first N, or random if specified)
            sample_indices = list(range(min(num_samples, total_rows)))
            samples = [rows[i] for i in sample_indices]

            print(f"  Processing {len(samples)} sample ticket(s) from {total_rows} total...\n")

            for idx, row in enumerate(samples, 1):
                try:
                    incident_id = row.get("number", f"row_{idx}")
                    title = row.get("short_description", "")[:50]
                    expected_assignment_group = row.get("assignment_group", "")
                    expected_impact = row.get("impact", "")
                    expected_urgency = row.get("urgency", "")

                    print(f"  [{idx}/{len(samples)}] Testing ticket {incident_id}")
                    print(f"      Title: {title}...")
                    print(f"      Expected Assignment Group: {expected_assignment_group}")

                    # Convert to Alert
                    alert = csv_row_to_alert(row, field_mappings)

                    # Call triage agent
                    print(f"      Calling triage agent...")
                    triage_output = call_triage_agent(alert)

                    # Validate output
                    validation = validate_triage_output(
                        triage_output, expected_assignment_group, expected_impact, expected_urgency
                    )

                    results["total"] += 1
                    if validation["passed"]:
                        results["passed"] += 1
                        print(f"      ✓ PASSED")
                    else:
                        results["failed"] += 1
                        print(f"      ✗ FAILED")

                    # Print evidence
                    if validation["evidence"]:
                        print(f"      Evidence:")
                        for key, value in validation["evidence"].items():
                            print(f"        {value}")

                    # Print errors
                    if validation["errors"]:
                        print(f"      Errors:")
                        for error in validation["errors"]:
                            print(f"        ✗ {error}")

                    # Print warnings
                    if validation["warnings"]:
                        print(f"      Warnings:")
                        for warning in validation["warnings"]:
                            print(f"        ⚠ {warning}")

                    # Store details
                    results["details"].append(
                        {
                            "incident_id": incident_id,
                            "title": title,
                            "expected_assignment_group": expected_assignment_group,
                            "triage_output": triage_output,
                            "validation": validation,
                        }
                    )

                    print()

                except Exception as e:
                    results["total"] += 1
                    results["failed"] += 1
                    error_msg = f"Error processing ticket {incident_id}: {str(e)}"
                    print(f"      ✗ ERROR: {error_msg}\n")
                    logger.error(error_msg)
                    continue

    except Exception as e:
        logger.error(f"Error reading CSV file {csv_file}: {str(e)}")
        raise

    return results


def main():
    global TRIAGE_SERVICE_URL
    
    parser = argparse.ArgumentParser(description="Validate triage agent with sample tickets")
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
        "--triage-url",
        type=str,
        default=TRIAGE_SERVICE_URL,
        help=f"Triage service URL (default: {TRIAGE_SERVICE_URL})",
    )

    args = parser.parse_args()

    # Update service URL if provided
    if args.triage_url:
        TRIAGE_SERVICE_URL = args.triage_url

    print("=" * 70)
    print("Triage Agent Validation Script")
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
        # Default: both ticket files
        tickets_dir = project_root / "tickets_data"
        csv_files = [
            tickets_dir / "updated high disk filtered - Sheet1.csv",
            tickets_dir / "updated database alerts filtered - Sheet1.csv",
        ]

    all_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "file_results": [],
    }

    for csv_file in csv_files:
        if not csv_file.exists():
            print(f"\n⚠ CSV file not found: {csv_file}")
            continue

        file_results = validate_tickets_from_csv(csv_file, servicenow_mappings, args.num_samples)
        all_results["total"] += file_results["total"]
        all_results["passed"] += file_results["passed"]
        all_results["failed"] += file_results["failed"]
        all_results["file_results"].append(
            {"file": str(csv_file), "results": file_results}
        )

    # Print summary
    print(f"\n{'='*70}")
    print(f"Validation Summary:")
    print(f"   Total tickets tested: {all_results['total']}")
    print(f"   Passed: {all_results['passed']}")
    print(f"   Failed: {all_results['failed']}")
    if all_results["total"] > 0:
        success_rate = (all_results["passed"] / all_results["total"]) * 100
        print(f"   Success rate: {success_rate:.1f}%")
    print(f"{'='*70}\n")

    # Save detailed results to JSON
    output_file = project_root / "validation_results" / f"triage_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Detailed results saved to: {output_file}\n")

    if all_results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

