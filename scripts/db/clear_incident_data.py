#!/usr/bin/env python3
"""Clear incident-related data from database before re-ingestion.

This script clears:
- incidents table
- incident_signatures table (to re-ingest with close_notes)
- triage_results table
- resolution_outputs table
- feedback table (optional)

It preserves:
- documents (runbooks)
- runbook_steps
- chunks (for runbooks)
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from db.connection import get_db_connection, get_logger
from ai_service.core import setup_logging

# Setup logging
setup_logging(log_level="INFO", service_name="clear_incident_data")
logger = get_logger(__name__)


def clear_incident_data(clear_feedback: bool = False):
    """Clear incident-related data from database."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        logger.info("Starting to clear incident-related data...")
        
        # Clear in order (respecting foreign key constraints)
        tables_to_clear = [
            ("feedback", "Feedback data"),
            ("resolution_outputs", "Resolution outputs"),
            ("triage_results", "Triage results"),
            ("incidents", "Incidents"),
            ("incident_signatures", "Incident signatures"),
        ]
        
        for table_name, description in tables_to_clear:
            if table_name == "feedback" and not clear_feedback:
                logger.info(f"Skipping {table_name} (use --clear-feedback to include)")
                continue
                
            logger.info(f"Clearing {description}...")
            cur.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            logger.info(f"  ✓ Cleared {table_name}")
        
        conn.commit()
        logger.info("Successfully cleared all incident-related data")
        
        # Verify
        cur.execute("SELECT COUNT(*) as count FROM incidents")
        incident_count = cur.fetchone()
        incident_count = incident_count["count"] if isinstance(incident_count, dict) else incident_count[0]
        
        cur.execute("SELECT COUNT(*) as count FROM incident_signatures")
        sig_count = cur.fetchone()
        sig_count = sig_count["count"] if isinstance(sig_count, dict) else sig_count[0]
        
        logger.info(f"Verification: incidents={incident_count}, incident_signatures={sig_count}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error clearing data: {e}", exc_info=True)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Clear incident-related data from database"
    )
    parser.add_argument(
        "--clear-feedback",
        action="store_true",
        help="Also clear feedback table (default: preserve feedback)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that you want to clear all incident data"
    )
    
    args = parser.parse_args()
    
    if not args.confirm:
        print("WARNING: This will delete all incident data!")
        print("Tables to be cleared:")
        print("  - incidents")
        print("  - incident_signatures")
        print("  - triage_results")
        print("  - resolution_outputs")
        if args.clear_feedback:
            print("  - feedback")
        print("\nRun with --confirm to proceed")
        sys.exit(1)
    
    try:
        clear_incident_data(clear_feedback=args.clear_feedback)
        print("\n✓ Successfully cleared incident data")
        print("You can now re-ingest tickets with: python3 scripts/data/ingest_servicenow_tickets.py --file <csv_file>")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)

