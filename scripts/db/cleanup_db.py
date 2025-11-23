#!/usr/bin/env python3
"""Safe cleanup script for NOC Agent AI data stores.

Usage examples:
  # Dry run (show what would be deleted)
  python scripts/db/cleanup_db.py --dry-run

  # Wipe everything (requires --yes)
  python scripts/db/cleanup_db.py --yes

  # Selective wipes
  python scripts/db/cleanup_db.py --yes --incidents --feedback
  python scripts/db/cleanup_db.py --yes --documents --chunks
"""
import sys
import os
import argparse
from typing import List

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.connection import get_db_connection  # noqa: E402


ALL_TARGETS = ["documents", "chunks", "incidents", "feedback"]


def build_statements(targets: List[str]) -> List[str]:
    """Build TRUNCATE statements with CASCADE and sequence resets in safe order."""
    # Order matters due to FKs; use TRUNCATE ... CASCADE, but still order for clarity
    ordered = []
    # Children first typically: chunks -> documents; feedback depends on incidents
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
    stmts = build_statements(targets)
    if dry_run:
        print("\nDRY RUN - The following statements would be executed:")
        for s in stmts:
            print(f"  {s.strip()}")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        for s in stmts:
            print(f"Executing: {s.strip()}")
            cur.execute(s)
        conn.commit()
        print("\n✅ Cleanup complete.")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Cleanup failed: {type(e).__name__}: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Safely cleanup NOC Agent AI Postgres data (truncate tables, reset sequences)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  # Dry run (no changes)
  python scripts/db/cleanup_db.py --dry-run

  # Wipe everything (requires confirmation)
  python scripts/db/cleanup_db.py --yes

  # Selective wipes
  python scripts/db/cleanup_db.py --yes --incidents --feedback
  python scripts/db/cleanup_db.py --yes --documents --chunks
        """
    )
    parser.add_argument("--yes", action="store_true", help="Confirm destructive action")
    parser.add_argument("--dry-run", action="store_true", help="Show statements without executing")
    parser.add_argument("--documents", action="store_true", help="Wipe documents table")
    parser.add_argument("--chunks", action="store_true", help="Wipe chunks table")
    parser.add_argument("--incidents", action="store_true", help="Wipe incidents table")
    parser.add_argument("--feedback", action="store_true", help="Wipe feedback table")

    args = parser.parse_args()

    selected = [t for t, flag in (
        ("documents", args.documents),
        ("chunks", args.chunks),
        ("incidents", args.incidents),
        ("feedback", args.feedback),
    ) if flag]

    # Default to ALL if nothing selected
    targets = selected or ALL_TARGETS

    if not args.dry_run and not args.yes:
        print("❌ Refusing to proceed without --yes (destructive). Use --dry-run to preview.")
        sys.exit(1)

    print(f"Targets: {', '.join(targets)}")
    cleanup_db(targets, dry_run=args.dry_run)


if __name__ == "__main__":
    main()


