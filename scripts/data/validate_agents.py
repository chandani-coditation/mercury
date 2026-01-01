#!/usr/bin/env python3
"""Validate agent outputs against filtered test data.

This script:
1. Reads filtered test data (filtered_database_alert.csv, filtered_high_disk_alert.csv)
2. For each test ticket, runs the triage and resolution agents
3. Compares agent outputs against expected values from test data
4. Generates a comprehensive validation report

Usage:
    python scripts/data/validate_agents.py
    python scripts/data/validate_agents.py --output-dir validation_results
    python scripts/data/validate_agents.py --tickets-dir tickets_data --limit 10
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ai_service.core import get_logger, setup_logging
import requests

# Setup logging
setup_logging(log_level="INFO", service_name="validate_agents")
logger = get_logger(__name__)

# Default paths
DEFAULT_TICKETS_DIR = project_root / "tickets_data"
DEFAULT_AI_SERVICE_URL = "http://localhost:8001"
DEFAULT_OUTPUT_DIR = project_root / "validation_results"

# Test data files (filtered tickets for validation)
TEST_DATA_FILES = [
    "filtered_database_alert.csv",
    "filtered_high_disk_alert.csv",
]


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


def csv_row_to_alert(row: Dict) -> Dict[str, Any]:
    """Convert CSV row to alert format for agent API (matches Alert model)."""
    # Extract key fields
    alert_id = row.get("number", "")
    title = row.get("short_description", "")
    description = row.get("description", "")
    category = row.get("category", "")
    assignment_group = row.get("assignment_group", "")
    impact = row.get("impact", "3 - Low")
    urgency = row.get("urgency", "3 - Low")
    cmdb_ci = row.get("cmdb_ci", "")
    
    # Parse timestamp
    opened_at = row.get("opened_at", "")
    timestamp = parse_date(opened_at)
    
    # Build labels dictionary (metadata goes into labels)
    labels = {
        "category": category,
        "assignment_group": assignment_group,
        "cmdb_ci": cmdb_ci,
        "impact": impact,
        "urgency": urgency,
        "state": row.get("state", ""),
        "opened_by": row.get("opened_by", ""),
    }
    
    # Build alert dictionary matching Alert model
    alert = {
        "alert_id": alert_id,
        "source": "servicenow",
        "title": title,
        "description": description,
        "labels": labels,
    }
    
    # Add timestamp if available
    if timestamp:
        alert["ts"] = timestamp.isoformat()
    
    return alert


def call_triage_agent(alert: Dict[str, Any], ai_service_url: str) -> Optional[Dict]:
    """Call triage agent API."""
    try:
        response = requests.post(
            f"{ai_service_url}/api/v1/triage",
            json=alert,
            timeout=120,  # Triage can take time
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Triage agent call failed: {str(e)}")
        return None


def call_resolution_agent(incident_id: str, ai_service_url: str) -> Optional[Dict]:
    """Call resolution agent API.

    Handles policy-blocked responses (HTTP 403) gracefully so we can still
    analyse triage vs. policy behaviour without treating them as hard failures.
    """
    try:
        response = requests.post(
            f"{ai_service_url}/api/v1/resolution",
            params={"incident_id": incident_id},
            timeout=180,  # Resolution can take longer
        )

        # Special handling for policy / approval 403 responses
        if response.status_code == 403:
            try:
                data = response.json()
            except ValueError:
                data = {"detail": response.text}

            detail = data.get("detail", data)
            logger.warning(
                "Resolution requires approval or was blocked by policy: "
                f"incident_id={incident_id}, detail={detail}"
            )

            # Return a structured object indicating policy block instead of None
            return {
                "incident_id": incident_id,
                "resolution": {},
                "policy_blocked": True,
                "http_status": 403,
                "error_detail": detail,
            }

        # For all other statuses, raise if not successful
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Resolution agent call failed: {str(e)}")
        return None


def extract_expected_values(row: Dict) -> Dict[str, Any]:
    """Extract expected values from CSV row for comparison."""
    return {
        "ticket_id": row.get("number", ""),
        "category": row.get("category", ""),
        "assignment_group": row.get("assignment_group", ""),
        "impact": row.get("impact", ""),
        "urgency": row.get("urgency", ""),
        "resolution_comments": row.get("resolution comments", ""),
    }


def compare_triage_output(
    agent_output: Dict, expected: Dict, ticket_id: str
) -> Dict[str, Any]:
    """Compare triage agent output against expected values."""
    comparison = {
        "ticket_id": ticket_id,
        "status": "unknown",
        "matches": {},
        "mismatches": {},
        "warnings": [],
    }
    
    triage = agent_output.get("triage_output", {})
    
    # Compare category
    expected_category = expected.get("category", "").lower()
    agent_category = triage.get("category", "").lower()
    if expected_category and agent_category:
        if expected_category in agent_category or agent_category in expected_category:
            comparison["matches"]["category"] = True
        else:
            comparison["mismatches"]["category"] = {
                "expected": expected_category,
                "actual": agent_category,
            }
    
    # Compare routing (assignment_group)
    expected_routing = expected.get("assignment_group", "").lower()
    agent_routing = triage.get("routing", "").lower()
    if expected_routing and agent_routing:
        if expected_routing in agent_routing or agent_routing in expected_routing:
            comparison["matches"]["routing"] = True
        else:
            comparison["mismatches"]["routing"] = {
                "expected": expected_routing,
                "actual": agent_routing,
            }
    
    # Check severity derivation
    impact = expected.get("impact", "")
    urgency = expected.get("urgency", "")
    agent_severity = triage.get("severity", "").lower()
    if impact and urgency:
        # Expected severity should be derived from impact+urgency
        # This is a soft check - we just verify it's set
        if agent_severity:
            comparison["matches"]["severity_derived"] = True
        else:
            comparison["warnings"].append("Severity not derived from impact/urgency")
    
    # Determine overall status
    if comparison["mismatches"]:
        comparison["status"] = "mismatch"
    elif comparison["matches"]:
        comparison["status"] = "match"
    else:
        comparison["status"] = "partial"
    
    return comparison


def compare_resolution_output(
    agent_output: Dict, expected: Dict, ticket_id: str
) -> Dict[str, Any]:
    """Compare resolution agent output against expected values."""
    comparison = {
        "ticket_id": ticket_id,
        "status": "unknown",
        "has_steps": False,
        "has_commands": False,
        "has_risk_assessment": False,
        "warnings": [],
    }
    
    # Handle both 'resolution' and 'resolution_output' keys for compatibility
    resolution = agent_output.get("resolution") or agent_output.get("resolution_output", {})
    
    # Check for resolution steps
    steps = resolution.get("steps", [])
    if steps and len(steps) > 0:
        comparison["has_steps"] = True
        comparison["steps_count"] = len(steps)
    else:
        comparison["warnings"].append("No resolution steps generated")
    
    # Check for commands
    commands = resolution.get("commands_by_step", {})
    if commands and len(commands) > 0:
        comparison["has_commands"] = True
        comparison["commands_count"] = sum(len(cmd_list) for cmd_list in commands.values())
    else:
        comparison["warnings"].append("No commands generated")
    
    # Check risk assessment
    risk_level = resolution.get("risk_level", "")
    if risk_level:
        comparison["has_risk_assessment"] = True
        comparison["risk_level"] = risk_level
    else:
        comparison["warnings"].append("No risk level assessment")
    
    # Check estimated time
    estimated_time = resolution.get("estimated_time_minutes")
    if estimated_time:
        comparison["estimated_time_minutes"] = estimated_time
    else:
        comparison["warnings"].append("No estimated time provided")
    
    # Check if resolution comments match (soft check)
    expected_comments = expected.get("resolution_comments", "").lower()
    if expected_comments:
        # We can't directly compare, but we can check if agent generated reasoning
        reasoning = resolution.get("reasoning", "").lower()
        if reasoning:
            comparison["has_reasoning"] = True
    
    # Determine overall status
    if comparison["has_steps"] and comparison["has_risk_assessment"]:
        comparison["status"] = "complete"
    elif comparison["has_steps"]:
        comparison["status"] = "partial"
    else:
        comparison["status"] = "incomplete"
    
    return comparison


def process_test_file(
    file_path: Path, ai_service_url: str, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Process a test CSV file and validate agents."""
    results = []
    
    print(f"\n{'='*70}")
    print(f"Processing test file: {file_path.name}")
    print(f"{'='*70}")
    logger.info(f"Processing test file: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if limit:
                rows = rows[:limit]
            
            print(f"\nFound {len(rows)} test ticket(s) to validate\n")
            logger.info(f"Found {len(rows)} test ticket(s) to validate")
            
            for idx, row in enumerate(rows, 1):
                ticket_id = row.get("number", f"row_{idx}")
                print(f"\n[{idx}/{len(rows)}] Processing ticket: {ticket_id}")
                logger.info(f"[{idx}/{len(rows)}] Processing ticket: {ticket_id}")
                
                # Convert CSV row to alert
                alert = csv_row_to_alert(row)
                expected = extract_expected_values(row)
                
                result = {
                    "ticket_id": ticket_id,
                    "source_file": file_path.name,
                    "expected": expected,
                    "triage": None,
                    "resolution": None,
                    "triage_comparison": None,
                    "resolution_comparison": None,
                    "errors": [],
                }
                
                # Step 1: Call triage agent
                print(f"  → Calling triage agent...")
                triage_response = call_triage_agent(alert, ai_service_url)
                
                if not triage_response:
                    error_msg = "Triage agent call failed"
                    result["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")
                    results.append(result)
                    continue
                
                result["triage"] = triage_response
                incident_id = triage_response.get("incident_id")
                
                if not incident_id:
                    error_msg = "No incident_id returned from triage agent"
                    result["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")
                    results.append(result)
                    continue
                
                print(f"    ✓ Triage completed (incident_id: {incident_id})")
                
                # Compare triage output
                triage_comparison = compare_triage_output(
                    triage_response, expected, ticket_id
                )
                result["triage_comparison"] = triage_comparison
                
                if triage_comparison["status"] == "match":
                    print(f"    ✓ Triage output matches expected values")
                elif triage_comparison["status"] == "mismatch":
                    print(f"    ⚠ Triage output has mismatches")
                    for field, mismatch in triage_comparison["mismatches"].items():
                        print(f"      - {field}: expected '{mismatch['expected']}', got '{mismatch['actual']}'")
                
                # Step 2: Call resolution agent
                print(f"  → Calling resolution agent...")
                resolution_response = call_resolution_agent(incident_id, ai_service_url)
                
                if not resolution_response:
                    error_msg = "Resolution agent call failed"
                    result["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")
                    results.append(result)
                    continue

                # If policy blocked (HTTP 403 / approval required), record and continue
                if resolution_response.get("policy_blocked"):
                    result["resolution"] = resolution_response
                    print(
                        "    ⚠ Resolution not generated - blocked by policy / requires approval "
                        "(HTTP 403). Recording as policy-blocked, not agent failure."
                    )
                    results.append(result)
                    continue
                
                result["resolution"] = resolution_response
                print(f"    ✓ Resolution completed")
                
                # Compare resolution output
                resolution_comparison = compare_resolution_output(
                    resolution_response, expected, ticket_id
                )
                result["resolution_comparison"] = resolution_comparison
                
                if resolution_comparison["status"] == "complete":
                    print(f"    ✓ Resolution output is complete")
                elif resolution_comparison["status"] == "partial":
                    print(f"    ⚠ Resolution output is partial")
                else:
                    print(f"    ✗ Resolution output is incomplete")
                
                if resolution_comparison["warnings"]:
                    for warning in resolution_comparison["warnings"]:
                        print(f"      ⚠ {warning}")
                
                results.append(result)
                
    except Exception as e:
        logger.error(f"Error processing test file {file_path}: {str(e)}", exc_info=True)
        print(f"\n✗ Error processing test file: {str(e)}")
    
    return results


def generate_report(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """Generate validation report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"validation_report_{timestamp}.json"
    summary_file = output_dir / f"validation_summary_{timestamp}.txt"
    
    # Save detailed results
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n{'='*70}")
    print("Validation Summary")
    print(f"{'='*70}")
    
    # Calculate statistics
    total = len(results)
    triage_success = sum(1 for r in results if r.get("triage") is not None)
    resolution_success = sum(1 for r in results if r.get("resolution") is not None)
    triage_matches = sum(
        1
        for r in results
        if r.get("triage_comparison", {}).get("status") == "match"
    )
    resolution_complete = sum(
        1
        for r in results
        if r.get("resolution_comparison", {}).get("status") == "complete"
    )
    errors = sum(1 for r in results if r.get("errors"))
    
    # Generate summary
    summary_lines = [
        f"Validation Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        f"Total test tickets: {total}",
        f"Triage agent success: {triage_success}/{total} ({triage_success/total*100:.1f}%)",
        f"Resolution agent success: {resolution_success}/{total} ({resolution_success/total*100:.1f}%)",
        f"Triage matches: {triage_matches}/{triage_success} ({triage_matches/triage_success*100:.1f}% of successful)" if triage_success > 0 else "Triage matches: N/A",
        f"Resolution complete: {resolution_complete}/{resolution_success} ({resolution_complete/resolution_success*100:.1f}% of successful)" if resolution_success > 0 else "Resolution complete: N/A",
        f"Errors: {errors}/{total}",
        "",
        "=" * 70,
    ]
    
    # Print summary
    for line in summary_lines:
        print(line)
    
    # Save summary
    with open(summary_file, "w") as f:
        f.write("\n".join(summary_lines))
    
    print(f"\n✓ Detailed report saved: {report_file}")
    print(f"✓ Summary saved: {summary_file}")
    logger.info(f"Validation report saved to {report_file}")
    logger.info(f"Validation summary saved to {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate agent outputs against filtered test data",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--tickets-dir",
        type=str,
        default=str(DEFAULT_TICKETS_DIR),
        help=f"Directory containing test CSV files (default: {DEFAULT_TICKETS_DIR})",
    )
    parser.add_argument(
        "--ai-service-url",
        type=str,
        default=DEFAULT_AI_SERVICE_URL,
        help=f"AI service URL (default: {DEFAULT_AI_SERVICE_URL})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for validation reports (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of tickets to process per file (for testing)",
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("Agent Validation Script")
    print("=" * 70)
    logger.info("Starting agent validation...")

    tickets_dir = Path(args.tickets_dir)
    output_dir = Path(args.output_dir)

    if not tickets_dir.exists():
        print(f"\n✗ Tickets directory not found: {tickets_dir}")
        logger.error(f"Tickets directory not found: {tickets_dir}")
        sys.exit(1)

    all_results = []

    # Process each test data file
    for test_file in TEST_DATA_FILES:
        file_path = tickets_dir / test_file
        if not file_path.exists():
            print(f"\n⚠ Test file not found: {file_path}")
            logger.warning(f"Test file not found: {file_path}")
            continue

        results = process_test_file(file_path, args.ai_service_url, args.limit)
        all_results.extend(results)

    if not all_results:
        print("\n✗ No test data processed. Please check file paths.")
        logger.error("No test data processed")
        sys.exit(1)

    # Generate report
    generate_report(all_results, output_dir)

    print("\n✓ Validation completed!")
    logger.info("Validation completed successfully")


if __name__ == "__main__":
    main()

