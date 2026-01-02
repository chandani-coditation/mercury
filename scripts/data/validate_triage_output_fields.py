#!/usr/bin/env python3
"""Validate triage agent output fields against original ticket data.

This script validates that the triage agent correctly predicts:
- routing (assignment_group)
- impact
- urgency
- severity (derived from impact/urgency)
- affected_services

by comparing against the original ticket data from ServiceNow CSV.
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
setup_logging(log_level="INFO", service_name="triage_field_validation")
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

    # Build labels (for fallback - but agent should predict from evidence)
    labels = {
        "type": "historical_incident",
        "ticket_id": incident_id,
        "category": category,
        # Note: We intentionally don't include assignment_group, impact, urgency in labels
        # to test if the agent predicts them from evidence
    }

    return Alert(
        alert_id=incident_id,
        title=title,
        description=description,
        severity=None,  # Will be determined by triage agent
        category=category,
        affected_services=affected_services if affected_services else None,
        labels=labels,
        ts=timestamp,
        source="servicenow",
    )


def get_expected_values(row: Dict, field_mappings: Dict) -> Dict:
    """Extract expected values from CSV row."""
    mappings = field_mappings.get("field_mappings", {})
    
    return {
        "incident_id": row.get(mappings.get("incident_id", {}).get("source_column", "number"), ""),
        "routing": row.get(mappings.get("assignment_group", {}).get("source_column", "assignment_group"), ""),
        "impact": row.get(mappings.get("impact", {}).get("source_column", "impact"), ""),
        "urgency": row.get(mappings.get("urgency", {}).get("source_column", "urgency"), ""),
        "affected_services": row.get(mappings.get("affected_services", {}).get("source_column", "cmdb_ci"), ""),
    }


def derive_expected_severity(impact: str, urgency: str, field_mappings: Dict) -> str:
    """Derive expected severity from impact/urgency using mapping."""
    if not impact or not urgency:
        return None
    
    try:
        severity_mapping = field_mappings.get("severity_mapping", {})
        mapping = severity_mapping.get("impact_urgency_to_severity", {})
        default = severity_mapping.get("default_severity", "medium")
        
        # Extract numeric values (e.g., "3 - Low" -> "3")
        impact_val = impact.split()[0] if impact and isinstance(impact, str) else "3"
        urgency_val = urgency.split()[0] if urgency and isinstance(urgency, str) else "3"
        
        # Create key (e.g., "3-3")
        key = f"{impact_val}-{urgency_val}"
        
        # Look up in mapping
        severity = mapping.get(key, default)
        return severity
    except Exception as e:
        logger.warning(f"Error deriving severity from impact/urgency: {e}. Using default 'medium'")
        return "medium"


def call_triage_agent(alert: Alert) -> Dict:
    """Call triage agent API."""
    global TRIAGE_SERVICE_URL
    
    alert_dict = alert.model_dump(mode="json", exclude_none=True)
    if alert.ts:
        alert_dict["ts"] = alert.ts.isoformat() if isinstance(alert.ts, datetime) else alert.ts
    else:
        alert_dict["ts"] = datetime.utcnow().isoformat()
    
    try:
        response = requests.post(
            f"{TRIAGE_SERVICE_URL}/api/v1/triage",
            json=alert_dict,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to call triage agent: {e}")
        raise


def normalize_value(value) -> str:
    """Normalize value for comparison."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else ""
    return str(value).strip()


def compare_fields(triage_output: Dict, expected: Dict, field_mappings: Dict) -> Dict:
    """Compare triage output fields with expected values."""
    triage = triage_output.get("triage", {})
    
    # Get expected severity
    expected_severity = None
    if expected.get("impact") and expected.get("urgency"):
        expected_severity = derive_expected_severity(
            expected["impact"], 
            expected["urgency"], 
            field_mappings
        )
    
    results = {
        "incident_id": expected["incident_id"],
        "fields": {}
    }
    
    # Compare each field
    fields_to_compare = [
        ("routing", "routing", "Routing (assignment_group)"),
        ("impact", "impact", "Impact"),
        ("urgency", "urgency", "Urgency"),
        ("severity", "severity", "Severity"),
        ("affected_services", "affected_services", "Affected Services"),
    ]
    
    for field_key, triage_key, display_name in fields_to_compare:
        expected_val = normalize_value(expected.get(field_key))
        if field_key == "severity":
            actual_val = normalize_value(triage.get(triage_key))
            expected_val = normalize_value(expected_severity)
        elif field_key == "affected_services":
            actual_val = normalize_value(triage.get(triage_key))
            # Compare as lists
            expected_list = [expected_val] if expected_val else []
            actual_list = triage.get(triage_key, []) if isinstance(triage.get(triage_key), list) else [triage.get(triage_key)] if triage.get(triage_key) else []
            expected_val = ", ".join(expected_list)
            actual_val = ", ".join(str(v) for v in actual_list) if actual_list else ""
        else:
            actual_val = normalize_value(triage.get(triage_key))
        
        match = (expected_val.lower() == actual_val.lower()) if expected_val and actual_val else (not expected_val and not actual_val)
        
        results["fields"][field_key] = {
            "display_name": display_name,
            "expected": expected_val,
            "actual": actual_val,
            "match": match
        }
    
    return results


def validate_tickets(csv_file: str, num_tickets: int = 3) -> List[Dict]:
    """Validate triage agent output for specified number of tickets."""
    field_mappings = get_field_mappings_config()
    
    results = []
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        tickets = list(reader)[:num_tickets]
    
    logger.info(f"Validating {len(tickets)} tickets from {csv_file}")
    
    for i, row in enumerate(tickets, 1):
        incident_id = row.get("number", f"TICKET-{i}")
        logger.info(f"\n[{i}/{len(tickets)}] Validating ticket: {incident_id}")
        
        try:
            # Get expected values from CSV
            expected = get_expected_values(row, field_mappings)
            
            # Convert to Alert
            alert = csv_row_to_alert(row, field_mappings)
            
            # Call triage agent
            logger.info(f"  Calling triage agent...")
            triage_result = call_triage_agent(alert)
            
            # Compare fields
            comparison = compare_fields(triage_result, expected, field_mappings)
            results.append(comparison)
            
            # Print results
            print(f"\n{'='*80}")
            print(f"Ticket: {incident_id}")
            print(f"{'='*80}")
            
            all_match = True
            for field_key, field_data in comparison["fields"].items():
                status = "✓ MATCH" if field_data["match"] else "✗ MISMATCH"
                if not field_data["match"]:
                    all_match = False
                
                print(f"\n{field_data['display_name']}: {status}")
                print(f"  Expected: {field_data['expected'] or '(empty)'}")
                print(f"  Actual:   {field_data['actual'] or '(empty)'}")
            
            print(f"\n{'='*80}")
            print(f"Overall: {'✓ ALL FIELDS MATCH' if all_match else '✗ SOME FIELDS MISMATCH'}")
            print(f"{'='*80}\n")
            
        except Exception as e:
            logger.error(f"Error validating ticket {incident_id}: {e}", exc_info=True)
            results.append({
                "incident_id": incident_id,
                "error": str(e),
                "fields": {}
            })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate triage agent output fields against original ticket data"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="tickets_data/updated database alerts filtered - Sheet1.csv",
        help="Path to CSV file with ticket data"
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=3,
        help="Number of tickets to validate (default: 3)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional: Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    csv_file = Path(args.file)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_file}")
        sys.exit(1)
    
    results = validate_tickets(str(csv_file), args.num_samples)
    
    # Summary
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")
    
    total = len(results)
    passed = sum(1 for r in results if r.get("fields") and all(f.get("match", False) for f in r["fields"].values()))
    failed = total - passed
    
    print(f"Total tickets tested: {total}")
    print(f"Passed (all fields match): {passed}")
    print(f"Failed (some fields mismatch): {failed}")
    print(f"Success rate: {(passed/total*100) if total > 0 else 0:.1f}%")
    
    # Field-level summary
    if results:
        field_stats = {}
        for result in results:
            if "fields" in result:
                for field_key, field_data in result["fields"].items():
                    if field_key not in field_stats:
                        field_stats[field_key] = {"total": 0, "matched": 0}
                    field_stats[field_key]["total"] += 1
                    if field_data.get("match"):
                        field_stats[field_key]["matched"] += 1
        
        print(f"\nField-level accuracy:")
        for field_key, stats in field_stats.items():
            accuracy = (stats["matched"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {field_key}: {stats['matched']}/{stats['total']} ({accuracy:.1f}%)")
    
    # Save results if requested
    if args.output:
        output_file = Path(args.output)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to: {output_file}")
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

