#!/usr/bin/env python3
"""Enhanced validation script with detailed runbook tracking and comprehensive summaries.

This script:
1. Reads filtered test data
2. Runs triage and resolution agents
3. Tracks runbook usage and solution generation
4. Generates detailed summaries for each ticket
5. Creates comprehensive validation reports

Usage:
    python scripts/data/validate_agents_enhanced.py
    python scripts/data/validate_agents_enhanced.py --limit 5
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
setup_logging(log_level="INFO", service_name="validate_agents_enhanced")
logger = get_logger(__name__)

# Default paths
DEFAULT_TICKETS_DIR = project_root / "tickets_data"
DEFAULT_AI_SERVICE_URL = "http://localhost:8001"
DEFAULT_OUTPUT_DIR = project_root / "validation_results"

# Test data files
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
    """Convert CSV row to alert format for agent API."""
    alert_id = row.get("number", "")
    title = row.get("short_description", "")
    description = row.get("description", "")
    category = row.get("category", "")
    assignment_group = row.get("assignment_group", "")
    impact = row.get("impact", "3 - Low")
    urgency = row.get("urgency", "3 - Low")
    cmdb_ci = row.get("cmdb_ci", "")
    
    timestamp = parse_date(row.get("opened_at", ""))
    
    labels = {
        "category": category,
        "assignment_group": assignment_group,
        "cmdb_ci": cmdb_ci,
        "impact": impact,
        "urgency": urgency,
        "state": row.get("state", ""),
        "opened_by": row.get("opened_by", ""),
    }
    
    alert = {
        "alert_id": alert_id,
        "source": "servicenow",
        "title": title,
        "description": description,
        "labels": labels,
    }
    
    if timestamp:
        alert["ts"] = timestamp.isoformat()
    
    return alert


def call_triage_agent(alert: Dict[str, Any], ai_service_url: str) -> Optional[Dict]:
    """Call triage agent API."""
    try:
        response = requests.post(
            f"{ai_service_url}/api/v1/triage",
            json=alert,
            timeout=180,  # Increased timeout
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Triage agent call failed: {str(e)}")
        return None


def call_resolution_agent(incident_id: str, ai_service_url: str) -> Optional[Dict]:
    """Call resolution agent API."""
    try:
        response = requests.post(
            f"{ai_service_url}/api/v1/resolution",
            params={"incident_id": incident_id},
            timeout=300,  # Increased timeout for resolution
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            # Policy blocked - not an error, just requires approval
            try:
                error_detail = e.response.json()
            except:
                error_detail = {"message": str(e)}
            return {
                "incident_id": incident_id,
                "resolution": {},
                "policy_blocked": True,
                "http_status": 403,
                "error_detail": error_detail,
            }
        logger.error(f"Resolution agent call failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Resolution agent call failed: {str(e)}")
        return None


def extract_runbook_usage(triage_output: Dict, resolution_output: Dict) -> Dict[str, Any]:
    """Extract runbook usage information from agent outputs."""
    runbook_info = {
        "runbooks_used": [],
        "runbook_chunks_count": 0,
        "total_evidence_chunks": 0,
        "runbook_titles": [],
        "runbook_services": [],
        "provenance_references": [],
    }
    
    # Check evidence chunks from triage
    triage_evidence = triage_output.get("triage_evidence") or triage_output.get("evidence_chunks")
    if isinstance(triage_evidence, dict):
        triage_evidence = triage_evidence.get("chunks", [])
    elif not isinstance(triage_evidence, list):
        triage_evidence = []
    
    # Check evidence chunks from resolution
    resolution_evidence = resolution_output.get("resolution_evidence") or resolution_output.get("evidence_chunks") or resolution_output.get("evidence")
    if isinstance(resolution_evidence, dict):
        resolution_evidence = resolution_evidence.get("chunks", [])
    elif not isinstance(resolution_evidence, list):
        resolution_evidence = []
    
    # Combine all evidence chunks
    all_chunks = []
    if triage_evidence:
        all_chunks.extend(triage_evidence)
    if resolution_evidence:
        all_chunks.extend(resolution_evidence)
    
    runbook_info["total_evidence_chunks"] = len(all_chunks)
    
    # Extract runbook chunks
    runbook_chunks = []
    seen_runbooks = set()  # Track unique runbooks by document_id
    
    for chunk in all_chunks:
        # Try multiple ways to get doc_type
        doc_type = (
            chunk.get("doc_type") 
            or (chunk.get("metadata") or {}).get("doc_type") 
            or (chunk.get("provenance") or {}).get("source_type")
        )
        
        if doc_type == "runbook":
            runbook_chunks.append(chunk)
            doc_id = chunk.get("document_id") or chunk.get("doc_id")
            
            # Only add unique runbooks
            if doc_id and doc_id not in seen_runbooks:
                seen_runbooks.add(doc_id)
                
                doc_title = (
                    chunk.get("doc_title") 
                    or chunk.get("title") 
                    or (chunk.get("metadata") or {}).get("title", "Unknown")
                )
                service = (
                    chunk.get("service") 
                    or (chunk.get("metadata") or {}).get("service") 
                    or (chunk.get("provenance") or {}).get("service", "Unknown")
                )
                
                runbook_info["runbooks_used"].append({
                    "document_id": doc_id,
                    "chunk_id": chunk.get("chunk_id"),
                    "title": doc_title,
                    "service": service,
                    "content_preview": (
                        (chunk.get("content", "")[:200] + "...") 
                        if len(chunk.get("content", "")) > 200 
                        else chunk.get("content", "")
                    ),
                })
                
                if doc_title and doc_title not in runbook_info["runbook_titles"]:
                    runbook_info["runbook_titles"].append(doc_title)
                if service and service not in runbook_info["runbook_services"]:
                    runbook_info["runbook_services"].append(service)
    
    runbook_info["runbook_chunks_count"] = len(runbook_chunks)
    
    # Extract provenance from resolution output
    resolution = resolution_output.get("resolution") or resolution_output.get("resolution_output", {})
    if isinstance(resolution, dict):
        provenance = resolution.get("provenance", [])
        if provenance:
            runbook_info["provenance_references"] = provenance
    
    return runbook_info


def analyze_solution_generation(resolution_output: Dict, runbook_info: Dict) -> Dict[str, Any]:
    """Analyze how solution was generated from runbooks."""
    analysis = {
        "steps_count": 0,
        "commands_count": 0,
        "steps": [],
        "commands_by_step": {},
        "runbook_mapped_steps": [],
        "runbook_mapped_commands": [],
        "reasoning": "",
        "risk_level": "",
        "estimated_time": None,
        "rollback_plan": None,
    }
    
    resolution = resolution_output.get("resolution") or resolution_output.get("resolution_output", {})
    
    # Extract steps
    steps = resolution.get("steps", [])
    analysis["steps_count"] = len(steps)
    analysis["steps"] = steps
    
    # Extract commands
    commands_by_step = resolution.get("commands_by_step", {})
    analysis["commands_by_step"] = commands_by_step
    analysis["commands_count"] = sum(len(cmd_list) for cmd_list in commands_by_step.values())
    
    # Map steps to runbooks (if provenance available)
    provenance = runbook_info.get("provenance_references", [])
    runbook_doc_ids = {rb["document_id"] for rb in runbook_info.get("runbooks_used", [])}
    
    if provenance:
        for prov in provenance:
            prov_doc_id = prov.get("doc_id") or prov.get("document_id")
            if prov_doc_id in runbook_doc_ids:
                # Find which runbook this references
                runbook = next((rb for rb in runbook_info["runbooks_used"] if rb["document_id"] == prov_doc_id), None)
                if runbook:
                    analysis["runbook_mapped_steps"].append({
                        "step_index": len(analysis["runbook_mapped_steps"]),
                        "runbook_title": runbook["title"],
                        "runbook_service": runbook["service"],
                    })
    
    # Extract other fields
    analysis["reasoning"] = resolution.get("reasoning") or resolution.get("rationale", "")
    analysis["risk_level"] = resolution.get("risk_level", "")
    analysis["estimated_time"] = resolution.get("estimated_time_minutes")
    analysis["rollback_plan"] = resolution.get("rollback_plan")
    
    return analysis


def create_ticket_summary(ticket_id: str, alert: Dict, triage_result: Dict, resolution_result: Dict, 
                         runbook_info: Dict, solution_analysis: Dict, expected: Dict) -> Dict[str, Any]:
    """Create comprehensive summary for a single ticket."""
    summary = {
        "ticket_id": ticket_id,
        "timestamp": datetime.now().isoformat(),
        "alert": {
            "title": alert.get("title", ""),
            "description": alert.get("description", "")[:500] + "..." if len(alert.get("description", "")) > 500 else alert.get("description", ""),
            "category": alert.get("labels", {}).get("category", ""),
            "assignment_group": alert.get("labels", {}).get("assignment_group", ""),
        },
        "expected_values": expected,
        "triage": {
            "incident_id": triage_result.get("incident_id") if triage_result else None,
            "severity": triage_result.get("triage", {}).get("severity") if triage_result else None,
            "category": triage_result.get("triage", {}).get("category") if triage_result else None,
            "routing": triage_result.get("triage", {}).get("routing") if triage_result else None,
            "confidence": triage_result.get("triage", {}).get("confidence") if triage_result else None,
            "summary": triage_result.get("triage", {}).get("summary", "")[:300] if triage_result else "",
            "policy_band": triage_result.get("policy_band") if triage_result else None,
        },
        "runbook_usage": runbook_info,
        "resolution": {
            "status": "success" if resolution_result and not resolution_result.get("policy_blocked") else ("policy_blocked" if resolution_result and resolution_result.get("policy_blocked") else "failed"),
            "steps": solution_analysis.get("steps", []),
            "steps_count": solution_analysis.get("steps_count", 0),
            "commands": solution_analysis.get("commands_by_step", {}),
            "commands_count": solution_analysis.get("commands_count", 0),
            "reasoning": solution_analysis.get("reasoning", ""),
            "risk_level": solution_analysis.get("risk_level", ""),
            "estimated_time_minutes": solution_analysis.get("estimated_time_minutes"),
            "rollback_plan": solution_analysis.get("rollback_plan"),
            "runbook_mapped_steps": solution_analysis.get("runbook_mapped_steps", []),
        },
        "solution_generation_process": {
            "runbooks_retrieved": len(runbook_info.get("runbooks_used", [])),
            "runbook_chunks_used": runbook_info.get("runbook_chunks_count", 0),
            "total_evidence_chunks": runbook_info.get("total_evidence_chunks", 0),
            "steps_generated": solution_analysis.get("steps_count", 0),
            "commands_generated": solution_analysis.get("commands_count", 0),
            "runbook_influence": "high" if runbook_info.get("runbook_chunks_count", 0) > 0 else "none",
            "runbook_titles": runbook_info.get("runbook_titles", []),
        },
    }
    
    return summary


def process_test_file(file_path: Path, ai_service_url: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Process a test CSV file and validate agents with detailed tracking."""
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
                expected = {
                    "ticket_id": ticket_id,
                    "category": row.get("category", ""),
                    "assignment_group": row.get("assignment_group", ""),
                    "impact": row.get("impact", ""),
                    "urgency": row.get("urgency", ""),
                    "resolution_comments": row.get("resolution comments", ""),
                }
                
                # Step 1: Call triage agent
                print(f"  → Calling triage agent...")
                triage_response = call_triage_agent(alert, ai_service_url)
                
                if not triage_response:
                    print(f"    ✗ Triage agent call failed")
                    results.append({
                        "ticket_id": ticket_id,
                        "status": "triage_failed",
                        "error": "Triage agent call failed",
                    })
                    continue
                
                incident_id = triage_response.get("incident_id")
                if not incident_id:
                    print(f"    ✗ No incident_id returned")
                    results.append({
                        "ticket_id": ticket_id,
                        "status": "triage_failed",
                        "error": "No incident_id returned",
                    })
                    continue
                
                print(f"    ✓ Triage completed (incident_id: {incident_id})")
                print(f"      Severity: {triage_response.get('triage', {}).get('severity', 'N/A')}")
                print(f"      Category: {triage_response.get('triage', {}).get('category', 'N/A')}")
                print(f"      Routing: {triage_response.get('triage', {}).get('routing', 'N/A')}")
                
                # Step 2: Call resolution agent
                print(f"  → Calling resolution agent...")
                resolution_response = call_resolution_agent(incident_id, ai_service_url)
                
                if not resolution_response:
                    print(f"    ✗ Resolution agent call failed")
                    results.append({
                        "ticket_id": ticket_id,
                        "status": "resolution_failed",
                        "triage": triage_response,
                        "error": "Resolution agent call failed",
                    })
                    continue
                
                if resolution_response.get("policy_blocked"):
                    print(f"    ⚠ Resolution blocked by policy (requires approval)")
                    resolution_response = {"resolution": {}, "policy_blocked": True}
                else:
                    resolution = resolution_response.get("resolution") or resolution_response.get("resolution_output", {})
                    steps_count = len(resolution.get("steps", []))
                    print(f"    ✓ Resolution completed")
                    print(f"      Steps: {steps_count}")
                    print(f"      Risk Level: {resolution.get('risk_level', 'N/A')}")
                
                # Step 3: Extract runbook usage
                print(f"  → Analyzing runbook usage...")
                runbook_info = extract_runbook_usage(triage_response, resolution_response)
                
                print(f"    Runbooks used: {len(runbook_info['runbooks_used'])}")
                print(f"    Runbook chunks: {runbook_info['runbook_chunks_count']}")
                for rb in runbook_info['runbooks_used']:
                    print(f"      - {rb['title']} ({rb['service']})")
                
                # Step 4: Analyze solution generation
                solution_analysis = analyze_solution_generation(resolution_response, runbook_info)
                
                # Step 5: Create comprehensive summary
                summary = create_ticket_summary(
                    ticket_id, alert, triage_response, resolution_response,
                    runbook_info, solution_analysis, expected
                )
                
                results.append(summary)
                print(f"    ✓ Analysis complete")
                
    except Exception as e:
        logger.error(f"Error processing test file {file_path}: {str(e)}", exc_info=True)
        print(f"\n✗ Error processing test file: {str(e)}")
    
    return results


def generate_comprehensive_report(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """Generate comprehensive validation report with detailed summaries."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detailed_report_file = output_dir / f"detailed_validation_report_{timestamp}.json"
    summary_report_file = output_dir / f"validation_summary_{timestamp}.txt"
    markdown_report_file = output_dir / f"validation_report_{timestamp}.md"
    
    # Save detailed JSON report
    with open(detailed_report_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Calculate statistics
    total = len(results)
    triage_success = sum(1 for r in results if r.get("triage", {}).get("incident_id"))
    resolution_success = sum(1 for r in results if r.get("resolution", {}).get("status") == "success")
    resolution_blocked = sum(1 for r in results if r.get("resolution", {}).get("status") == "policy_blocked")
    resolution_failed = sum(1 for r in results if r.get("resolution", {}).get("status") == "failed")
    
    # Runbook usage statistics
    tickets_with_runbooks = sum(1 for r in results if r.get("runbook_usage", {}).get("runbook_chunks_count", 0) > 0)
    total_runbook_chunks = sum(r.get("runbook_usage", {}).get("runbook_chunks_count", 0) for r in results)
    total_steps_generated = sum(r.get("resolution", {}).get("steps_count", 0) for r in results)
    total_commands_generated = sum(r.get("resolution", {}).get("commands_count", 0) for r in results)
    
    # Generate text summary
    summary_lines = [
        "=" * 80,
        "COMPREHENSIVE AGENT VALIDATION REPORT",
        "=" * 80,
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n" + "=" * 80,
        "EXECUTIVE SUMMARY",
        "=" * 80,
        f"\nTotal Tickets Processed: {total}",
        f"Triage Success Rate: {triage_success}/{total} ({triage_success/total*100:.1f}%)" if total > 0 else "N/A",
        f"Resolution Success Rate: {resolution_success}/{total} ({resolution_success/total*100:.1f}%)" if total > 0 else "N/A",
        f"Resolution Blocked (Policy): {resolution_blocked}/{total} ({resolution_blocked/total*100:.1f}%)" if total > 0 else "N/A",
        f"Resolution Failed: {resolution_failed}/{total} ({resolution_failed/total*100:.1f}%)" if total > 0 else "N/A",
        "\n" + "=" * 80,
        "RUNBOOK USAGE ANALYSIS",
        "=" * 80,
        f"\nTickets Using Runbooks: {tickets_with_runbooks}/{total} ({tickets_with_runbooks/total*100:.1f}%)" if total > 0 else "N/A",
        f"Total Runbook Chunks Retrieved: {total_runbook_chunks}",
        f"Average Runbook Chunks per Ticket: {total_runbook_chunks/tickets_with_runbooks:.1f}" if tickets_with_runbooks > 0 else "0",
        "\n" + "=" * 80,
        "SOLUTION GENERATION METRICS",
        "=" * 80,
        f"\nTotal Steps Generated: {total_steps_generated}",
        f"Total Commands Generated: {total_commands_generated}",
        f"Average Steps per Ticket: {total_steps_generated/resolution_success:.1f}" if resolution_success > 0 else "0",
        f"Average Commands per Ticket: {total_commands_generated/resolution_success:.1f}" if resolution_success > 0 else "0",
    ]
    
    # Generate markdown report
    md_lines = [
        "# Comprehensive Agent Validation Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n## Executive Summary",
        f"\n- **Total Tickets Processed:** {total}",
        f"- **Triage Success Rate:** {triage_success}/{total} ({triage_success/total*100:.1f}%)" if total > 0 else "- **Triage Success Rate:** N/A",
        f"- **Resolution Success Rate:** {resolution_success}/{total} ({resolution_success/total*100:.1f}%)" if total > 0 else "- **Resolution Success Rate:** N/A",
        f"- **Resolution Blocked (Policy):** {resolution_blocked}/{total} ({resolution_blocked/total*100:.1f}%)" if total > 0 else "- **Resolution Blocked:** N/A",
        "\n## Runbook Usage Analysis",
        f"\n- **Tickets Using Runbooks:** {tickets_with_runbooks}/{total} ({tickets_with_runbooks/total*100:.1f}%)" if total > 0 else "- **Tickets Using Runbooks:** N/A",
        f"- **Total Runbook Chunks Retrieved:** {total_runbook_chunks}",
        f"- **Average Runbook Chunks per Ticket:** {total_runbook_chunks/tickets_with_runbooks:.1f}" if tickets_with_runbooks > 0 else "- **Average Runbook Chunks per Ticket:** 0",
        "\n## Solution Generation Metrics",
        f"\n- **Total Steps Generated:** {total_steps_generated}",
        f"- **Total Commands Generated:** {total_commands_generated}",
        f"- **Average Steps per Ticket:** {total_steps_generated/resolution_success:.1f}" if resolution_success > 0 else "- **Average Steps per Ticket:** 0",
        f"- **Average Commands per Ticket:** {total_commands_generated/resolution_success:.1f}" if resolution_success > 0 else "- **Average Commands per Ticket:** 0",
        "\n## Detailed Ticket Summaries",
        "\n### Ticket-by-Ticket Analysis",
    ]
    
    # Add detailed ticket summaries
    for idx, result in enumerate(results, 1):
        ticket_id = result.get("ticket_id", f"Ticket_{idx}")
        md_lines.append(f"\n#### {idx}. Ticket {ticket_id}")
        md_lines.append(f"\n**Alert:** {result.get('alert', {}).get('title', 'N/A')}")
        md_lines.append(f"\n**Triage:**")
        triage = result.get("triage", {})
        md_lines.append(f"- Severity: {triage.get('severity', 'N/A')}")
        md_lines.append(f"- Category: {triage.get('category', 'N/A')}")
        md_lines.append(f"- Routing: {triage.get('routing', 'N/A')}")
        
        md_lines.append(f"\n**Runbook Usage:**")
        runbook_usage = result.get("runbook_usage", {})
        md_lines.append(f"- Runbooks Used: {len(runbook_usage.get('runbooks_used', []))}")
        md_lines.append(f"- Runbook Chunks: {runbook_usage.get('runbook_chunks_count', 0)}")
        for rb in runbook_usage.get("runbooks_used", []):
            md_lines.append(f"  - {rb.get('title', 'Unknown')} ({rb.get('service', 'Unknown')})")
        
        md_lines.append(f"\n**Resolution:**")
        resolution = result.get("resolution", {})
        md_lines.append(f"- Status: {resolution.get('status', 'N/A')}")
        md_lines.append(f"- Steps Count: {resolution.get('steps_count', 0)}")
        md_lines.append(f"- Commands Count: {resolution.get('commands_count', 0)}")
        md_lines.append(f"- Risk Level: {resolution.get('risk_level', 'N/A')}")
        
        if resolution.get("steps"):
            md_lines.append(f"\n**Resolution Steps:**")
            for i, step in enumerate(resolution.get("steps", []), 1):
                md_lines.append(f"{i}. {step}")
        
        solution_process = result.get("solution_generation_process", {})
        md_lines.append(f"\n**Solution Generation Process:**")
        md_lines.append(f"- Runbooks Retrieved: {solution_process.get('runbooks_retrieved', 0)}")
        md_lines.append(f"- Runbook Influence: {solution_process.get('runbook_influence', 'N/A')}")
        md_lines.append(f"- Steps Generated: {solution_process.get('steps_generated', 0)}")
        md_lines.append(f"- Commands Generated: {solution_process.get('commands_generated', 0)}")
        
        md_lines.append("\n---")
    
    # Save reports
    with open(summary_report_file, "w") as f:
        f.write("\n".join(summary_lines))
    
    with open(markdown_report_file, "w") as f:
        f.write("\n".join(md_lines))
    
    # Print summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    for line in summary_lines[5:]:  # Skip header
        print(line)
    
    print(f"\n{'='*80}")
    print(f"Reports Generated:")
    print(f"  - Detailed JSON: {detailed_report_file}")
    print(f"  - Text Summary: {summary_report_file}")
    print(f"  - Markdown Report: {markdown_report_file}")
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced agent validation with detailed runbook tracking",
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

    print("\n" + "=" * 80)
    print("Enhanced Agent Validation Script")
    print("=" * 80)
    logger.info("Starting enhanced agent validation...")

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

    # Generate comprehensive report
    generate_comprehensive_report(all_results, output_dir)

    print("\n✓ Enhanced validation completed!")
    logger.info("Enhanced validation completed successfully")


if __name__ == "__main__":
    main()

