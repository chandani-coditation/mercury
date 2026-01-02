"""Hybrid search combining vector similarity and full-text search."""

from retrieval.incident_descriptions import get_incident_descriptions

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
    fulltext_weight: float = 0.3,
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
        query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # Normalize service and component (ensure None or non-empty strings)
        service_val = service if service and str(service).strip() else None
        component_val = component if component and str(component).strip() else None

        # Build filter conditions with case-insensitive partial matching
        # This allows matching "database" with "Database-SQL", "Database", etc.
        filters = []
        filter_params = []

        if service_val:
            # Case-insensitive partial match: "database" matches "Database-SQL", "Database", etc.
            filters.append("COALESCE(LOWER(c.metadata->>'service'), '') LIKE LOWER(%s::text)")
            filter_params.append(f"%{service_val}%")

        if component_val:
            # Case-insensitive partial match: "sql-server" matches "sql-server", "SQL Server", etc.
            filters.append("COALESCE(LOWER(c.metadata->>'component'), '') LIKE LOWER(%s::text)")
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
            chunks.append(
                {
                    "chunk_id": str(row["id"]),
                    "document_id": str(row["document_id"]),
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "doc_title": row["doc_title"],
                    "doc_type": row["doc_type"],
                    "vector_score": float(row["vector_score"]) if row["vector_score"] else 0.0,
                    "fulltext_score": (
                        float(row["fulltext_score"]) if row["fulltext_score"] else 0.0
                    ),
                    "rrf_score": float(row["rrf_score"]),
                }
            )

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
    logger.debug(
        f"Starting triage retrieval: query='{query_text[:100]}...', "
        f"service={service}, component={component}, limit={limit}"
    )
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Generate query embedding
        query_embedding = embed_text(query_text)
        query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        # Normalize service and component
        service_val = service if service and str(service).strip() else None
        component_val = component if component and str(component).strip() else None
        
        # Build filter conditions for incident_signatures table
        # Use more flexible matching - service/component are hints, not strict filters
        filters = []
        filter_params = []
        
        if service_val:
            # More flexible: match service or affected_service, case-insensitive
            # Also allow partial matches (e.g., "Database" matches "Database-SQL")
            filters.append("""
                (COALESCE(LOWER(s.service), '') LIKE LOWER(%s::text)
                 OR COALESCE(LOWER(s.affected_service), '') LIKE LOWER(%s::text)
                 OR COALESCE(LOWER(s.service), '') LIKE LOWER(%s::text)
                 OR COALESCE(LOWER(s.affected_service), '') LIKE LOWER(%s::text))
            """)
            # Add multiple variations for better matching
            service_lower = service_val.lower()
            filter_params.extend([
                f"%{service_lower}%",  # service contains
                f"%{service_lower}%",  # affected_service contains
                f"{service_lower}%",   # service starts with
                f"{service_lower}%"    # affected_service starts with
            ])
        
        # Component filter: Make it completely optional
        # Strategy: If signature has no component (NULL/empty), it matches ANY alert component
        # This is critical for storage signatures which have component=NULL
        # We only apply component filter if signature actually has a component value
        # This allows:
        # - Alerts with component='Storage' to match signatures with component=NULL (most important)
        # - Alerts with component='Storage' to match signatures with component='Storage' or 'Disk' etc.
        # - Service match is still required (handled by service filter above)
        # 
        # Logic: Only filter by component if signature HAS a component value
        # If signature component is NULL/empty, don't filter by component at all
        # This is more permissive than the previous OR logic
        if component_val:
            # Only filter if signature has a component - if NULL, don't filter
            filters.append("""
                (COALESCE(s.component, '') = '' 
                 OR COALESCE(LOWER(s.component), '') LIKE LOWER(%s::text))
            """)
            component_lower = component_val.lower()
            filter_params.append(f"%{component_lower}%")
        
        filter_clause = " AND " + " AND ".join(filters) if filters else ""
        
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
        
        # Build params for incident signatures
        # Query parameter order (filter_clause is inserted AFTER WHERE and BEFORE ORDER BY):
        # Vector CTE: $1=score, $2=rank, $3...$N=filter_params, $N+1=ORDER BY, $N+2=limit
        # Fulltext CTE: $N+3=score, $N+4=rank, $N+5=WHERE, $N+6...$M=filter_params, $M+1=ORDER BY, $M+2=limit
        # Final: $M+3=final limit
        sig_params = []
        # Vector CTE
        sig_params.append(query_embedding_str)  # 1: vector_score
        sig_params.append(query_embedding_str)  # 2: vector_rank
        sig_params.extend(filter_params)  # 3...N: filter params (service + component) - inserted AFTER WHERE
        sig_params.append(query_embedding_str)  # N+1: vector ORDER BY
        sig_params.append(limit)  # N+2: vector limit
        # Fulltext CTE
        sig_params.append(str(query_text))  # N+3: fulltext_score
        sig_params.append(str(query_text))  # N+4: fulltext_rank
        sig_params.append(str(query_text))  # N+5: fulltext WHERE
        sig_params.extend(filter_params)  # N+6...M: filter params (service + component) - inserted AFTER WHERE
        sig_params.append(str(query_text))  # M+1: fulltext ORDER BY
        sig_params.append(limit)  # M+2: fulltext limit
        # Final
        sig_params.append(limit)  # M+3: final limit
        
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
                                desc_parts.append(f"Original Incident {inc_id} - Title: {desc['title']}")
                            if desc.get("description"):
                                # Truncate description to 200 chars
                                desc_text = desc["description"][:200] + ("..." if len(desc["description"]) > 200 else "")
                                desc_parts.append(f"Original Incident {inc_id} - Description: {desc_text}")
                    if desc_parts:
                        enhanced_content = row["content"] + "\n\n" + "\n".join(desc_parts)
                
                incident_signatures.append({
                    "chunk_id": str(row["id"]),
                    "document_id": str(row["document_id"]),
                    "chunk_index": row["chunk_index"],
                    "content": enhanced_content,
                    "metadata": metadata,
                    "doc_title": row["doc_title"],
                    "doc_type": row["doc_type"],
                    "vector_score": float(row["vector_score"]) if row["vector_score"] else 0.0,
                    "fulltext_score": float(row["fulltext_score"]) if row["fulltext_score"] else 0.0,
                    "rrf_score": float(row["rrf_score"]) if row["rrf_score"] else 0.0,
                })
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
                                desc_parts.append(f"Original Incident {inc_id} - Title: {desc['title']}")
                            if desc.get("description"):
                                # Truncate description to 200 chars
                                desc_text = desc["description"][:200] + ("..." if len(desc["description"]) > 200 else "")
                                desc_parts.append(f"Original Incident {inc_id} - Description: {desc_text}")
                    if desc_parts:
                        enhanced_content = row[3] + "\n\n" + "\n".join(desc_parts)
                
                incident_signatures.append({
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
                })
        
        # Retrieve runbook metadata (documents only, NOT steps)
        # Runbook metadata is in documents table, not chunks
        runbook_filters = []
        runbook_params = [query_text]  # For full-text search
        
        # Service filter: match if service contains the value (flexible matching)
        if service_val:
            runbook_filters.append("COALESCE(LOWER(d.service), '') LIKE LOWER(%s::text)")
            runbook_params.append(f"%{service_val}%")
        
        # Component filter: For triage, we prioritize service match over component match
        # Component is optional - if provided, we'll boost relevance but not exclude
        # This allows "Database" service alerts to match "Database Alerts" runbooks
        # even if component is "Database" vs "Alerts"
        # For now, skip component filter for runbook metadata - service + fulltext is sufficient
        # Component matching can be handled by relevance scoring
        
        runbook_filter_clause = " AND " + " AND ".join(runbook_filters) if runbook_filters else ""
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
                    plainto_tsquery('english', %s)) as relevance_score
        FROM documents d
        WHERE d.doc_type = 'runbook'
        {runbook_filter_clause}
        ORDER BY relevance_score DESC, d.last_reviewed_at DESC NULLS LAST
        LIMIT %s
        """
        
        cur.execute(runbook_meta_query, runbook_params)
        runbook_rows = cur.fetchall()
        
        runbook_metadata = []
        for row in runbook_rows:
            if isinstance(row, dict):
                tags = row["tags"] if isinstance(row["tags"], dict) else {}
                runbook_metadata.append({
                    "document_id": str(row["document_id"]),
                    "doc_type": row["doc_type"],
                    "service": row["service"],
                    "component": row["component"],
                    "title": row["title"],
                    "tags": tags,
                    "last_reviewed_at": row["last_reviewed_at"].isoformat() if row["last_reviewed_at"] else None,
                    "relevance_score": float(row["relevance_score"]) if row["relevance_score"] else 0.0,
                })
            else:
                tags = row[5] if isinstance(row[5], dict) else {}
                runbook_metadata.append({
                    "document_id": str(row[0]),
                    "doc_type": row[1],
                    "service": row[2],
                    "component": row[3],
                    "title": row[4],
                    "tags": tags,
                    "last_reviewed_at": row[6].isoformat() if row[6] else None,
                    "relevance_score": float(row[7]) if row[7] else 0.0,
                })
        
        logger.debug(
            f"Triage retrieval completed: {len(incident_signatures)} signatures, "
            f"{len(runbook_metadata)} runbook metadata"
        )
        
        return {
            "incident_signatures": incident_signatures,
            "runbook_metadata": runbook_metadata,
        }
    
    finally:
        cur.close()
        conn.close()
