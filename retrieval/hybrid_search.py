"""Hybrid search combining vector similarity and full-text search."""
import os
import time
from typing import List, Dict, Optional
from db.connection import get_db_connection
from ingestion.embeddings import embed_text

# Import logging (use ai_service logger if available, fallback to standard logging)
try:
    from ai_service.core import get_logger
except ImportError:
    import logging
    def get_logger(name):
        return logging.getLogger(name)

logger = get_logger(__name__)


def hybrid_search(
    query_text: str,
    service: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 5,
    vector_weight: float = 0.7,
    fulltext_weight: float = 0.3
) -> List[Dict]:
    """
    Perform hybrid search using RRF (Reciprocal Rank Fusion).
    
    Args:
        query_text: Search query
        service: Optional service filter
        component: Optional component filter
        limit: Number of results to return
        vector_weight: Weight for vector search (0-1)
        fulltext_weight: Weight for full-text search (0-1)
    
    Returns:
        List of chunks with scores
    """
    start_time = time.time()
    logger.debug(
        f"Starting hybrid search: query='{query_text[:100]}...', "
        f"service={service}, component={component}, limit={limit}"
    )
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Generate query embedding
        query_embedding = embed_text(query_text)
        # Convert to pgvector string format
        query_embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # Normalize service and component (ensure None or non-empty strings)
        service_val = service if service and str(service).strip() else None
        component_val = component if component and str(component).strip() else None
        
        # Build filter conditions with case-insensitive partial matching
        # This allows matching "database" with "Database-SQL", "Database", etc.
        filters = []
        filter_params = []
        
        if service_val:
            # Case-insensitive partial match: "database" matches "Database-SQL", "Database", etc.
            filters.append("LOWER(c.metadata->>'service') LIKE LOWER(%s)")
            filter_params.append(f"%{service_val}%")
        
        if component_val:
            # Case-insensitive partial match: "sql-server" matches "sql-server", "SQL Server", etc.
            filters.append("LOWER(c.metadata->>'component') LIKE LOWER(%s)")
            filter_params.append(f"%{component_val}%")
        
        filter_clause = " AND " + " AND ".join(filters) if filters else ""
        
        # Hybrid search query using RRF
        # Vector search: cosine similarity
        # Full-text search: ts_rank
        # RRF: 1/(k + rank) for each result set, then combine
        
        query = f"""
        WITH vector_results AS (
            SELECT 
                c.id,
                c.document_id,
                c.chunk_index,
                c.content,
                c.metadata,
                d.title as doc_title,
                d.doc_type as doc_type,
                1 - (c.embedding <=> %s::vector) as vector_score,
                ROW_NUMBER() OVER (ORDER BY c.embedding <=> %s::vector) as vector_rank
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            {filter_clause}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        ),
        fulltext_results AS (
            SELECT 
                c.id,
                c.document_id,
                c.chunk_index,
                c.content,
                c.metadata,
                d.title as doc_title,
                d.doc_type as doc_type,
                ts_rank(c.tsv, plainto_tsquery('english', %s)) as fulltext_score,
                ROW_NUMBER() OVER (ORDER BY ts_rank(c.tsv, plainto_tsquery('english', %s)) DESC) as fulltext_rank
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.tsv @@ plainto_tsquery('english', %s)
            {filter_clause}
            ORDER BY ts_rank(c.tsv, plainto_tsquery('english', %s)) DESC
            LIMIT %s
        ),
        combined_results AS (
            SELECT 
                COALESCE(v.id, f.id) as id,
                COALESCE(v.document_id, f.document_id) as document_id,
                COALESCE(v.chunk_index, f.chunk_index) as chunk_index,
                COALESCE(v.content, f.content) as content,
                COALESCE(v.metadata, f.metadata) as metadata,
                COALESCE(v.doc_title, f.doc_title) as doc_title,
                COALESCE(v.doc_type, f.doc_type) as doc_type,
                COALESCE(v.vector_score, 0.0) as vector_score,
                COALESCE(f.fulltext_score, 0.0) as fulltext_score,
                COALESCE(v.vector_rank, 999) as vector_rank,
                COALESCE(f.fulltext_rank, 999) as fulltext_rank,
                -- RRF: 1/(k + rank) where k=60 is standard
                (1.0 / (60.0 + COALESCE(v.vector_rank, 999))) * {vector_weight} +
                (1.0 / (60.0 + COALESCE(f.fulltext_rank, 999))) * {fulltext_weight} as rrf_score
            FROM vector_results v
            FULL OUTER JOIN fulltext_results f ON v.id = f.id
        )
        SELECT 
            id,
            document_id,
            chunk_index,
            content,
            metadata,
            doc_title,
            doc_type,
            vector_score,
            fulltext_score,
            rrf_score
        FROM combined_results
        WHERE rrf_score > 0
        ORDER BY rrf_score DESC
        LIMIT %s
        """
        
        # Build params list matching the query placeholders in order
        # Query placeholders in order (when no filters):
        # 1: embedding (vector_score)
        # 2: embedding (vector_rank)  
        # 3: embedding (ORDER BY)
        # 4: limit (vector_results)
        # 5: text (fulltext_score)
        # 6: text (fulltext_rank)
        # 7: text (WHERE)
        # 8: text (ORDER BY)
        # 9: limit (fulltext_results)
        # 10: final limit
        exec_params = []
        
        # Vector results params
        exec_params.append(query_embedding_str)  # 1: vector_score embedding
        exec_params.append(query_embedding_str)  # 2: vector_rank embedding
        # Filters for vector_results (if any) - these come BEFORE ORDER BY
        # Use filter_params which already have the LIKE patterns
        for param in filter_params:
            exec_params.append(param)
        exec_params.append(query_embedding_str)  # 3: ORDER BY embedding
        exec_params.append(limit * 2)  # 4: vector_results limit
        
        # Fulltext results params
        exec_params.append(query_text)  # 5: fulltext_score text
        exec_params.append(query_text)  # 6: fulltext_rank text
        exec_params.append(query_text)  # 7: WHERE text
        # Filters for fulltext_results (if any) - these come BEFORE ORDER BY
        # Use same filter_params again (each filter appears twice in query)
        for param in filter_params:
            exec_params.append(param)
        exec_params.append(query_text)  # 8: ORDER BY text
        exec_params.append(limit * 2)  # 9: fulltext_results limit
        
        # Final
        exec_params.append(limit)  # 10: final limit
        
        # CRITICAL: Verify we have exactly the right number of parameters
        # Base: 10 params (no filters)
        # Each filter adds 2 params (one in vector_results, one in fulltext_results)
        expected_params = 10 + (2 * len(filter_params))
        
        if len(exec_params) != expected_params:
            raise ValueError(
                f"Parameter count mismatch: expected {expected_params} params "
                f"but built {len(exec_params)} params. "
                f"Service: {repr(service_val)}, Component: {repr(component_val)}"
            )
        
        # Debug: verify parameter count and log BEFORE execute
        placeholder_count = query.count('%s')
        param_count = len(exec_params)
        
        # Log using standardized logger
        logger.error(
            f"HYBRID_SEARCH: placeholders={placeholder_count}, params={param_count}, "
            f"service={repr(service_val)}, component={repr(component_val)}"
        )
        logger.error(
            f"HYBRID_SEARCH: param list length={len(exec_params)}, "
            f"params={[type(p).__name__ for p in exec_params]}"
        )
        
        # Verify parameter count matches query placeholders
        if param_count != placeholder_count:
            error_msg = (
                f"Parameter mismatch: query has {placeholder_count} placeholders "
                f"but {param_count} parameters provided. "
                f"Service: {repr(service_val)}, Component: {repr(component_val)}. "
                f"Params: {[str(p)[:50] if isinstance(p, str) else str(p) for p in exec_params]}"
            )
            logger.error(f"HYBRID_SEARCH ERROR: {error_msg}")
            raise ValueError(error_msg)
        
        try:
            cur.execute(query, exec_params)
        except Exception as e:
            logger.error(f"HYBRID_SEARCH SQL ERROR: {e}")
            logger.error(f"Query placeholders: {placeholder_count}, Params: {param_count}")
            logger.error(f"Service: {repr(service_val)}, Component: {repr(component_val)}")
            raise
        
        results = cur.fetchall()
        
        duration = time.time() - start_time
        logger.debug(
            f"Hybrid search completed: found {len(results)} results in {duration:.3f}s"
        )

        # Diagnostic: log top fused hits to verify RRF/MMR behavior
        top_preview = []
        for row in results[:3]:
            top_preview.append(
                {
                    "doc_id": str(row["document_id"]),
                    "doc_type": row["doc_type"],
                    "vector_score": float(row["vector_score"]) if row["vector_score"] else 0.0,
                    "fulltext_score": float(row["fulltext_score"]) if row["fulltext_score"] else 0.0,
                    "rrf_score": float(row["rrf_score"]),
                    "title": (row["doc_title"] or "")[:80],
                }
            )
        logger.info(
            "HYBRID_SEARCH TOP RESULTS: "
            f"count={len(results)}, duration_sec={duration:.3f}, "
            f"service={repr(service_val)}, component={repr(component_val)}, "
            f"vector_weight={vector_weight}, fulltext_weight={fulltext_weight}, "
            f"preview={top_preview}"
        )
        
        # Convert to list of dicts
        chunks = []
        for row in results:
            chunks.append({
                "chunk_id": str(row["id"]),
                "document_id": str(row["document_id"]),
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "metadata": row["metadata"],
                "doc_title": row["doc_title"],
                "doc_type": row["doc_type"],
                "vector_score": float(row["vector_score"]) if row["vector_score"] else 0.0,
                "fulltext_score": float(row["fulltext_score"]) if row["fulltext_score"] else 0.0,
                "rrf_score": float(row["rrf_score"])
            })
        
        return chunks
    
    finally:
        cur.close()
        conn.close()


def mmr_search(
    query_text: str,
    service: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 5,
    diversity: float = 0.5
) -> List[Dict]:
    """
    Maximal Marginal Relevance search for diverse results.
    
    Args:
        query_text: Search query
        service: Optional service filter
        component: Optional component filter
        limit: Number of results
        diversity: Diversity parameter (0-1, higher = more diverse)
    
    Returns:
        List of diverse chunks
    """
    # Get initial results from hybrid search
    candidates = hybrid_search(query_text, service, component, limit=limit * 3)
    
    if not candidates:
        return []
    
    # Simple MMR: select first result, then iteratively add most relevant
    # that is also diverse from already selected
    selected = []
    remaining = candidates.copy()
    
    # First result is always the top one
    if remaining:
        selected.append(remaining.pop(0))
    
    # For remaining slots, balance relevance and diversity
    while len(selected) < limit and remaining:
        best_idx = 0
        best_score = -1
        
        for idx, candidate in enumerate(remaining):
            # Relevance score (RRF score)
            relevance = candidate["rrf_score"]
            
            # Diversity: max similarity to already selected
            max_sim = 0.0
            if selected:
                # Simple heuristic: if same document, lower diversity
                for sel in selected:
                    if candidate["document_id"] == sel["document_id"]:
                        max_sim = 0.8  # High similarity if same doc
                    else:
                        max_sim = max(max_sim, 0.3)  # Lower similarity if different doc
            
            # MMR score: lambda * relevance - (1 - lambda) * max_similarity
            mmr_score = diversity * relevance - (1 - diversity) * max_sim
            
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        
        selected.append(remaining.pop(best_idx))
    
    return selected

