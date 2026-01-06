#!/usr/bin/env python3
"""Verify database setup and embeddings.

**IMPORTANT: This script uses Docker PostgreSQL only.**
It connects to the Docker container 'noc-ai-postgres' via docker exec.

Usage:
    python scripts/db/verify_db.py
"""
import sys
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Get database credentials from .env (for Docker PostgreSQL)
DOCKER_CONTAINER = "noc-ai-postgres"  # Docker container name (fixed)
DB_USER = os.getenv("POSTGRES_USER", "noc_ai")
DB_NAME = os.getenv("POSTGRES_DB", "noc_ai")


def check_docker_container():
    """Verify Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={DOCKER_CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        if DOCKER_CONTAINER not in result.stdout:
            raise RuntimeError(f"Docker container '{DOCKER_CONTAINER}' is not running. Please start it with 'docker compose up -d'")
    except FileNotFoundError:
        raise RuntimeError("Docker not found. Please ensure Docker is installed and running.")
    except subprocess.CalledProcessError:
        raise RuntimeError(f"Failed to check Docker container status. Ensure '{DOCKER_CONTAINER}' is running.")


def execute_sql(query: str) -> list:
    """Execute SQL query via Docker exec and return results (Docker PostgreSQL only)."""
    check_docker_container()
    
    docker_cmd = [
        "docker", "exec", DOCKER_CONTAINER,
        "psql", "-U", DB_USER, "-d", DB_NAME,
        "-t", "-A", "-F", "|"  # Tab-separated output
    ]
    
    try:
        result = subprocess.run(
            docker_cmd,
            input=query,
            capture_output=True,
            text=True,
            check=True
        )
        # Parse tab-separated output
        lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        return lines
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Database query failed: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("Docker not found. Please ensure Docker is installed and the 'noc-ai-postgres' container is running.")


def execute_sql_single(query: str) -> str:
    """Execute SQL query via Docker exec and return single value (Docker PostgreSQL only)."""
    check_docker_container()
    
    docker_cmd = [
        "docker", "exec", DOCKER_CONTAINER,
        "psql", "-U", DB_USER, "-d", DB_NAME,
        "-t", "-A", "-c", query
    ]
    
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Database query failed: {e.stderr}")


def parse_result_line(line: str, fields: list) -> dict:
    """Parse a pipe-separated result line into a dict."""
    values = line.split("|")
    return {fields[i]: values[i].strip() if i < len(values) else None for i in range(len(fields))}


def verify_db():
    """Verify database setup, documents, chunks, and embeddings using Docker PostgreSQL."""
    try:
        print("=" * 70)
        print(" Database Verification Report")
        print(f" (Using Docker container: {DOCKER_CONTAINER})")
        print("=" * 70)

        # 1. Check documents count
        print("\n📄 Documents:")
        total_docs = int(execute_sql_single("SELECT COUNT(*) FROM documents;"))
        print(f"  Total documents: {total_docs}")

        # Documents by type
        doc_types = execute_sql("SELECT doc_type, COUNT(*) as count FROM documents GROUP BY doc_type ORDER BY doc_type;")
        print("\n  Documents by type:")
        for line in doc_types:
            parts = line.split("|")
            if len(parts) >= 2:
                print(f"    {parts[0]}: {parts[1]}")

        # 2. Check chunks count
        print("\n📦 Chunks:")
        total_chunks = int(execute_sql_single("SELECT COUNT(*) FROM chunks;"))
        print(f"  Total chunks: {total_chunks}")

        # Chunks with embeddings
        chunk_stats_line = execute_sql_single("""
            SELECT 
                COUNT(*)::text || '|' || 
                COUNT(embedding)::text || '|' || 
                (COUNT(*) - COUNT(embedding))::text
            FROM chunks;
        """)
        parts = chunk_stats_line.split("|")
        total = int(parts[0]) if parts[0] else 0
        with_embedding = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        missing_embedding = int(parts[2]) if len(parts) > 2 and parts[2] else 0
        
        print(f"  Chunks with embeddings: {with_embedding}/{total}")
        if missing_embedding > 0:
            print(f"    ⚠️  WARNING: {missing_embedding} chunks missing embeddings!")

        # Chunks with tsvector
        tsv_stats_line = execute_sql_single("""
            SELECT 
                COUNT(*)::text || '|' || 
                COUNT(tsv)::text || '|' || 
                (COUNT(*) - COUNT(tsv))::text
            FROM chunks;
        """)
        parts = tsv_stats_line.split("|")
        with_tsv = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        missing_tsv = int(parts[2]) if len(parts) > 2 and parts[2] else 0
        
        print(f"  Chunks with tsvector: {with_tsv}/{total}")
        if missing_tsv > 0:
            print(f"    ⚠️  WARNING: {missing_tsv} chunks missing tsvector!")

        # 3. Check embedding dimensions
        print("\n🔢 Embedding Details:")
        total_with_emb = int(execute_sql_single("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;"))
        print(f"  Total chunks with embeddings: {total_with_emb}")
        print("  Expected dimension: 1536 (text-embedding-3-small)")

        # 4. Check chunks per document
        print("\n📊 Chunks per Document:")
        chunk_per_doc = execute_sql("""
            SELECT 
                d.doc_type,
                COALESCE(AVG(chunk_count), 0)::text as avg_chunks,
                COALESCE(MIN(chunk_count), 0)::text as min_chunks,
                COALESCE(MAX(chunk_count), 0)::text as max_chunks
            FROM documents d
            LEFT JOIN (
                SELECT document_id, COUNT(*) as chunk_count
                FROM chunks
                GROUP BY document_id
            ) c ON d.id = c.document_id
            GROUP BY d.doc_type
            ORDER BY d.doc_type;
        """)
        print("  Average chunks per document by type:")
        for line in chunk_per_doc:
            parts = line.split("|")
            if len(parts) >= 4:
                print(f"    {parts[0]}: avg={float(parts[1]):.1f}, min={parts[2]}, max={parts[3]}")

        # 5. Check for documents without chunks
        print("\n🔗 Document-Chunk Relationships:")
        orphaned = int(execute_sql_single("""
            SELECT COUNT(*) 
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE c.id IS NULL;
        """))
        if orphaned > 0:
            print(f"    ⚠️  WARNING: {orphaned} documents have no chunks!")
        else:
            print("   ✅ All documents have chunks")

        # 6. Ingestion Quality Checks
        print("\n📊 Ingestion Quality Checks:")
        
        # Service normalization check (check incident_signatures table, not documents)
        services = execute_sql("""
            SELECT service, COUNT(*)::text as count 
            FROM incident_signatures 
            GROUP BY service 
            ORDER BY count DESC;
        """)
        server_incidents = 0
        total_incidents = 0
        print("  Service distribution (from incident_signatures):")
        for line in services:
            parts = line.split("|")
            if len(parts) >= 2:
                service = parts[0]
                count = int(parts[1])
                total_incidents += count
                print(f"    - {service}: {count} incidents")
                if service == 'Server':
                    server_incidents = count
        
        if server_incidents > 0:
            print(f"  ⚠️  Found {server_incidents} incidents with 'Server' service (should be normalized)")
        else:
            print("  ✅ Service normalization working (no 'Server' incidents)")
        
        if total_incidents > 0:
            print(f"  ✅ Total incident signatures: {total_incidents}")
        
        # Runbook deduplication check
        duplicates = execute_sql("""
            SELECT title, COUNT(*)::text as count 
            FROM documents 
            WHERE doc_type = 'runbook' 
            GROUP BY title 
            HAVING COUNT(*) > 1
            ORDER BY count DESC;
        """)
        if duplicates:
            print(f"  ⚠️  Found duplicate runbooks:")
            for line in duplicates:
                parts = line.split("|")
                if len(parts) >= 2:
                    print(f"     - '{parts[0]}': {parts[1]} duplicates")
        else:
            print("  ✅ Runbook deduplication working (no duplicates)")
        
        # Runbook steps check
        total_steps = int(execute_sql_single("SELECT COUNT(*) FROM runbook_steps;"))
        if total_steps == 0:
            print(f"  ⚠️  No runbook steps found in database")
        else:
            print(f"  ✅ Found {total_steps} runbook steps")
            runbooks_without_steps = execute_sql("""
                SELECT d.title, COUNT(rs.id)::text as step_count 
                FROM documents d 
                LEFT JOIN runbook_steps rs ON d.id = rs.runbook_document_id 
                WHERE d.doc_type = 'runbook' 
                GROUP BY d.id, d.title 
                HAVING COUNT(rs.id) = 0
                LIMIT 5;
            """)
            if runbooks_without_steps:
                print(f"     ⚠️  {len(runbooks_without_steps)} runbooks have no steps")

        # 7. Summary
        print("\n" + "=" * 70)
        print(" Summary:")
        print("=" * 70)

        all_good = True
        if total_docs == 0:
            print("    ⚠️  No documents found!")
            all_good = False
        else:
            print(f"   ✅ {total_docs} documents ingested")

        if total_chunks == 0:
            print("    ⚠️  No chunks found!")
            all_good = False
        else:
            print(f"   ✅ {total_chunks} chunks created")

        if missing_embedding > 0:
            print(f"    ⚠️  {missing_embedding} chunks missing embeddings")
            all_good = False
        else:
            print(f"   ✅ All {total_chunks} chunks have embeddings")

        if missing_tsv > 0:
            print(f"    ⚠️  {missing_tsv} chunks missing tsvector")
            all_good = False
        else:
            print(f"   ✅ All {total_chunks} chunks have tsvector")

        if orphaned > 0:
            print(f"    ⚠️  {orphaned} documents without chunks")
            all_good = False

        if server_incidents > 0 or duplicates or total_steps == 0:
            all_good = False

        if all_good:
            print("\n   ✅ Database is correctly set up and all embeddings generated!")
        else:
            print("\n    ⚠️  Some issues detected. Please review above.")

        print("=" * 70)

    except RuntimeError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during verification: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    verify_db()
