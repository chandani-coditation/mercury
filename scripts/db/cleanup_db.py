#!/usr/bin/env python3
"""Safe cleanup script for NOC Agent AI data stores.

**IMPORTANT: This script uses Docker PostgreSQL only.**
It connects to the Docker container 'noc-ai-postgres' via docker exec.

Usage examples:
  # Dry run (show what would be deleted)
  python scripts/db/cleanup_db.py --dry-run

  # Wipe everything (requires --yes)
  python scripts/db/cleanup_db.py --yes

  # Selective wipes
  python scripts/db/cleanup_db.py --yes --incidents --feedback
  python scripts/db/cleanup_db.py --yes --documents --chunks --runbook-steps
  python scripts/db/cleanup_db.py --yes --incident-signatures --agent-state
"""
import sys
import os
import argparse
import subprocess
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ai_service.core import get_logger, setup_logging
except ImportError:
    import logging

    def setup_logging(log_level="INFO", service_name="cleanup_script"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)

# Setup logging
setup_logging(log_level="INFO", service_name="cleanup_script")
logger = get_logger(__name__)


ALL_TARGETS = [
    "documents",
    "chunks",
    "incidents",
    "feedback",
    "runbook_steps",
    "incident_signatures",
    "agent_state",
]

# Load .env file from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Get database credentials from .env (for Docker PostgreSQL)
DOCKER_CONTAINER = "noc-ai-postgres"  # Docker container name (fixed)
DB_USER = os.getenv("POSTGRES_USER", "noc_ai")
DB_NAME = os.getenv("POSTGRES_DB", "noc_ai")


def build_statements(targets: List[str]) -> List[str]:
    """Build TRUNCATE statements with CASCADE and sequence resets in safe order."""
    # Order matters due to FKs; use TRUNCATE ... CASCADE, but still order for clarity
    ordered = []
    # Children first typically: chunks -> documents; feedback depends on incidents
    if "chunks" in targets:
        ordered.append("TRUNCATE TABLE chunks RESTART IDENTITY CASCADE;")
    if "runbook_steps" in targets:
        ordered.append("TRUNCATE TABLE runbook_steps RESTART IDENTITY CASCADE;")
    if "incident_signatures" in targets:
        ordered.append("TRUNCATE TABLE incident_signatures RESTART IDENTITY CASCADE;")
    if "documents" in targets:
        ordered.append("TRUNCATE TABLE documents RESTART IDENTITY CASCADE;")
    if "feedback" in targets:
        ordered.append("TRUNCATE TABLE feedback RESTART IDENTITY CASCADE;")
    if "incidents" in targets:
        ordered.append("TRUNCATE TABLE incidents RESTART IDENTITY CASCADE;")
    if "agent_state" in targets:
        ordered.append("TRUNCATE TABLE agent_state RESTART IDENTITY CASCADE;")
    return ordered


def cleanup_db(targets: List[str], dry_run: bool = False) -> None:
    """Clean up database using Docker exec (connects to Docker PostgreSQL only)."""
    # Verify Docker container is running
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={DOCKER_CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        if DOCKER_CONTAINER not in result.stdout:
            raise RuntimeError(
                f"Docker container '{DOCKER_CONTAINER}' is not running. Please start it with 'docker compose up -d'"
            )
    except FileNotFoundError:
        raise RuntimeError("Docker not found. Please ensure Docker is installed and running.")
    except subprocess.CalledProcessError:
        raise RuntimeError(
            f"Failed to check Docker container status. Ensure '{DOCKER_CONTAINER}' is running."
        )

    stmts = build_statements(targets)
    if dry_run:
        logger.info(
            f"\nDRY RUN - The following statements would be executed in Docker PostgreSQL ({DOCKER_CONTAINER}):"
        )
        logger.info(f"  Database: {DB_NAME}, User: {DB_USER}")
        for s in stmts:
            logger.info(f"  {s.strip()}")
        return

    # Use Docker exec to connect to Docker PostgreSQL container
    # This ensures we ONLY use Docker PostgreSQL, never local instance
    docker_cmd = ["docker", "exec", DOCKER_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-c"]

    try:
        for s in stmts:
            logger.info(f"Executing in Docker ({DOCKER_CONTAINER}): {s.strip()}")
            # Execute SQL via docker exec
            result = subprocess.run(docker_cmd + [s], capture_output=True, text=True, check=True)
            if result.stdout:
                logger.info(result.stdout.strip())
        logger.info("\n✅ Cleanup complete.")
    except subprocess.CalledProcessError as e:
        logger.error(f"\n❌ Cleanup failed: {e}")
        if e.stderr:
            logger.error(f"Error: {e.stderr}")
        raise


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
        """,
    )
    parser.add_argument("--yes", action="store_true", help="Confirm destructive action")
    parser.add_argument("--dry-run", action="store_true", help="Show statements without executing")
    parser.add_argument("--documents", action="store_true", help="Wipe documents table")
    parser.add_argument("--chunks", action="store_true", help="Wipe chunks table")
    parser.add_argument("--incidents", action="store_true", help="Wipe incidents table")
    parser.add_argument("--feedback", action="store_true", help="Wipe feedback table")
    parser.add_argument(
        "--runbook-steps",
        dest="runbook_steps",
        action="store_true",
        help="Wipe runbook_steps table",
    )
    parser.add_argument(
        "--incident-signatures",
        dest="incident_signatures",
        action="store_true",
        help="Wipe incident_signatures table",
    )
    parser.add_argument(
        "--agent-state",
        dest="agent_state",
        action="store_true",
        help="Wipe agent_state table",
    )

    args = parser.parse_args()

    selected = [
        t
        for t, flag in (
            ("documents", args.documents),
            ("chunks", args.chunks),
            ("incidents", args.incidents),
            ("feedback", args.feedback),
            ("runbook_steps", args.runbook_steps),
            ("incident_signatures", args.incident_signatures),
            ("agent_state", args.agent_state),
        )
        if flag
    ]

    # Default to ALL if nothing selected
    targets = selected or ALL_TARGETS

    if not args.dry_run and not args.yes:
        logger.warning(" Refusing to proceed without --yes (destructive). Use --dry-run to preview.")
        sys.exit(1)

    logger.info(f"Targets: {', '.join(targets)}")
    cleanup_db(targets, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
