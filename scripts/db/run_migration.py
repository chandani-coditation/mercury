#!/usr/bin/env python3
"""Run database migrations."""
import sys
import os

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.connection import get_db_connection

def run_migration(migration_file):
    """Run a SQL migration file."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print(f"Running migration: {migration_file}")
        cur.execute(migration_sql)
        conn.commit()
        print("✓ Migration completed successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    migration_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "db", "migrations")
    
    # Run all migrations in order
    migrations = sorted([f for f in os.listdir(migration_dir) if f.endswith('.sql')])
    
    if not migrations:
        print("No migrations found")
        sys.exit(0)
    
    print(f"Found {len(migrations)} migration(s)")
    
    for migration in migrations:
        migration_path = os.path.join(migration_dir, migration)
        run_migration(migration_path)
    
    print("\n✓ All migrations completed")

