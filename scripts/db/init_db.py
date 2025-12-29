"""Initialize the database schema."""

import sys
import os

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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

    print(" Database schema initialized successfully")
    print(" Extensions: vector, uuid-ossp")
    print(" Tables: documents, chunks, incidents, feedback")
    print(" Indexes and view created")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        init_schema()
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)
