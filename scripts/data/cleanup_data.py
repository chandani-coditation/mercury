#!/usr/bin/env python3
"""Clean up all data from the knowledge base.

This script removes all documents, chunks, incidents, and feedback from the database.

Usage:
  # Dry run (show what would be deleted)
  python scripts/data/cleanup_data.py --dry-run

  # Wipe everything (requires --yes)
  python scripts/data/cleanup_data.py --yes

  # Selective cleanup
  python scripts/data/cleanup_data.py --yes --documents --chunks
  python scripts/data/cleanup_data.py --yes --incidents --feedback
"""
import sys
import os
import argparse
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from ai_service.core import get_logger, setup_logging
except ImportError:
    import logging

    def setup_logging(log_level="INFO", service_name="cleanup_data_script"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)


# Setup logging
setup_logging(log_level="INFO", service_name="cleanup_data_script")
logger = get_logger(__name__)

from db.connection import get_db_connection

ALL_TARGETS = ["documents", "chunks", "incidents", "feedback"]


def build_statements(targets: List[str]) -> List[str]:
    """Build TRUNCATE statements with CASCADE and sequence resets in safe order."""
    # Order matters due to FKs; use TRUNCATE ... CASCADE
    ordered = []
    # Children first: chunks -> documents; feedback depends on incidents
    if "chunks" in targets:
        ordered.append("TRUNCATE TABLE chunks RESTART IDENTITY CASCADE;")
    if "documents" in targets:
        ordered.append("TRUNCATE TABLE documents RESTART IDENTITY CASCADE;")
    if "feedback" in targets:
        ordered.append("TRUNCATE TABLE feedback RESTART IDENTITY CASCADE;")
    if "incidents" in targets:
        ordered.append("TRUNCATE TABLE incidents RESTART IDENTITY CASCADE;")
    return ordered


def cleanup_db(targets: List[str], dry_run: bool = False) -> None:
    """Clean up database tables."""
    stmts = build_statements(targets)

    if dry_run:
        logger.info("\n DRY RUN - The following statements would be executed:")
        for s in stmts:
            logger.info(f"  {s.strip()}")
        logger.info(f"\n  This would delete all data from: {', '.join(targets)}")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        for s in stmts:
            logger.info(f"Executing: {s.strip()}")
            cur.execute(s)
        conn.commit()
        logger.info(f"\n Cleanup complete. Deleted all data from: {', '.join(targets)}")
    except Exception as e:
        conn.rollback()
        logger.error(f"\n Cleanup failed: {type(e).__name__}: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Clean up NOC Agent AI database (truncate tables, reset sequences)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  # Dry run (no changes)
  python scripts/data/cleanup_data.py --dry-run

  # Wipe everything (requires confirmation)
  python scripts/data/cleanup_data.py --yes

  # Selective cleanup
  python scripts/data/cleanup_data.py --yes --incidents --feedback
  python scripts/data/cleanup_data.py --yes --documents --chunks
        """,
    )
    parser.add_argument("--yes", action="store_true", help="Confirm destructive action")
    parser.add_argument("--dry-run", action="store_true", help="Show statements without executing")
    parser.add_argument("--documents", action="store_true", help="Wipe documents table")
    parser.add_argument("--chunks", action="store_true", help="Wipe chunks table")
    parser.add_argument("--incidents", action="store_true", help="Wipe incidents table")
    parser.add_argument("--feedback", action="store_true", help="Wipe feedback table")

    args = parser.parse_args()

    selected = [
        t
        for t, flag in (
            ("documents", args.documents),
            ("chunks", args.chunks),
            ("incidents", args.incidents),
            ("feedback", args.feedback),
        )
        if flag
    ]

    # Default to ALL if nothing selected
    targets = selected or ALL_TARGETS

    if not args.dry_run and not args.yes:
        logger.warning(
            " Refusing to proceed without --yes (destructive). Use --dry-run to preview."
        )
        sys.exit(1)

    logger.info(f"Targets: {', '.join(targets)}")
    cleanup_db(targets, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
