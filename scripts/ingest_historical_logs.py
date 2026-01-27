#!/usr/bin/env python3
"""
Script to ingest historical logs for resolved tickets into the database.

This script fetches error logs from InfluxDB for historical tickets and stores them
in the database for similarity matching in future triage operations.

Usage:
    # Ingest logs for a single ticket
    python scripts/ingest_historical_logs.py --ticket-id INC6052852 --date "2024-01-15T14:30:00Z"
    
    # Ingest logs for multiple tickets from a CSV file
    python scripts/ingest_historical_logs.py --csv tickets.csv
    
    # CSV format: ticket_id,created_date,incident_id (incident_id is optional)
    # Example:
    # INC6052852,2024-01-15T14:30:00Z,uuid-1234
    # INC6052853,2024-01-16T10:00:00Z,
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ingestion.log_ingestion import ingest_logs_for_ticket
from ai_service.core import get_logger

logger = get_logger(__name__)


def parse_date(date_str: str) -> datetime:
    """Parse date from string (ISO format)."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception as e:
        raise ValueError(f"Invalid date format '{date_str}': {e}")


def ingest_single_ticket(ticket_id: str, created_date: str, incident_id: str = None):
    """Ingest logs for a single ticket."""
    logger.info(f"Ingesting logs for ticket {ticket_id}")
    
    try:
        # Parse date
        creation_date = parse_date(created_date)
        
        # Ingest logs
        inserted_count = ingest_logs_for_ticket(
            ticket_id=ticket_id,
            ticket_creation_date=creation_date,
            incident_id=incident_id,
        )
        
        logger.info(f"Successfully ingested {inserted_count} logs for ticket {ticket_id}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"Failed to ingest logs for ticket {ticket_id}: {e}", exc_info=True)
        return 0


def ingest_from_csv(csv_path: str):
    """Ingest logs for multiple tickets from a CSV file."""
    logger.info(f"Ingesting logs from CSV: {csv_path}")
    
    if not Path(csv_path).exists():
        logger.error(f"CSV file not found: {csv_path}")
        return
    
    total_tickets = 0
    total_logs = 0
    failed_tickets = []
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        
        # Validate CSV headers
        required_headers = ['ticket_id', 'created_date']
        if not all(h in reader.fieldnames for h in required_headers):
            logger.error(f"CSV must have columns: {', '.join(required_headers)}")
            logger.error(f"Found columns: {', '.join(reader.fieldnames)}")
            return
        
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
            ticket_id = row['ticket_id'].strip()
            created_date = row['created_date'].strip()
            incident_id = row.get('incident_id', '').strip() or None
            
            if not ticket_id or not created_date:
                logger.warning(f"Row {row_num}: Skipping empty ticket_id or created_date")
                continue
            
            try:
                inserted_count = ingest_single_ticket(ticket_id, created_date, incident_id)
                total_tickets += 1
                total_logs += inserted_count
            except Exception as e:
                logger.error(f"Row {row_num}: Failed to ingest {ticket_id}: {e}")
                failed_tickets.append(ticket_id)
    
    # Print summary
    print("\n" + "="*60)
    print("INGESTION SUMMARY")
    print("="*60)
    print(f"Total tickets processed: {total_tickets}")
    print(f"Total logs inserted: {total_logs}")
    print(f"Failed tickets: {len(failed_tickets)}")
    if failed_tickets:
        print(f"Failed ticket IDs: {', '.join(failed_tickets)}")
    print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest historical error logs for similarity matching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--ticket-id",
        help="Single ticket ID to ingest (e.g., INC6052852)",
    )
    
    parser.add_argument(
        "--date",
        help="Ticket creation date in ISO format (e.g., 2024-01-15T14:30:00Z)",
    )
    
    parser.add_argument(
        "--incident-id",
        help="Optional incident UUID from incidents table",
    )
    
    parser.add_argument(
        "--csv",
        help="CSV file with multiple tickets (columns: ticket_id,created_date,incident_id)",
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.csv:
        ingest_from_csv(args.csv)
    elif args.ticket_id and args.date:
        inserted_count = ingest_single_ticket(
            ticket_id=args.ticket_id,
            created_date=args.date,
            incident_id=args.incident_id,
        )
        print(f"\nIngested {inserted_count} logs for ticket {args.ticket_id}")
    else:
        parser.error("Must provide either --csv OR (--ticket-id AND --date)")


if __name__ == "__main__":
    main()
