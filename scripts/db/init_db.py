"""Initialize the database schema."""

import sys
import os

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from ai_service.core import get_logger, setup_logging
except ImportError:
    import logging

    def setup_logging(log_level="INFO", service_name="init_db_script"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)

# Setup logging
setup_logging(log_level="INFO", service_name="init_db_script")
logger = get_logger(__name__)

from db.connection import get_db_connection


def init_schema():
    """Initialize database schema."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Read and execute schema file
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "db", "schema.sql"
    )
    with open(schema_path, "r") as f:
        schema_sql = f.read()

    # Execute schema
    cur.execute(schema_sql)
    conn.commit()

    logger.info(" Database schema initialized successfully")
    logger.info(" Extensions: vector, uuid-ossp")
    logger.info(" Tables: documents, chunks, incidents, feedback")
    logger.info(" Indexes and view created")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        init_schema()
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        sys.exit(1)
