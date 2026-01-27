#!/usr/bin/env python3
"""Ingest ServiceNow tickets from CSV files.

This script parses CSV files from the tickets_data/ folder and ingests them
as historical incidents using the field mappings configuration.

Usage:
    python scripts/data/ingest_servicenow_tickets.py --dir tickets_data
    python scripts/data/ingest_servicenow_tickets.py --file "tickets_data/Database Alerts Filtered - Sheet1.csv"
"""

import argparse
import csv
import sys
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ai_service.core import get_field_mappings_config, get_logger, setup_logging
from ingestion.normalizers import clean_description_text
from ingestion.models import IngestIncident
import requests

# Setup logging to ensure console output
setup_logging(log_level="INFO", service_name="ingestion_script")
logger = get_logger(__name__)

# Default ingestion service URL
INGESTION_SERVICE_URL = "http://localhost:8002"


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse ServiceNow date format (supports MM/DD/YYYY, DD/MM/YYYY, and ISO formats)."""
    if not date_str or date_str.strip() == "":
        return None

    # Try multiple date formats (order matters - try most specific first)
    formats = [
        "%d/%m/%Y %H:%M",  # DD/MM/YYYY HH:mm (e.g., "29/11/2025 23:03")
        "%m/%d/%Y %H:%M",  # MM/DD/YYYY HH:mm (e.g., "11/29/2025 23:03")
        "%d/%m/%Y",  # DD/MM/YYYY (e.g., "29/11/2025")
        "%m/%d/%Y",  # MM/DD/YYYY (e.g., "11/29/2025")
        "%Y-%m-%d %H:%M:%S",  # ISO format with time (e.g., "2025-11-29 23:03:00")
        "%Y-%m-%d %H:%M",  # ISO format with time (no seconds)
        "%Y-%m-%d",  # ISO date only (e.g., "2025-11-29")
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    logger.warning(f"Could not parse date: {date_str}")
    return None


def derive_severity(impact: str, urgency: str, severity_mapping: Dict) -> str:
    """Derive severity from impact and urgency using mapping configuration."""
    # Extract numeric values (e.g., "1 - High" -> "1")
    impact_val = impact.split()[0] if impact else "3"
    urgency_val = urgency.split()[0] if urgency else "3"

    # Create key (e.g., "1-1", "2-3")
    key = f"{impact_val}-{urgency_val}"

    # Look up in mapping
    severity = severity_mapping.get(
        key, severity_mapping.get("default_severity", "medium")
    )
    return severity


def map_csv_row_to_incident(
    row: Dict, field_mappings: Dict, severity_mapping: Dict
) -> IngestIncident:
    """Map CSV row to IngestIncident using field mappings configuration."""
    mappings = field_mappings.get("field_mappings", {})

    # Extract fields using mappings
    incident_id = row.get(
        mappings.get("incident_id", {}).get("source_column", "number"), ""
    )
    title = row.get(
        mappings.get("title", {}).get("source_column", "short_description"), ""
    )
    description = row.get(
        mappings.get("description", {}).get("source_column", "description"), ""
    )
    category = row.get(
        mappings.get("category", {}).get("source_column", "category"), ""
    )

    # Clean description to normalize whitespace (matches query normalization during triage)
    description = clean_description_text(description)

    # Validate required fields before proceeding
    if not title or not title.strip():
        raise ValueError(
            f"Missing required field 'title' for incident {incident_id}"
        )
    if not description or not description.strip():
        raise ValueError(
            f"Missing required field 'description' for incident {incident_id}"
        )

    # Parse timestamp
    timestamp = None
    timestamp_col = mappings.get("timestamp", {}).get(
        "source_column", "opened_at"
    )
    if timestamp_col in row:
        timestamp = parse_date(row[timestamp_col])
        # Note: timestamp is optional, so we don't fail if parsing fails
        # But we log a warning (already done in parse_date)

    # Derive severity from impact + urgency
    impact = row.get(
        mappings.get("impact", {}).get("source_column", "impact"), "3 - Low"
    )
    urgency = row.get(
        mappings.get("urgency", {}).get("source_column", "urgency"), "3 - Low"
    )
    severity = derive_severity(impact, urgency, severity_mapping)

    # Extract affected services from cmdb_ci
    affected_services = []
    cmdb_ci = row.get(
        mappings.get("affected_services", {}).get("source_column", "cmdb_ci"), ""
    )
    if cmdb_ci:
        affected_services = [cmdb_ci]

    # Extract assignment_group
    assignment_group = row.get(
        mappings.get("assignment_group", {}).get(
            "source_column", "assignment_group"
        ),
        "",
    )

    # Build comprehensive tags
    tags = {
        "type": "historical_incident",
        "ticket_id": incident_id,
        "canonical_incident_key": incident_id,  # Using incident number as canonical key
        "category": category,
        "severity": severity,
        "assignment_group": assignment_group,
        "state": row.get(
            mappings.get("state", {}).get("source_column", "state"), ""
        ),
        "impact": impact,
        "urgency": urgency,
    }

    # Add optional fields to tags
    problem_id = row.get(
        mappings.get("problem_id", {}).get("source_column", "problem_id"), ""
    )
    if problem_id:
        tags["problem_id"] = problem_id

    # Extract close_notes
    close_notes = row.get("close_notes", "")

    # Build metadata - IMPORTANT: assignment_group, impact, urgency, and close_notes must be in metadata
    # so that create_incident_signature() can extract them for the incident_signatures table
    metadata = {
        "source": "servicenow",
        "opened_by": row.get(
            mappings.get("opened_by", {}).get("source_column", "opened_by"), ""
        ),
        "sys_updated_on": row.get(
            mappings.get("sys_updated_on", {}).get(
                "source_column", "sys_updated_on"
            ),
            "",
        ),
        "u_reopen_count": row.get(
            mappings.get("u_reopen_count", {}).get(
                "source_column", "u_reopen_count"
            ),
            "",
        ),
        # Store assignment_group, impact, urgency, and close_notes in metadata for incident_signatures table
        "assignment_group": assignment_group if assignment_group else None,
        "impact": impact if impact else None,
        "urgency": urgency if urgency else None,
        "close_notes": close_notes if close_notes else None,
    }

    return IngestIncident(
        incident_id=incident_id,
        title=title,
        description=description,
        severity=severity,
        category=category,
        affected_services=affected_services,
        timestamp=timestamp,
        metadata=metadata,
        tags=tags,
    )


def ingest_incident(
    incident: IngestIncident, ingestion_url: str = INGESTION_SERVICE_URL
) -> tuple[bool, Optional[str]]:
    """Ingest a single incident via the ingestion API.

    Returns:
        Tuple of (success: bool, document_id: Optional[str])
    """
    try:
        response = requests.post(
            f"{ingestion_url}/ingest/incident",
            json=incident.model_dump(mode="json", exclude_none=True),
            timeout=60,  # Increased timeout for embedding generation
        )
        response.raise_for_status()
        result = response.json()
        signature_id = result.get("signature_id") or result.get(
            "chunk_id"
        )  # Support both formats
        incident_signature_id = result.get("incident_signature_id")
        logger.info(
            f"Incident signature ingested: signature_id={signature_id}, incident_signature_id={incident_signature_id}"
        )
        return True, signature_id
    except Exception as e:
        logger.error(
            f"Failed to ingest incident {incident.incident_id}: {str(e)}"
        )
        return False, None


def split_incidents_for_testing(
    incidents: List[IngestIncident], test_percentage: float = 0.1
) -> Tuple[List[IngestIncident], List[IngestIncident]]:
    """Split incidents into ingestion set (90%) and test set (10%).

    Args:
        incidents: List of incidents to split
        test_percentage: Percentage to reserve for testing (default: 0.1 = 10%)

    Returns:
        Tuple of (incidents_to_ingest, incidents_for_testing)
    """
    if not incidents:
        return [], []

    # Shuffle for random selection
    shuffled = incidents.copy()
    random.seed(42)  # Fixed seed for reproducibility
    random.shuffle(shuffled)

    # Calculate split point
    total = len(shuffled)
    test_count = max(1, int(total * test_percentage))  # At least 1 for testing

    test_incidents = shuffled[:test_count]
    ingest_incidents = shuffled[test_count:]

    return ingest_incidents, test_incidents


def save_test_incidents_to_file(
    incidents: List[IngestIncident], output_file: Path
) -> None:
    """Save test incidents to a CSV file (always replaces the file).

    Args:
        incidents: List of incidents to save
        output_file: Path to output CSV file
    """
    if not incidents:
        return

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Get field names from first incident
    first_incident = incidents[0]
    fieldnames = list(
        first_incident.model_dump(mode="json", exclude_none=True).keys()
    )

    # Write to CSV (always replace, not append)
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for incident in incidents:
            # Convert to dict, handling datetime serialization
            incident_dict = incident.model_dump(mode="json", exclude_none=True)
            # Convert datetime to ISO format string for CSV
            if "timestamp" in incident_dict and incident_dict["timestamp"]:
                if isinstance(incident_dict["timestamp"], datetime):
                    incident_dict["timestamp"] = incident_dict[
                        "timestamp"
                    ].isoformat()
            writer.writerow(incident_dict)

    logger.info(f"Saved {len(incidents)} test incidents to {output_file}")


def ingest_csv_file(
    file_path: Path,
    field_mappings: Dict,
    severity_mapping: Dict,
    ingestion_url: str,
    test_percentage: float = 0.1,
    test_output_file: Optional[Path] = None,
) -> tuple[int, int, List[IngestIncident]]:
    """Ingest all rows from a CSV file with improved progress reporting.

    Args:
        file_path: Path to CSV file
        field_mappings: Field mapping configuration
        severity_mapping: Severity mapping configuration
        ingestion_url: Ingestion service URL
        test_percentage: Percentage of incidents to reserve for testing (default: 0.1 = 10%)
        test_output_file: Optional path to save test incidents (default: tickets_data/test_incidents.csv)
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"Processing: {file_path.name}")
    logger.info(f"{'='*70}")

    success_count = 0
    error_count = 0
    start_time = time.time()

    try:
        # First pass: Read all rows and parse incidents
        logger.info("  Reading and parsing CSV file...")
        incidents = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                try:
                    incident = map_csv_row_to_incident(
                        row, field_mappings, severity_mapping
                    )
                    incidents.append(incident)
                except Exception as e:
                    error_count += 1
                    error_msg = f"  Error parsing row {row_num}: {str(e)}"
                    logger.warning(f"     WARNING: {error_msg}")
                    continue

        total_rows = len(incidents)
        logger.info(f"  Parsed {total_rows} ticket(s) successfully")

        if total_rows == 0:
            logger.warning("  WARNING: No valid tickets to ingest")
            return 0, error_count, []

        # Split incidents: 90% for ingestion, 10% for testing
        test_incidents = []
        if test_percentage > 0:
            ingest_incidents, test_incidents = split_incidents_for_testing(
                incidents, test_percentage
            )

            # Save test incidents to file if output file specified (for single file mode)
            if test_output_file:
                save_test_incidents_to_file(test_incidents, test_output_file)
                logger.info(
                    f"  Reserved {len(test_incidents)} ticket(s) for testing -> {test_output_file.name}"
                )
            else:
                logger.info(
                    f"  Reserved {len(test_incidents)} ticket(s) for testing"
                )
            logger.info(
                f"  Ingesting {len(ingest_incidents)} ticket(s) ({100*(1-test_percentage):.0f}%)"
            )

            incidents = ingest_incidents  # Use only the ingestion set

        # Second pass: Ingest incidents (individual requests with progress)
        logger.info(f"  Ingesting {total_rows} ticket(s)...")
        logger.info(f"  Progress: [{' ' * 50}] 0%")

        for idx, incident in enumerate(incidents, 1):
            # Calculate progress percentage
            progress = int((idx / total_rows) * 100)
            filled = int(progress / 2)  # 50 chars = 100%

            # Estimate time remaining
            elapsed = time.time() - start_time
            if idx > 1:
                avg_time_per_incident = elapsed / (idx - 1)
                remaining = avg_time_per_incident * (total_rows - idx + 1)
                if remaining > 60:
                    eta_str = (
                        f" (ETA: {int(remaining/60)}m {int(remaining%60)}s)"
                    )
                else:
                    eta_str = f" (ETA: {int(remaining)}s)"
            else:
                eta_str = ""

            # Update progress bar
            incident_id = incident.incident_id or f"row_{idx}"
            title_preview = (
                (incident.title[:40] + "...")
                if len(incident.title) > 40
                else incident.title
            )
            logger.info(
                f"  Progress: [{'=' * filled}{' ' * (50 - filled)}] {progress}% - {title_preview}{eta_str}"
            )

            success, _ = ingest_incident(incident, ingestion_url)
            if success:
                success_count += 1
            else:
                error_count += 1
                # Show error on new line but keep progress bar
                logger.warning(f"     WARNING: Failed: {incident_id}")
                logger.info(
                    f"  Progress: [{'=' * filled}{' ' * (50 - filled)}] {progress}%"
                )

        logger.info(f"  Progress: [{'=' * 50}] 100% - Complete!")

        elapsed_time = time.time() - start_time
        logger.info(f"  Completed in {elapsed_time:.1f}s")
        logger.info(f"  Success: {success_count}, Errors: {error_count}")
        if success_count > 0:
            logger.info(
                f"  Average: {elapsed_time/success_count:.2f}s per ticket"
            )

    except Exception as e:
        logger.error(f"Error reading CSV file {file_path}: {str(e)}")
        raise

    return success_count, error_count, test_incidents


def main():
    # Setup logging first to ensure output is visible
    setup_logging(log_level="INFO", service_name="ingestion_script")

    parser = argparse.ArgumentParser(
        description="Ingest ServiceNow tickets from CSV files"
    )
    parser.add_argument("--dir", type=str, help="Directory containing CSV files")
    parser.add_argument("--file", type=str, help="Single CSV file to ingest")
    parser.add_argument(
        "--ingestion-url",
        type=str,
        default=INGESTION_SERVICE_URL,
        help=f"Ingestion service URL (default: {INGESTION_SERVICE_URL})",
    )
    parser.add_argument(
        "--test-percentage",
        type=float,
        default=0.1,
        help="Percentage of incidents to reserve for testing (default: 0.1 = 10%%)",
    )
    parser.add_argument(
        "--test-output-file",
        type=str,
        default=None,
        help="Path to save test incidents CSV (default: <input_dir>/test_incidents.csv)",
    )
    parser.add_argument(
        "--no-test-split",
        action="store_true",
        help="Disable test split (ingest 100%% of data)",
    )

    args = parser.parse_args()

    if not args.dir and not args.file:
        parser.error("Either --dir or --file must be provided")

    # Startup message
    logger.info("=" * 70)
    logger.info("ServiceNow Ticket Ingestion Script")
    logger.info("=" * 70)
    logger.info("Starting ServiceNow ticket ingestion...")

    # Load field mappings configuration
    try:
        logger.info(" Loading field mappings configuration...")
        field_mappings_config = get_field_mappings_config()
        servicenow_mappings = field_mappings_config.get("servicenow_csv", {})
        severity_mapping = field_mappings_config.get("severity_mapping", {}).get(
            "impact_urgency_to_severity", {}
        )
        logger.info(" Configuration loaded successfully")
    except Exception as e:
        logger.error(f" Failed to load field mappings: {str(e)}")
        sys.exit(1)

    total_success = 0
    total_errors = 0
    all_test_incidents = []  # Accumulate test incidents from all files

    if args.file:
        # Process single file
        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f" File not found: {file_path}")
            sys.exit(1)

        test_output = (
            Path(args.test_output_file)
            if args.test_output_file
            else file_path.parent / "test_incidents.csv"
        )
        success, errors, test_incidents = ingest_csv_file(
            file_path,
            servicenow_mappings,
            severity_mapping,
            args.ingestion_url,
            test_percentage=0 if args.no_test_split else args.test_percentage,
            test_output_file=None,  # Don't save per-file, accumulate instead
        )
        total_success += success
        total_errors += errors
        if test_incidents:
            all_test_incidents.extend(test_incidents)

    else:
        # Process directory
        dir_path = Path(args.dir)
        if not dir_path.exists():
            logger.error(f" Directory not found: {dir_path}")
            sys.exit(1)

        csv_files = list(dir_path.glob("*.csv"))
        if not csv_files:
            logger.warning(f"  No CSV files found in {dir_path}")
            sys.exit(0)

        logger.info(f"Found {len(csv_files)} CSV file(s) to process")

        for csv_file in csv_files:
            success, errors, test_incidents = ingest_csv_file(
                csv_file,
                servicenow_mappings,
                severity_mapping,
                args.ingestion_url,
                test_percentage=(
                    0 if args.no_test_split else args.test_percentage
                ),
                test_output_file=None,  # Don't save per-file, accumulate instead
            )
            total_success += success
            total_errors += errors
            if test_incidents:
                all_test_incidents.extend(test_incidents)

        # Save all accumulated test incidents to a single file (always replace)
        if all_test_incidents and not args.no_test_split:
            test_output = (
                Path(args.test_output_file)
                if args.test_output_file
                else dir_path / "test_incidents.csv"
            )
            save_test_incidents_to_file(all_test_incidents, test_output)
            logger.info(
                f"Saved {len(all_test_incidents)} test incidents to {test_output}"
            )

    logger.info(f"\n{'='*70}")
    logger.info(f"Ingestion Summary:")
    logger.info(f"   Successfully ingested: {total_success} ticket(s)")
    logger.info(f"   Errors: {total_errors} ticket(s)")
    logger.info(f"{'='*70}")

    # Verify embeddings were created
    if total_success > 0:
        logger.info("\n" + "=" * 70)
        logger.info("Verification")
        logger.info("=" * 70)
        logger.info("Verifying embeddings in database...")
        try:
            from db.connection import get_db_connection_context

            with get_db_connection_context() as conn:
                cur = conn.cursor()

                # Count incident signatures
                cur.execute("SELECT COUNT(*) FROM incident_signatures;")
                sig_result = cur.fetchone()
                sig_count = (
                    sig_result["count"]
                    if isinstance(sig_result, dict)
                    else sig_result[0]
                )

                # Count incident signatures with embeddings
                cur.execute(
                    "SELECT COUNT(*) FROM incident_signatures WHERE embedding IS NOT NULL;"
                )
                embed_result = cur.fetchone()
                embed_count = (
                    embed_result["count"]
                    if isinstance(embed_result, dict)
                    else embed_result[0]
                )

                # Count incident signatures with tsv
                cur.execute(
                    "SELECT COUNT(*) FROM incident_signatures WHERE tsv IS NOT NULL;"
                )
                tsv_result = cur.fetchone()
                tsv_count = (
                    tsv_result["count"]
                    if isinstance(tsv_result, dict)
                    else tsv_result[0]
                )

                cur.close()

            logger.info(f"\nDatabase Verification:")
            logger.info(f"   Incident signatures created: {sig_count}")
            logger.info(
                f"   Signatures with embeddings: {embed_count}/{sig_count}"
            )
            logger.info(f"   Signatures with tsvector: {tsv_count}/{sig_count}")

            if (
                embed_count == sig_count
                and sig_count > 0
                and tsv_count == sig_count
            ):
                logger.info(
                    f"\n   SUCCESS: All {sig_count} incident signatures have embeddings and tsvector!"
                )
            elif embed_count < sig_count or tsv_count < sig_count:
                missing_embed = sig_count - embed_count
                missing_tsv = sig_count - tsv_count
                logger.warning(
                    f"\n   WARNING: {missing_embed} missing embeddings, {missing_tsv} missing tsvector!"
                )
            else:
                logger.warning(
                    f"\n   WARNING: No incident signatures found in database!"
                )

        except Exception as e:
            logger.warning(f"\n   Could not verify embeddings: {str(e)}")
            logger.warning(
                f"   You can manually verify using: python scripts/db/verify_db.py"
            )

    if total_errors > 0:
        logger.error(
            f"\n  Completed with {total_errors} error(s). Check logs for details."
        )
        sys.exit(1)
    else:
        logger.info(f"\n Ingestion completed successfully!")


if __name__ == "__main__":
    main()
