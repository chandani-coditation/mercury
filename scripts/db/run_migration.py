#!/usr/bin/env python3
"""Run database migrations."""

import sys
import os

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

try:
    from ai_service.core import get_logger, setup_logging
except ImportError:
    import logging

    def setup_logging(log_level="INFO", service_name="migration_script"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)


# Setup logging
setup_logging(log_level="INFO", service_name="migration_script")
logger = get_logger(__name__)

from db.connection import get_db_connection


def run_migration(migration_file):
    """Run a SQL migration file."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        with open(migration_file, "r") as f:
            migration_sql = f.read()

        logger.info(f"Running migration: {migration_file}")
        cur.execute(migration_sql)
        conn.commit()
        logger.info(" Migration completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f" Migration failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    migration_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "db",
        "migrations",
    )

    # Check for combined migration file first
    combined_migration = os.path.join(
        migration_dir, "000_combined_migration.sql"
    )

    if os.path.exists(combined_migration):
        logger.info(
            "Found combined migration file - using it instead of individual migrations"
        )
        run_migration(combined_migration)
        logger.info("\n Combined migration completed")
    else:
        # Run all migrations in order (excluding combined if it exists)
        migrations = sorted(
            [
                f
                for f in os.listdir(migration_dir)
                if f.endswith(".sql") and f != "000_combined_migration.sql"
            ]
        )

        if not migrations:
            logger.warning("No migrations found")
            sys.exit(0)

        logger.info(f"Found {len(migrations)} migration(s)")

        for migration in migrations:
            migration_path = os.path.join(migration_dir, migration)
            run_migration(migration_path)

        logger.info("\n All migrations completed")
