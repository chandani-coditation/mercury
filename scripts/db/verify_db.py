#!/usr/bin/env python3
"""Verify database setup and embeddings.

Usage:
    python scripts/db/verify_db.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from db.connection import get_db_connection


def verify_db():
    """Verify database setup, documents, chunks, and embeddings."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        print("=" * 70)
        print(" Database Verification Report")
        print("=" * 70)

        # 1. Check documents count
        print("\n Documents:")
        cur.execute("SELECT COUNT(*) as total FROM documents;")
        total_docs = cur.fetchone()["total"]
        print(f"  Total documents: {total_docs}")

        # Documents by type
        cur.execute(
            """
            SELECT doc_type, COUNT(*) as count 
            FROM documents 
            GROUP BY doc_type 
            ORDER BY doc_type;
        """
        )
        print("\n  Documents by type:")
        for row in cur.fetchall():
            print(f"    {row['doc_type']}: {row['count']}")

        # 2. Check chunks count
        print("\n Chunks:")
        cur.execute("SELECT COUNT(*) as total FROM chunks;")
        total_chunks = cur.fetchone()["total"]
        print(f"  Total chunks: {total_chunks}")

        # Chunks with embeddings
        cur.execute(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(embedding) as with_embedding,
                COUNT(*) - COUNT(embedding) as missing_embedding
            FROM chunks;
        """
        )
        chunk_stats = cur.fetchone()
        print(f"  Chunks with embeddings: {chunk_stats['with_embedding']}/{chunk_stats['total']}")
        if chunk_stats["missing_embedding"] > 0:
            print(f"    WARNING: {chunk_stats['missing_embedding']} chunks missing embeddings!")

        # Chunks with tsvector
        cur.execute(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(tsv) as with_tsv,
                COUNT(*) - COUNT(tsv) as missing_tsv
            FROM chunks;
        """
        )
        tsv_stats = cur.fetchone()
        print(f"  Chunks with tsvector: {tsv_stats['with_tsv']}/{tsv_stats['total']}")
        if tsv_stats["missing_tsv"] > 0:
            print(f"    WARNING: {tsv_stats['missing_tsv']} chunks missing tsvector!")

        # 3. Check embedding dimensions (pgvector stores as vector type)
        print("\n Embedding Details:")
        # Check if we can query vector dimensions using pgvector functions
        # For text-embedding-3-small, expected dimension is 1536
        cur.execute(
            """
            SELECT 
                COUNT(*) as total_with_embeddings
            FROM chunks 
            WHERE embedding IS NOT NULL;
        """
        )
        total_with_emb = cur.fetchone()["total_with_embeddings"]
        print(f"  Total chunks with embeddings: {total_with_emb}")
        print("  Expected dimension: 1536 (text-embedding-3-small)")

        # Try to get a sample embedding to verify format
        cur.execute(
            """
            SELECT embedding::text as embedding_text
            FROM chunks 
            WHERE embedding IS NOT NULL
            LIMIT 1;
        """
        )
        sample = cur.fetchone()
        if sample and sample["embedding_text"]:
            # Count dimensions by counting commas + 1
            dims = sample["embedding_text"].count(",") + 1
            print(f"  Sample embedding dimensions: {dims}")
            if dims == 1536:
                print("   Embedding dimensions match expected (1536)")
            else:
                print(f"    Unexpected dimensions: {dims} (expected 1536)")

        # 4. Check chunks per document
        print("\n Chunks per Document:")
        cur.execute(
            """
            SELECT 
                d.doc_type,
                AVG(chunk_count) as avg_chunks,
                MIN(chunk_count) as min_chunks,
                MAX(chunk_count) as max_chunks
            FROM documents d
            LEFT JOIN (
                SELECT document_id, COUNT(*) as chunk_count
                FROM chunks
                GROUP BY document_id
            ) c ON d.id = c.document_id
            GROUP BY d.doc_type
            ORDER BY d.doc_type;
        """
        )
        print("  Average chunks per document by type:")
        for row in cur.fetchall():
            avg = row["avg_chunks"] or 0
            min_c = row["min_chunks"] or 0
            max_c = row["max_chunks"] or 0
            print(f"    {row['doc_type']}: avg={avg:.1f}, min={min_c}, max={max_c}")

        # 5. Sample embeddings validation
        print("\n Sample Embedding Validation:")
        cur.execute(
            """
            SELECT 
                c.id,
                c.content,
                c.embedding::text as embedding_text,
                d.doc_type,
                d.title
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            LIMIT 3;
        """
        )
        samples = cur.fetchall()
        if samples:
            for i, sample in enumerate(samples, 1):
                # Check if embedding is a valid vector
                embedding_str = sample["embedding_text"] or ""
                # pgvector format: [1,2,3,...]
                if embedding_str.startswith("[") and embedding_str.endswith("]"):
                    dims = embedding_str.count(",") + 1
                    title_preview = (sample["title"] or "N/A")[:50]
                    print(f"  Sample {i}: {sample['doc_type']} - '{title_preview}...'")
                    print(f"     Valid vector: {dims} dimensions")
                    print(f"     Content length: {len(sample['content'])} chars")
                else:
                    print(f"  Sample {i}:   Invalid embedding format!")
        else:
            print("    No embeddings found to validate!")

        # 6. Check for documents without chunks
        print("\n🔗 Document-Chunk Relationships:")
        cur.execute(
            """
            SELECT COUNT(*) as orphaned
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            WHERE c.id IS NULL;
        """
        )
        orphaned = cur.fetchone()["orphaned"]
        if orphaned > 0:
            print(f"    WARNING: {orphaned} documents have no chunks!")
        else:
            print("   All documents have chunks")

        # 7. Check indexes
        print("\n📇 Indexes:")
        cur.execute(
            """
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename IN ('chunks', 'documents')
            ORDER BY tablename, indexname;
        """
        )
        indexes = cur.fetchall()
        print(f"  Found {len(indexes)} indexes:")
        for idx in indexes:
            idx_type = (
                "GIN"
                if "GIN" in idx["indexdef"]
                else "ivfflat" if "ivfflat" in idx["indexdef"] else "B-tree"
            )
            print(f"    {idx['indexname']} ({idx_type})")

        # 8. Summary
        print("\n" + "=" * 70)
        print(" Summary:")
        print("=" * 70)

        all_good = True
        if total_docs == 0:
            print("    No documents found!")
            all_good = False
        else:
            print(f"   {total_docs} documents ingested")

        if total_chunks == 0:
            print("    No chunks found!")
            all_good = False
        else:
            print(f"   {total_chunks} chunks created")

        if chunk_stats["missing_embedding"] > 0:
            print(f"    {chunk_stats['missing_embedding']} chunks missing embeddings")
            all_good = False
        else:
            print(f"   All {total_chunks} chunks have embeddings")

        if tsv_stats["missing_tsv"] > 0:
            print(f"    {tsv_stats['missing_tsv']} chunks missing tsvector")
            all_good = False
        else:
            print(f"   All {total_chunks} chunks have tsvector")

        if orphaned > 0:
            print(f"    {orphaned} documents without chunks")
            all_good = False

        if all_good:
            print("\n   Database is correctly set up and all embeddings generated!")
        else:
            print("\n    Some issues detected. Please review above.")

        print("=" * 70)

    except Exception as e:
        print(f"\n Error during verification: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    verify_db()
