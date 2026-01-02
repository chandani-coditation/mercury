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
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ai_service.core import get_field_mappings_config, get_logger, setup_logging
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
    severity = severity_mapping.get(key, severity_mapping.get("default_severity", "medium"))
    return severity


def map_csv_row_to_incident(
    row: Dict, field_mappings: Dict, severity_mapping: Dict
) -> IngestIncident:
    """Map CSV row to IngestIncident using field mappings configuration."""
    mappings = field_mappings.get("field_mappings", {})

    # Extract fields using mappings
    incident_id = row.get(mappings.get("incident_id", {}).get("source_column", "number"), "")
    title = row.get(mappings.get("title", {}).get("source_column", "short_description"), "")
    description = row.get(mappings.get("description", {}).get("source_column", "description"), "")
    category = row.get(mappings.get("category", {}).get("source_column", "category"), "")

    # Validate required fields before proceeding
    if not title or not title.strip():
        raise ValueError(f"Missing required field 'title' for incident {incident_id}")
    if not description or not description.strip():
        raise ValueError(f"Missing required field 'description' for incident {incident_id}")

    # Parse timestamp
    timestamp = None
    timestamp_col = mappings.get("timestamp", {}).get("source_column", "opened_at")
    if timestamp_col in row:
        timestamp = parse_date(row[timestamp_col])
        # Note: timestamp is optional, so we don't fail if parsing fails
        # But we log a warning (already done in parse_date)

    # Derive severity from impact + urgency
    impact = row.get(mappings.get("impact", {}).get("source_column", "impact"), "3 - Low")
    urgency = row.get(mappings.get("urgency", {}).get("source_column", "urgency"), "3 - Low")
    severity = derive_severity(impact, urgency, severity_mapping)

    # Extract affected services from cmdb_ci
    affected_services = []
    cmdb_ci = row.get(mappings.get("affected_services", {}).get("source_column", "cmdb_ci"), "")
    if cmdb_ci:
        affected_services = [cmdb_ci]

    # Extract assignment_group
    assignment_group = row.get(
        mappings.get("assignment_group", {}).get("source_column", "assignment_group"), ""
    )

    # Build comprehensive tags
    tags = {
        "type": "historical_incident",
        "ticket_id": incident_id,
        "canonical_incident_key": incident_id,  # Using incident number as canonical key
        "category": category,
        "severity": severity,
        "assignment_group": assignment_group,
        "state": row.get(mappings.get("state", {}).get("source_column", "state"), ""),
        "impact": impact,
        "urgency": urgency,
    }

    # Add optional fields to tags
    problem_id = row.get(mappings.get("problem_id", {}).get("source_column", "problem_id"), "")
    if problem_id:
        tags["problem_id"] = problem_id

    # Extract close_notes
    close_notes = row.get("close_notes", "")
    
    # Build metadata - IMPORTANT: assignment_group, impact, urgency, and close_notes must be in metadata
    # so that create_incident_signature() can extract them for the incident_signatures table
    metadata = {
        "source": "servicenow",
        "opened_by": row.get(mappings.get("opened_by", {}).get("source_column", "opened_by"), ""),
        "sys_updated_on": row.get(
            mappings.get("sys_updated_on", {}).get("source_column", "sys_updated_on"), ""
        ),
        "u_reopen_count": row.get(
            mappings.get("u_reopen_count", {}).get("source_column", "u_reopen_count"), ""
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
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        signature_id = result.get("signature_id") or result.get("chunk_id")  # Support both formats
        incident_signature_id = result.get("incident_signature_id")
        logger.info(f"Incident signature ingested: signature_id={signature_id}, incident_signature_id={incident_signature_id}")
        return True, signature_id
    except Exception as e:
        logger.error(f"Failed to ingest incident {incident.incident_id}: {str(e)}")
        return False, None


def ingest_csv_file(
    file_path: Path, field_mappings: Dict, severity_mapping: Dict, ingestion_url: str
) -> tuple[int, int]:
    """Ingest all rows from a CSV file."""
    print(f"\n Processing: {file_path.name}")
    logger.info(f"Processing CSV file: {file_path}")

    success_count = 0
    error_count = 0

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            total_rows = sum(1 for _ in reader)  # Count total rows
            f.seek(0)  # Reset file pointer
            reader = csv.DictReader(f)  # Recreate reader

            print(f"  Found {total_rows} ticket(s) to process\n")
            logger.info(f"  Found {total_rows} ticket(s) to process")

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (row 1 is header)
                try:
                    incident = map_csv_row_to_incident(row, field_mappings, severity_mapping)
                    incident_id = incident.incident_id or f"row_{row_num}"
                    title_preview = (
                        (incident.title[:50] + "...")
                        if len(incident.title) > 50
                        else incident.title
                    )

                    # Print progress to console
                    print(
                        f"  [{row_num-1}/{total_rows}] Ingesting ticket {incident_id}: {title_preview}"
                    )
                    logger.info(
                        f"  [{row_num-1}/{total_rows}] Ingesting ticket {incident_id}: {title_preview}"
                    )

                    success, signature_id = ingest_incident(incident, ingestion_url)

                    if success:
                        success_count += 1
                        print(f"     Successfully ingested (signature_id: {signature_id})")
                        logger.info(f"     Successfully ingested (signature_id: {signature_id})")
                    else:
                        error_count += 1
                        print(f"     Failed to ingest ticket {incident_id}")
                        logger.error(f"     Failed to ingest ticket {incident_id}")

                except Exception as e:
                    error_count += 1
                    error_msg = f"  Error processing row {row_num} in {file_path.name}: {str(e)}"
                    print(f"     {error_msg}")
                    logger.error(error_msg)
                    continue

    except Exception as e:
        logger.error(f"Error reading CSV file {file_path}: {str(e)}")
        raise

    return success_count, error_count


def main():
    # Setup logging first to ensure output is visible
    setup_logging(log_level="INFO", service_name="ingestion_script")

    parser = argparse.ArgumentParser(description="Ingest ServiceNow tickets from CSV files")
    parser.add_argument("--dir", type=str, help="Directory containing CSV files")
    parser.add_argument("--file", type=str, help="Single CSV file to ingest")
    parser.add_argument(
        "--ingestion-url",
        type=str,
        default=INGESTION_SERVICE_URL,
        help=f"Ingestion service URL (default: {INGESTION_SERVICE_URL})",
    )

    args = parser.parse_args()

    if not args.dir and not args.file:
        parser.error("Either --dir or --file must be provided")

    # Print startup message
    print("=" * 70)
    print("ServiceNow Ticket Ingestion Script")
    print("=" * 70)
    logger.info("Starting ServiceNow ticket ingestion...")

    # Load field mappings configuration
    try:
        print(" Loading field mappings configuration...")
        field_mappings_config = get_field_mappings_config()
        servicenow_mappings = field_mappings_config.get("servicenow_csv", {})
        severity_mapping = field_mappings_config.get("severity_mapping", {}).get(
            "impact_urgency_to_severity", {}
        )
        print(" Configuration loaded successfully\n")
    except Exception as e:
        print(f" Failed to load field mappings: {str(e)}")
        logger.error(f"Failed to load field mappings: {str(e)}")
        sys.exit(1)

    total_success = 0
    total_errors = 0

    if args.file:
        # Process single file
        file_path = Path(args.file)
        if not file_path.exists():
            print(f" File not found: {file_path}")
            logger.error(f"File not found: {file_path}")
            sys.exit(1)

        success, errors = ingest_csv_file(
            file_path, servicenow_mappings, severity_mapping, args.ingestion_url
        )
        total_success += success
        total_errors += errors

    else:
        # Process directory
        dir_path = Path(args.dir)
        if not dir_path.exists():
            print(f" Directory not found: {dir_path}")
            logger.error(f"Directory not found: {dir_path}")
            sys.exit(1)

        csv_files = list(dir_path.glob("*.csv"))
        if not csv_files:
            print(f"  No CSV files found in {dir_path}")
            logger.warning(f"No CSV files found in {dir_path}")
            sys.exit(0)

        print(f"\n📁 Found {len(csv_files)} CSV file(s) to process\n")
        logger.info(f"Found {len(csv_files)} CSV file(s)")

        for csv_file in csv_files:
            success, errors = ingest_csv_file(
                csv_file, servicenow_mappings, severity_mapping, args.ingestion_url
            )
            total_success += success
            total_errors += errors

    print(f"\n{'='*70}")
    print(f"Ingestion Summary:")
    print(f"   Successfully ingested: {total_success} ticket(s)")
    print(f"   Errors: {total_errors} ticket(s)")
    print(f"{'='*70}")
    logger.info(f"\n{'='*70}")
    logger.info(f"Ingestion Summary:")
    logger.info(f"   Successfully ingested: {total_success} ticket(s)")
    logger.info(f"   Errors: {total_errors} ticket(s)")
    logger.info(f"{'='*70}")

    # Verify embeddings were created
    if total_success > 0:
        print("\n Verifying embeddings in database...")
        logger.info("\nVerifying embeddings in database...")
        try:
            from db.connection import get_db_connection

            conn = get_db_connection()
            cur = conn.cursor()

            # Count incident signatures (stored in dedicated table)
            cur.execute(
                """
                SELECT COUNT(*) as sig_count 
                FROM incident_signatures
            """
            )
            sig_result = cur.fetchone()
            sig_count = (
                sig_result["sig_count"] if isinstance(sig_result, dict) else sig_result[0]
            )

            # Count incident signatures with embeddings
            cur.execute(
                """
                SELECT COUNT(*) as embed_count 
                FROM incident_signatures 
                WHERE embedding IS NOT NULL
            """
            )
            embed_result = cur.fetchone()
            embed_count = (
                embed_result["embed_count"] if isinstance(embed_result, dict) else embed_result[0]
            )

            # Get embedding dimension sample
            cur.execute(
                """
                SELECT embedding::text as embedding_text
                FROM incident_signatures 
                WHERE embedding IS NOT NULL
                LIMIT 1
            """
            )
            sample = cur.fetchone()
            embedding_dim = None
            if sample:
                embedding_text = sample["embedding_text"] if isinstance(sample, dict) else sample[0]
                if embedding_text:
                    embedding_dim = embedding_text.count(",") + 1

            conn.close()

            print(f"\nDatabase Verification:")
            print(f"   Incident signatures stored: {sig_count}")
            print(f"   Signatures with embeddings: {embed_count}/{sig_count}")
            logger.info(f"\nDatabase Verification:")
            logger.info(f"   Incident signatures stored: {sig_count}")
            logger.info(f"   Signatures with embeddings: {embed_count}/{sig_count}")

            if embedding_dim:
                print(f"   Embedding dimension: {embedding_dim}")
                logger.info(f"   Embedding dimension: {embedding_dim}")

            if embed_count == sig_count and sig_count > 0:
                print(f"\n   SUCCESS: All {sig_count} incident signatures have embeddings!")
                logger.info(f"\n   SUCCESS: All {sig_count} incident signatures have embeddings!")
            elif embed_count < sig_count:
                print(f"\n    WARNING: {sig_count - embed_count} signatures are missing embeddings!")
                logger.warning(
                    f"\n    WARNING: {sig_count - embed_count} signatures are missing embeddings!"
                )
            else:
                print(f"\n    WARNING: No incident signatures found in database!")
                logger.warning(f"\n    WARNING: No incident signatures found in database!")

        except Exception as e:
            print(f"    Could not verify embeddings: {str(e)}")
            print(f"     You can manually verify using: python scripts/db/verify_db.py")
            logger.warning(f"    Could not verify embeddings: {str(e)}")
            logger.warning(f"     You can manually verify using: python scripts/db/verify_db.py")

    if total_errors > 0:
        print(f"\n  Completed with {total_errors} error(s). Check logs for details.")
        sys.exit(1)
    else:
        print(f"\n Ingestion completed successfully!")


if __name__ == "__main__":
    main()
