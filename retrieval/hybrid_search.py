"""Hybrid search combining vector similarity and full-text search."""

from retrieval.incident_descriptions import get_incident_descriptions

import os
import time
from typing import List, Dict, Optional, Union
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


def _normalize_limit(limit: Union[int, str, float, None], default: int = 5) -> int:
    """
    Normalize limit parameter to integer.
    
    Args:
        limit: Limit value (can be int, string, float, or None)
        default: Default value if limit is None or invalid
    
    Returns:
        Integer limit value
    """
    if limit is None:
        return default
    
    try:
        if isinstance(limit, (int, float)):
            limit_int = int(limit)
        elif isinstance(limit, str):
            limit_int = int(limit.strip())
        else:
            return default
        
        # Ensure positive
        if limit_int < 1:
            return default
        return limit_int
    except (ValueError, TypeError, AttributeError):
        logger.warning(f"Invalid limit value: {repr(limit)}, using default: {default}")
        return default


def _normalize_query_text(query_text: Optional[str]) -> str:
    """
    Normalize query text parameter.
    
    Args:
        query_text: Query text (can be None, empty string, or string)
    
    Returns:
        Normalized query text (empty string if None/invalid)
    """
    if query_text is None:
        return ""
    
    if isinstance(query_text, str):
        return query_text.strip()
    
    # Try to convert to string
    try:
        return str(query_text).strip()
    except Exception:
        return ""


def hybrid_search(
    query_text: str,
    service: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 5,
    vector_weight: float = 0.7,
    fulltext_weight: float = 0.3,
    rrf_k: int = 60,
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
    # Normalize and validate parameters
    query_text = _normalize_query_text(query_text)
    limit = _normalize_limit(limit, default=5)
    rrf_k = _normalize_limit(rrf_k, default=60)
    
    if not query_text:
        logger.warning("Empty query text provided to hybrid_search, returning empty results")
        return []
    
    start_time = time.time()
    logger.debug(
        f"Starting hybrid search: query='{query_text[:100]}...', "
        f"service={service}, component={component}, limit={limit}"
    )
    
    # TASK #7: Track retrieval metrics
    try:
        from retrieval.metrics import record_retrieval
        _track_metrics = True
    except ImportError:
        _track_metrics = False

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Generate query embedding
        query_embedding = embed_text(query_text)
        if query_embedding is None:
            logger.error(f"Failed to generate query embedding. Cannot proceed with hybrid search.")
            return []
        # Convert to pgvector string format
        query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # Normalize service and component (ensure None or non-empty strings)
        service_val = service if service and str(service).strip() else None
        component_val = component if component and str(component).strip() else None

        # PHASE 1: Soft Filters - Remove hard WHERE filters, use as relevance boosters instead
        # Service/component are now used as score boosters in ORDER BY, not WHERE filters
        # This allows semantic search to find relevant content even with mismatches
        # Match quality will be calculated in the final ORDER BY clause
        filter_clause = ""  # No hard filters - all results included, ranked by relevance + match boosts

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
                -- RRF: 1/(k + rank) where k is configurable (default 60)
                (1.0 / ({rrf_k}.0 + COALESCE(v.vector_rank, 999))) * {vector_weight} +
                (1.0 / ({rrf_k}.0 + COALESCE(f.fulltext_rank, 999))) * {fulltext_weight} as rrf_score,
                -- PHASE 1: Soft filter boosts for service/component matching
                -- Service match boost: exact match = 0.15, partial match = 0.10, no match = 0.0
                CASE 
                    WHEN %s IS NULL THEN 0.0
                    WHEN LOWER(COALESCE(v.metadata->>'service', f.metadata->>'service', '')) = LOWER(%s) THEN 0.15
                    WHEN LOWER(COALESCE(v.metadata->>'service', f.metadata->>'service', '')) LIKE LOWER(%s) THEN 0.10
                    ELSE 0.0
                END as service_match_boost,
                -- Component match boost: exact match = 0.10, partial match = 0.05, no match = 0.0
                CASE 
                    WHEN %s IS NULL THEN 0.0
                    WHEN LOWER(COALESCE(v.metadata->>'component', f.metadata->>'component', '')) = LOWER(%s) THEN 0.10
                    WHEN LOWER(COALESCE(v.metadata->>'component', f.metadata->>'component', '')) LIKE LOWER(%s) THEN 0.05
                    ELSE 0.0
                END as component_match_boost
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
            rrf_score,
            service_match_boost,
            component_match_boost,
            -- Final score: RRF + service boost + component boost
            rrf_score + service_match_boost + component_match_boost as final_score
        FROM combined_results
        WHERE rrf_score > 0
        ORDER BY final_score DESC
        LIMIT %s
        """

        # Build params list matching the query placeholders in order
        # Query placeholders in order (PHASE 1: no hard filters, but soft filter boosts):
        # 1: embedding (vector_score)
        # 2: embedding (vector_rank)
        # 3: embedding (ORDER BY)
        # 4: limit (vector_results)
        # 5: text (fulltext_score)
        # 6: text (fulltext_rank)
        # 7: text (WHERE)
        # 8: text (ORDER BY)
        # 9: limit (fulltext_results)
        # 10-15: Service/component match boost params (service_val check, service_val exact, service_val partial, component_val check, component_val exact, component_val partial)
        # 16: final limit
        exec_params = []

        # Vector results params
        exec_params.append(query_embedding_str)  # 1: vector_score embedding
        exec_params.append(query_embedding_str)  # 2: vector_rank embedding
        exec_params.append(query_embedding_str)  # 3: ORDER BY embedding
        exec_params.append(limit * 2)  # 4: vector_results limit

        # Fulltext results params
        exec_params.append(query_text)  # 5: fulltext_score text
        exec_params.append(query_text)  # 6: fulltext_rank text
        exec_params.append(query_text)  # 7: WHERE text
        exec_params.append(query_text)  # 8: ORDER BY text
        exec_params.append(limit * 2)  # 9: fulltext_results limit

        # Soft filter boost params (for service/component match detection)
        # Service match boost params
        exec_params.append(service_val)  # 10: service_val check (IS NULL)
        exec_params.append(service_val if service_val else None)  # 11: service_val exact match
        exec_params.append(f"%{service_val}%" if service_val else None)  # 12: service_val partial match
        
        # Component match boost params
        exec_params.append(component_val)  # 13: component_val check (IS NULL)
        exec_params.append(component_val if component_val else None)  # 14: component_val exact match
        exec_params.append(f"%{component_val}%" if component_val else None)  # 15: component_val partial match

        # Final limit
        exec_params.append(limit)  # 16: final limit

        # CRITICAL: Verify we have exactly the right number of parameters
        # Base: 16 params (9 for search + 6 for soft filter boosts + 1 for final limit)
        expected_params = 16

        if len(exec_params) != expected_params:
            raise ValueError(
                f"Parameter count mismatch: expected {expected_params} params "
                f"but built {len(exec_params)} params. "
                f"Service: {repr(service_val)}, Component: {repr(component_val)}. "
                f"This is a bug in the query parameter building logic."
            )

        # Debug: verify parameter count and log BEFORE execute
        placeholder_count = query.count("%s")
        param_count = len(exec_params)

        # Log using standardized logger (DEBUG level for diagnostic info)
        logger.debug(
            f"HYBRID_SEARCH: placeholders={placeholder_count}, params={param_count}, "
            f"service={repr(service_val)}, component={repr(component_val)}"
        )
        logger.debug(
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
        logger.debug(f"Hybrid search completed: found {len(results)} results in {duration:.3f}s")

        # Diagnostic: log top fused hits to verify RRF/MMR behavior
        top_preview = []
        for row in results[:3]:
            top_preview.append(
                {
                    "doc_id": str(row["document_id"]),
                    "doc_type": row["doc_type"],
                    "vector_score": float(row["vector_score"]) if row["vector_score"] else 0.0,
                    "fulltext_score": (
                        float(row["fulltext_score"]) if row["fulltext_score"] else 0.0
                    ),
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
            # Safe metadata access - ensure it's a dict (psycopg with dict_row should always return dicts)
            metadata = row.get("metadata") if isinstance(row, dict) else {}
            if not isinstance(metadata, dict):
                logger.warning(f"Metadata is not a dict, converting: {type(metadata)}")
                metadata = {}
            
            chunks.append(
                {
                    "chunk_id": str(row.get("id", "")),
                    "document_id": str(row.get("document_id", "")),
                    "chunk_index": row.get("chunk_index", 0),
                    "content": row.get("content", ""),
                    "metadata": metadata,
                    "doc_title": row.get("doc_title", ""),
                    "doc_type": row.get("doc_type", ""),
                    "vector_score": float(row.get("vector_score", 0.0)) if row.get("vector_score") else 0.0,
                    "fulltext_score": float(row.get("fulltext_score", 0.0)) if row.get("fulltext_score") else 0.0,
                    "rrf_score": float(row.get("rrf_score", 0.0)),
                    "service_match_boost": float(row.get("service_match_boost", 0.0)),
                    "component_match_boost": float(row.get("component_match_boost", 0.0)),
                    "final_score": float(row.get("final_score", row.get("rrf_score", 0.0))),
                }
            )

        # TASK #7: Record retrieval metrics
        if _track_metrics:
            retrieval_time_ms = (time.time() - start_time) * 1000
            try:
                record_retrieval(
                    results=chunks,
                    retrieval_type="hybrid_search",
                    service=service,
                    component=component,
                    query_service=service,
                    query_component=component,
                    retrieval_time_ms=retrieval_time_ms,
                )
            except Exception as e:
                logger.debug(f"Failed to record retrieval metrics: {e}")

        return chunks

    finally:
        cur.close()
        conn.close()


def mmr_search(
    query_text: str,
    service: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 5,
    diversity: float = 0.5,
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
    # Normalize limit
    limit = _normalize_limit(limit, default=5)
    
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


def triage_retrieval(
    query_text: str,
    service: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 5,
    vector_weight: float = 0.7,
    fulltext_weight: float = 0.3,
    rrf_k: int = 60,
) -> Dict[str, List[Dict]]:
    """
    Specialized retrieval for triage agent.

    Per architecture: Triage agent may ONLY retrieve:
    - Incident signatures (chunks with incident_signature_id in metadata)
    - Runbook metadata (documents with doc_type='runbook', NOT runbook steps)

    Args:
        query_text: Search query
        service: Optional service filter
        component: Optional component filter
        limit: Number of results per type
        vector_weight: Weight for vector search (0-1)
        fulltext_weight: Weight for full-text search (0-1)

    Returns:
        Dictionary with:
        - 'incident_signatures': List of incident signature chunks
        - 'runbook_metadata': List of runbook document metadata (not steps)
    """
    start_time = time.time()
    logger.debug(
        f"Starting triage retrieval: query='{query_text[:100]}...', "
        f"service={service}, component={component}, limit={limit}"
    )
    
    # TASK #7: Track retrieval metrics
    try:
        from retrieval.metrics import record_retrieval
        _track_metrics = True
    except ImportError:
        _track_metrics = False

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Generate query embedding
        query_embedding = embed_text(query_text)
        if query_embedding is None:
            logger.error(f"Failed to generate query embedding for triage retrieval. Cannot proceed.")
            return {"incident_signatures": [], "runbook_metadata": []}
        query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # Normalize service and component
        service_val = service if service and str(service).strip() else None
        component_val = component if component and str(component).strip() else None

        # PHASE 1: Soft Filters - Remove hard WHERE filters, use as relevance boosters instead
        # Service/component are now used as score boosters in ORDER BY, not WHERE filters
        # This allows semantic search to find relevant incident signatures even with mismatches
        filter_clause = ""  # No hard filters - all results included, ranked by relevance + match boosts

        # Retrieve incident signatures directly from incident_signatures table
        # (No need for chunks table - embeddings and tsvector are already in incident_signatures)
        # Parameter order:
        # Vector: $1 (score), $2 (rank), $3 (ORDER BY), $4 (limit), [filters for vector]
        # Fulltext: $5 (score), $6 (rank), $7 (WHERE), $8 (ORDER BY), $9 (limit), [filters for fulltext]
        # Final: $last (final limit)
        incident_sig_query = f"""
        WITH vector_results AS (
            SELECT 
                s.id,
                s.source_document_id as document_id,
                0 as chunk_index,
                -- Create content from signature fields for display
                CONCAT(
                    'Failure Type: ', COALESCE(s.failure_type, ''),
                    E'\\nError Class: ', COALESCE(s.error_class, ''),
                    E'\\nSymptoms: ', COALESCE(array_to_string(s.symptoms, ', '), ''),
                    E'\\nService: ', COALESCE(s.service, ''),
                    E'\\nComponent: ', COALESCE(s.component, '')
                ) as content,
                -- Create metadata JSON from signature fields
                jsonb_build_object(
                    'incident_signature_id', s.incident_signature_id,
                    'failure_type', s.failure_type,
                    'error_class', s.error_class,
                    'symptoms', s.symptoms,
                    'affected_service', s.affected_service,
                    'service', s.service,
                    'component', s.component,
                    'assignment_group', s.assignment_group,
                    'impact', s.impact,
                    'urgency', s.urgency,
                    'source_incident_ids', s.source_incident_ids,
                    'match_count', COALESCE(array_length(s.source_incident_ids, 1), 0)
                ) as metadata,
                COALESCE(s.affected_service, s.service) as doc_title,
                'incident_signature' as doc_type,
                1 - (s.embedding <=> %s::vector) as vector_score,
                ROW_NUMBER() OVER (ORDER BY s.embedding <=> %s::vector) as vector_rank
            FROM incident_signatures s
            WHERE s.embedding IS NOT NULL
            {filter_clause}
            ORDER BY s.embedding <=> %s::vector
            LIMIT %s
        ),
        fulltext_results AS (
            SELECT 
                s.id,
                s.source_document_id as document_id,
                0 as chunk_index,
                CONCAT(
                    'Failure Type: ', COALESCE(s.failure_type, ''),
                    E'\\nError Class: ', COALESCE(s.error_class, ''),
                    E'\\nSymptoms: ', COALESCE(array_to_string(s.symptoms, ', '), ''),
                    E'\\nService: ', COALESCE(s.service, ''),
                    E'\\nComponent: ', COALESCE(s.component, '')
                ) as content,
                jsonb_build_object(
                    'incident_signature_id', s.incident_signature_id,
                    'failure_type', s.failure_type,
                    'error_class', s.error_class,
                    'symptoms', s.symptoms,
                    'affected_service', s.affected_service,
                    'service', s.service,
                    'component', s.component,
                    'assignment_group', s.assignment_group,
                    'impact', s.impact,
                    'urgency', s.urgency,
                    'source_incident_ids', s.source_incident_ids,
                    'match_count', COALESCE(array_length(s.source_incident_ids, 1), 0)
                ) as metadata,
                COALESCE(s.affected_service, s.service) as doc_title,
                'incident_signature' as doc_type,
                ts_rank(s.tsv, plainto_tsquery('english', %s::text)) as fulltext_score,
                ROW_NUMBER() OVER (ORDER BY ts_rank(s.tsv, plainto_tsquery('english', %s::text)) DESC) as fulltext_rank
            FROM incident_signatures s
            WHERE s.tsv @@ plainto_tsquery('english', %s::text)
            {filter_clause}
            ORDER BY ts_rank(s.tsv, plainto_tsquery('english', %s::text)) DESC
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
                (1.0 / ({rrf_k}.0 + COALESCE(v.vector_rank, 999))) * {vector_weight} +
                (1.0 / ({rrf_k}.0 + COALESCE(f.fulltext_rank, 999))) * {fulltext_weight} as rrf_score,
                -- PHASE 1: Soft filter boosts for service/component matching
                -- Service match boost: exact match = 0.15, partial match = 0.10, no match = 0.0
                -- Check both service and affected_service fields
                CASE 
                    WHEN %s IS NULL THEN 0.0
                    WHEN LOWER(COALESCE(v.metadata->>'service', f.metadata->>'service', '')) = LOWER(%s) 
                         OR LOWER(COALESCE(v.metadata->>'affected_service', f.metadata->>'affected_service', '')) = LOWER(%s) THEN 0.15
                    WHEN LOWER(COALESCE(v.metadata->>'service', f.metadata->>'service', '')) LIKE LOWER(%s)
                         OR LOWER(COALESCE(v.metadata->>'affected_service', f.metadata->>'affected_service', '')) LIKE LOWER(%s) THEN 0.10
                    ELSE 0.0
                END as service_match_boost,
                -- Component match boost: exact match = 0.10, partial match = 0.05, no match = 0.0
                -- If signature component is NULL, don't penalize (allow match)
                CASE 
                    WHEN %s IS NULL THEN 0.0
                    WHEN COALESCE(v.metadata->>'component', f.metadata->>'component', '') = '' THEN 0.05  -- NULL component gets small boost
                    WHEN LOWER(COALESCE(v.metadata->>'component', f.metadata->>'component', '')) = LOWER(%s) THEN 0.10
                    WHEN LOWER(COALESCE(v.metadata->>'component', f.metadata->>'component', '')) LIKE LOWER(%s) THEN 0.05
                    ELSE 0.0
                END as component_match_boost
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
            rrf_score,
            service_match_boost,
            component_match_boost,
            -- Final score: RRF + service boost + component boost
            rrf_score + service_match_boost + component_match_boost as final_score
        FROM combined_results
        WHERE rrf_score > 0
        ORDER BY final_score DESC
        LIMIT %s
        """

        # Build params for incident signatures
        # Query parameter order (PHASE 1: no hard filters, but soft filter boosts):
        # Vector CTE: $1=score, $2=rank, $3=ORDER BY, $4=limit
        # Fulltext CTE: $5=score, $6=rank, $7=WHERE, $8=ORDER BY, $9=limit
        # Soft filter boosts: $10-15 (service check, service exact x2, service partial x2, component check, component exact, component partial)
        # Final: $16=final limit
        sig_params = []
        # Vector CTE
        sig_params.append(query_embedding_str)  # 1: vector_score
        sig_params.append(query_embedding_str)  # 2: vector_rank
        sig_params.append(query_embedding_str)  # 3: vector ORDER BY
        sig_params.append(limit)  # 4: vector limit
        # Fulltext CTE
        sig_params.append(str(query_text))  # 5: fulltext_score
        sig_params.append(str(query_text))  # 6: fulltext_rank
        sig_params.append(str(query_text))  # 7: fulltext WHERE
        sig_params.append(str(query_text))  # 8: fulltext ORDER BY
        sig_params.append(limit)  # 9: fulltext limit
        # Soft filter boost params (for service/component match detection)
        # Service match boost params (check both service and affected_service)
        sig_params.append(service_val)  # 10: service_val check (IS NULL)
        sig_params.append(service_val if service_val else None)  # 11: service_val exact match (service field)
        sig_params.append(service_val if service_val else None)  # 12: service_val exact match (affected_service field)
        sig_params.append(f"%{service_val}%" if service_val else None)  # 13: service_val partial match (service field)
        sig_params.append(f"%{service_val}%" if service_val else None)  # 14: service_val partial match (affected_service field)
        # Component match boost params
        sig_params.append(component_val)  # 15: component_val check (IS NULL)
        sig_params.append(component_val if component_val else None)  # 16: component_val exact match
        sig_params.append(f"%{component_val}%" if component_val else None)  # 17: component_val partial match
        # Final limit
        sig_params.append(limit)  # 18: final limit

        # Execute incident signatures query
        cur.execute(incident_sig_query, sig_params)
        incident_sig_rows = cur.fetchall()

        # Collect all source_incident_ids to fetch descriptions
        all_source_incident_ids = []
        for row in incident_sig_rows:
            if isinstance(row, dict):
                metadata = row.get("metadata", {})
            else:
                metadata = row[4] if isinstance(row[4], dict) else {}
            source_ids = metadata.get("source_incident_ids", [])
            if source_ids:
                all_source_incident_ids.extend(source_ids)

        # Fetch original incident descriptions
        incident_descriptions = {}
        if all_source_incident_ids:
            unique_incident_ids = list(set(all_source_incident_ids))
            try:
                incident_descriptions = get_incident_descriptions(unique_incident_ids)
            except Exception as e:
                logger.warning(f"Failed to fetch incident descriptions: {e}")

        incident_signatures = []
        for row in incident_sig_rows:
            if isinstance(row, dict):
                metadata = row["metadata"] if isinstance(row["metadata"], dict) else {}
                source_ids = metadata.get("source_incident_ids", [])

                # Enhance content with original incident descriptions
                enhanced_content = row["content"]
                if source_ids and incident_descriptions:
                    desc_parts = []
                    for inc_id in source_ids[:2]:  # Show up to 2 incident descriptions
                        if inc_id in incident_descriptions:
                            desc = incident_descriptions[inc_id]
                            if desc.get("title"):
                                desc_parts.append(
                                    f"Original Incident {inc_id} - Title: {desc['title']}"
                                )
                            if desc.get("description"):
                                # Truncate description to 200 chars
                                desc_text = desc["description"][:200] + (
                                    "..." if len(desc["description"]) > 200 else ""
                                )
                                desc_parts.append(
                                    f"Original Incident {inc_id} - Description: {desc_text}"
                                )
                    if desc_parts:
                        enhanced_content = row["content"] + "\n\n" + "\n".join(desc_parts)

                incident_signatures.append(
                    {
                        "chunk_id": str(row["id"]),
                        "document_id": str(row["document_id"]),
                        "chunk_index": row["chunk_index"],
                        "content": enhanced_content,
                        "metadata": metadata,
                        "doc_title": row["doc_title"],
                        "doc_type": row["doc_type"],
                        "vector_score": float(row["vector_score"]) if row["vector_score"] else 0.0,
                        "fulltext_score": (
                            float(row["fulltext_score"]) if row["fulltext_score"] else 0.0
                        ),
                        "rrf_score": float(row["rrf_score"]) if row["rrf_score"] else 0.0,
                    }
                )
            else:
                # Handle tuple result
                metadata = row[4] if isinstance(row[4], dict) else {}
                source_ids = metadata.get("source_incident_ids", [])

                # Enhance content with original incident descriptions
                enhanced_content = row[3]
                if source_ids and incident_descriptions:
                    desc_parts = []
                    for inc_id in source_ids[:2]:  # Show up to 2 incident descriptions
                        if inc_id in incident_descriptions:
                            desc = incident_descriptions[inc_id]
                            if desc.get("title"):
                                desc_parts.append(
                                    f"Original Incident {inc_id} - Title: {desc['title']}"
                                )
                            if desc.get("description"):
                                # Truncate description to 200 chars
                                desc_text = desc["description"][:200] + (
                                    "..." if len(desc["description"]) > 200 else ""
                                )
                                desc_parts.append(
                                    f"Original Incident {inc_id} - Description: {desc_text}"
                                )
                    if desc_parts:
                        enhanced_content = row[3] + "\n\n" + "\n".join(desc_parts)

                # Handle tuple result - check if we have soft filter boost columns
                row_len = len(row)
                incident_signatures.append(
                    {
                        "chunk_id": str(row[0]),
                        "document_id": str(row[1]),
                        "chunk_index": row[2],
                        "content": enhanced_content,
                        "metadata": metadata,
                        "doc_title": row[5],
                        "doc_type": row[6],
                        "vector_score": float(row[7]) if row[7] else 0.0,
                        "fulltext_score": float(row[8]) if row[8] else 0.0,
                        "rrf_score": float(row[9]) if row[9] else 0.0,
                        "service_match_boost": float(row[10]) if row_len > 10 and row[10] else 0.0,
                        "component_match_boost": float(row[11]) if row_len > 11 and row[11] else 0.0,
                        "final_score": float(row[12]) if row_len > 12 and row[12] else float(row[9]) if row[9] else 0.0,
                    }
                )

        # Retrieve runbook metadata (documents only, NOT steps)
        # Runbook metadata is in documents table, not chunks
        # PHASE 1: No hard filters - use soft filter boosts in ORDER BY
        runbook_params = [query_text]  # For full-text search

        # PHASE 1: Soft Filters - Remove hard WHERE filters for runbook metadata
        # Service/component are now used as relevance boosters, not WHERE filters
        # This allows semantic search to find relevant runbooks even with mismatches
        runbook_filter_clause = ""  # No hard filters - all results included, ranked by relevance
        runbook_params.append(limit)  # For LIMIT

        runbook_meta_query = f"""
        SELECT 
            d.id as document_id,
            d.doc_type,
            d.service,
            d.component,
            d.title,
            d.tags,
            d.last_reviewed_at,
            -- Use document title/content for full-text search
            ts_rank(to_tsvector('english', COALESCE(d.title, '') || ' ' || COALESCE(d.content, '')), 
                    plainto_tsquery('english', %s)) as relevance_score,
            -- PHASE 1: Soft filter boosts for service/component matching
            CASE 
                WHEN %s IS NULL THEN 0.0
                WHEN LOWER(COALESCE(d.service, '')) = LOWER(%s) THEN 0.15
                WHEN LOWER(COALESCE(d.service, '')) LIKE LOWER(%s) THEN 0.10
                ELSE 0.0
            END as service_match_boost,
            CASE 
                WHEN %s IS NULL THEN 0.0
                WHEN LOWER(COALESCE(d.component, '')) = LOWER(%s) THEN 0.10
                WHEN LOWER(COALESCE(d.component, '')) LIKE LOWER(%s) THEN 0.05
                ELSE 0.0
            END as component_match_boost
        FROM documents d
        WHERE d.doc_type = 'runbook'
        ORDER BY (relevance_score + 
                  CASE WHEN %s IS NULL THEN 0.0
                       WHEN LOWER(COALESCE(d.service, '')) = LOWER(%s) THEN 0.15
                       WHEN LOWER(COALESCE(d.service, '')) LIKE LOWER(%s) THEN 0.10
                       ELSE 0.0 END +
                  CASE WHEN %s IS NULL THEN 0.0
                       WHEN LOWER(COALESCE(d.component, '')) = LOWER(%s) THEN 0.10
                       WHEN LOWER(COALESCE(d.component, '')) LIKE LOWER(%s) THEN 0.05
                       ELSE 0.0 END) DESC, 
                 d.last_reviewed_at DESC NULLS LAST
        LIMIT %s
        """

        # Build params for runbook metadata query with soft filter boosts
        # Query params: query_text, service_val check, service_val exact, service_val partial (x2 for ORDER BY),
        #               component_val check, component_val exact, component_val partial (x2 for ORDER BY), limit
        runbook_params_extended = [
            query_text,  # 1: fulltext search
            service_val,  # 2: service check (SELECT)
            service_val if service_val else None,  # 3: service exact (SELECT)
            f"%{service_val}%" if service_val else None,  # 4: service partial (SELECT)
            component_val,  # 5: component check (SELECT)
            component_val if component_val else None,  # 6: component exact (SELECT)
            f"%{component_val}%" if component_val else None,  # 7: component partial (SELECT)
            service_val,  # 8: service check (ORDER BY)
            service_val if service_val else None,  # 9: service exact (ORDER BY)
            f"%{service_val}%" if service_val else None,  # 10: service partial (ORDER BY)
            component_val,  # 11: component check (ORDER BY)
            component_val if component_val else None,  # 12: component exact (ORDER BY)
            f"%{component_val}%" if component_val else None,  # 13: component partial (ORDER BY)
            limit,  # 14: limit
        ]
        cur.execute(runbook_meta_query, runbook_params_extended)
        runbook_rows = cur.fetchall()

        runbook_metadata = []
        for row in runbook_rows:
            if isinstance(row, dict):
                tags = row["tags"] if isinstance(row["tags"], dict) else {}
                runbook_metadata.append(
                    {
                        "document_id": str(row["document_id"]),
                        "doc_type": row["doc_type"],
                        "service": row["service"],
                        "component": row["component"],
                        "title": row["title"],
                        "tags": tags,
                        "last_reviewed_at": (
                            row["last_reviewed_at"].isoformat() if row["last_reviewed_at"] else None
                        ),
                        "relevance_score": (
                            float(row["relevance_score"]) if row["relevance_score"] else 0.0
                        ),
                        "service_match_boost": float(row.get("service_match_boost", 0.0)) if "service_match_boost" in row else 0.0,
                        "component_match_boost": float(row.get("component_match_boost", 0.0)) if "component_match_boost" in row else 0.0,
                    }
                )
            else:
                tags = row[5] if isinstance(row[5], dict) else {}
                runbook_metadata.append(
                    {
                        "document_id": str(row[0]),
                        "doc_type": row[1],
                        "service": row[2],
                        "component": row[3],
                        "title": row[4],
                        "tags": tags,
                        "last_reviewed_at": row[6].isoformat() if row[6] else None,
                        "relevance_score": float(row[7]) if row[7] else 0.0,
                        "service_match_boost": float(row[8]) if len(row) > 8 and row[8] else 0.0,
                        "component_match_boost": float(row[9]) if len(row) > 9 and row[9] else 0.0,
                    }
                )

        logger.debug(
            f"Triage retrieval completed: {len(incident_signatures)} signatures, "
            f"{len(runbook_metadata)} runbook metadata"
        )

        result = {
            "incident_signatures": incident_signatures,
            "runbook_metadata": runbook_metadata,
        }
        
        # TASK #7: Record retrieval metrics
        if _track_metrics:
            retrieval_time_ms = (time.time() - start_time) * 1000
            try:
                # Combine all results for metrics
                all_results = incident_signatures + runbook_metadata
                record_retrieval(
                    results=all_results,
                    retrieval_type="triage_retrieval",
                    service=service,
                    component=component,
                    query_service=service,
                    query_component=component,
                    retrieval_time_ms=retrieval_time_ms,
                )
            except Exception as e:
                logger.debug(f"Failed to record triage retrieval metrics: {e}")
        
        return result

    finally:
        cur.close()
        conn.close()
