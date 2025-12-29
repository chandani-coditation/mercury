#!/usr/bin/env python3
"""Reset database and ingest fresh data (runbooks + tickets).

This script:
1. Clears all data from the database (documents, chunks, incidents, feedback)
2. Ingests runbooks from the runbooks/ directory
3. Ingests tickets data from specified CSV files

Usage:
    python scripts/data/reset_and_ingest.py
    python scripts/data/reset_and_ingest.py --skip-cleanup
    python scripts/data/reset_and_ingest.py --runbooks-dir runbooks --tickets-dir tickets_data
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ai_service.core import get_logger, setup_logging

# Setup logging
setup_logging(log_level="INFO", service_name="reset_and_ingest")
logger = get_logger(__name__)

# Default paths
DEFAULT_RUNBOOKS_DIR = project_root / "runbooks"
DEFAULT_TICKETS_DIR = project_root / "tickets_data"
DEFAULT_INGESTION_URL = "http://localhost:8002"

# CSV files to ingest (with comments/resolution data)
TICKET_FILES = [
    "database_alerts_comments.csv",
    "high_disk_alert_comment.csv",
]


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    logger.info(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,
            text=True,
        )
        print(f"\n✓ {description} completed successfully")
        logger.info(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ {description} failed with exit code {e.returncode}")
        logger.error(f"✗ {description} failed with exit code {e.returncode}")
        return False
    except Exception as e:
        print(f"\n✗ {description} failed: {str(e)}")
        logger.error(f"✗ {description} failed: {str(e)}")
        return False


def cleanup_database() -> bool:
    """Clear all data from the database."""
    script_path = project_root / "scripts" / "db" / "cleanup_db.py"
    cmd = [sys.executable, str(script_path), "--yes"]
    return run_command(cmd, "Cleaning up database (documents, chunks, incidents, feedback)")


def ingest_runbooks(runbooks_dir: Path, ingestion_url: str) -> bool:
    """Ingest runbooks from directory."""
    script_path = project_root / "scripts" / "data" / "ingest_runbooks.py"
    
    if not runbooks_dir.exists():
        print(f"\n✗ Runbooks directory not found: {runbooks_dir}")
        logger.error(f"Runbooks directory not found: {runbooks_dir}")
        return False
    
    docx_files = list(runbooks_dir.glob("*.docx"))
    if not docx_files:
        print(f"\n⚠ No DOCX files found in {runbooks_dir}")
        logger.warning(f"No DOCX files found in {runbooks_dir}")
        return False
    
    cmd = [
        sys.executable,
        str(script_path),
        "--dir",
        str(runbooks_dir),
        "--ingestion-url",
        ingestion_url,
    ]
    return run_command(cmd, f"Ingesting runbooks from {runbooks_dir}")


def ingest_tickets(tickets_dir: Path, ingestion_url: str) -> bool:
    """Ingest tickets from specified CSV files."""
    script_path = project_root / "scripts" / "data" / "ingest_servicenow_tickets.py"
    
    if not tickets_dir.exists():
        print(f"\n✗ Tickets directory not found: {tickets_dir}")
        logger.error(f"Tickets directory not found: {tickets_dir}")
        return False
    
    success = True
    for csv_file in TICKET_FILES:
        file_path = tickets_dir / csv_file
        if not file_path.exists():
            print(f"\n⚠ CSV file not found: {file_path}")
            logger.warning(f"CSV file not found: {file_path}")
            continue
        
        cmd = [
            sys.executable,
            str(script_path),
            "--file",
            str(file_path),
            "--ingestion-url",
            ingestion_url,
        ]
        if not run_command(cmd, f"Ingesting tickets from {csv_file}"):
            success = False
    
    return success


def verify_database() -> bool:
    """Verify database state after ingestion."""
    script_path = project_root / "scripts" / "db" / "verify_db.py"
    return run_command([sys.executable, str(script_path)], "Verifying database state")


def main():
    parser = argparse.ArgumentParser(
        description="Reset database and ingest fresh data (runbooks + tickets)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip database cleanup step (useful for re-ingesting without clearing)",
    )
    parser.add_argument(
        "--runbooks-dir",
        type=str,
        default=str(DEFAULT_RUNBOOKS_DIR),
        help=f"Directory containing runbook DOCX files (default: {DEFAULT_RUNBOOKS_DIR})",
    )
    parser.add_argument(
        "--tickets-dir",
        type=str,
        default=str(DEFAULT_TICKETS_DIR),
        help=f"Directory containing ticket CSV files (default: {DEFAULT_TICKETS_DIR})",
    )
    parser.add_argument(
        "--ingestion-url",
        type=str,
        default=DEFAULT_INGESTION_URL,
        help=f"Ingestion service URL (default: {DEFAULT_INGESTION_URL})",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip database verification step",
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("Database Reset and Data Ingestion Script")
    print("=" * 70)
    logger.info("Starting database reset and data ingestion...")

    steps_completed = []
    steps_failed = []

    # Step 1: Cleanup database
    if not args.skip_cleanup:
        if cleanup_database():
            steps_completed.append("Database cleanup")
        else:
            steps_failed.append("Database cleanup")
            print("\n⚠ Continuing despite cleanup failure...")
    else:
        print("\n⏭ Skipping database cleanup (--skip-cleanup)")
        steps_completed.append("Database cleanup (skipped)")

    # Step 2: Ingest runbooks
    runbooks_dir = Path(args.runbooks_dir)
    if ingest_runbooks(runbooks_dir, args.ingestion_url):
        steps_completed.append("Runbooks ingestion")
    else:
        steps_failed.append("Runbooks ingestion")

    # Step 3: Ingest tickets
    tickets_dir = Path(args.tickets_dir)
    if ingest_tickets(tickets_dir, args.ingestion_url):
        steps_completed.append("Tickets ingestion")
    else:
        steps_failed.append("Tickets ingestion")

    # Step 4: Verify database
    if not args.skip_verify:
        if verify_database():
            steps_completed.append("Database verification")
        else:
            steps_failed.append("Database verification")
    else:
        print("\n⏭ Skipping database verification (--skip-verify)")

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"\n✓ Completed steps ({len(steps_completed)}):")
    for step in steps_completed:
        print(f"  - {step}")

    if steps_failed:
        print(f"\n✗ Failed steps ({len(steps_failed)}):")
        for step in steps_failed:
            print(f"  - {step}")
        print("\n⚠ Some steps failed. Please review the output above.")
        sys.exit(1)
    else:
        print("\n✓ All steps completed successfully!")
        print("\nNext steps:")
        print("  1. Run agent validation: python scripts/data/validate_agents.py")
        print("  2. Test agents with filtered test data")
        logger.info("All steps completed successfully")


if __name__ == "__main__":
    main()

