"""Hybrid search combining vector similarity and full-text search."""

from retrieval.incident_descriptions import get_incident_descriptions
from retrieval.query_builders import HybridSearchQueryBuilder

import os
import time
from typing import List, Dict, Optional, Union
from db.connection import get_db_connection_context
from ingestion.embeddings import embed_text

# Import logging (use ai_service logger if available, fallback to standard logging)
try:
    from ai_service.core import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger(__name__)


def _normalize_limit(limit: Union[int, str, float, None], default: int = 10) -> int:
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
    limit: int = 10,  # Increased from 5 to 10 for better results
    vector_weight: float = 0.7,
    fulltext_weight: float = 0.3,
    rrf_k: int = 60,
    fulltext_query_text: Optional[str] = None,
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
    # Use simpler query for full-text search if provided, otherwise use query_text for both
    fulltext_query = (
        _normalize_query_text(fulltext_query_text)
        if fulltext_query_text is not None
        else query_text
    )
    limit = _normalize_limit(limit, default=10)  # Increased default from 5 to 10
    rrf_k = _normalize_limit(rrf_k, default=HybridSearchQueryBuilder.DEFAULT_RRF_K)

    if not query_text:
        logger.warning("Empty query text provided to hybrid_search, returning empty results")
        return []

    start_time = time.time()

    try:
        from retrieval.metrics import record_retrieval
        _track_metrics = True
    except ImportError:
        _track_metrics = False

    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Generate query embedding
            query_embedding = embed_text(query_text)
            if query_embedding is None:
                logger.error(
                    f"Failed to generate query embedding. Cannot proceed with hybrid search."
                )
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
            filter_clause = (
                ""  # No hard filters - all results included, ranked by relevance + match boosts
            )

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
            WHERE c.tsv IS NOT NULL
            AND length(plainto_tsquery('english', %s)::text) > 0
            AND c.tsv @@ plainto_tsquery('english', %s)
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
                -- Calculate fulltext_score: use from fulltext_results if available,
                -- otherwise calculate ts_rank for chunks that have tsv but didn't match the query
                COALESCE(
                    f.fulltext_score,
                    CASE 
                        WHEN v.id IS NOT NULL AND c.tsv IS NOT NULL 
                             AND length(plainto_tsquery('english', %s)::text) > 0
                        THEN ts_rank(c.tsv, plainto_tsquery('english', %s))
                        ELSE 0.0
                    END
                ) as fulltext_score,
                COALESCE(v.vector_rank, 999) as vector_rank,
                -- Calculate fulltext_rank: use from fulltext_results if available,
                -- otherwise assign a high rank (999) for non-matching chunks
                COALESCE(f.fulltext_rank, 999) as fulltext_rank,
                -- RRF: 1/(k + rank) where k is configurable (default 60)
                {HybridSearchQueryBuilder.build_rrf_score_formula(vector_weight, fulltext_weight, rrf_k)} as rrf_score,
                -- PHASE 1: Soft filter boosts for service/component matching
                {HybridSearchQueryBuilder.build_service_boost_case()} as service_match_boost,
                {HybridSearchQueryBuilder.build_component_boost_case()} as component_match_boost
            FROM vector_results v
            FULL OUTER JOIN fulltext_results f ON v.id = f.id
            LEFT JOIN chunks c ON COALESCE(v.id, f.id) = c.id
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
            # 7: text (WHERE - first plainto_tsquery)
            # 8: text (WHERE - empty check)
            # 9: text (ORDER BY)
            # 10: limit (fulltext_results)
            # 11-16: Service/component match boost params (service_val check, service_val exact, service_val partial, component_val check, component_val exact, component_val partial)
            # 17-18: fulltext_query for combined_results (ts_rank calculation for non-matching chunks)
            # 19: final limit
            exec_params = []

            # Calculate RRF candidate limit (higher multiplier for better fusion results)
            candidate_limit = HybridSearchQueryBuilder.calculate_rrf_candidate_limit(limit)

            # Vector results params
            exec_params.append(query_embedding_str)  # 1: vector_score embedding
            exec_params.append(query_embedding_str)  # 2: vector_rank embedding
            exec_params.append(query_embedding_str)  # 3: ORDER BY embedding
            exec_params.append(candidate_limit)  # 4: vector_results limit (improved multiplier)

            # Fulltext results params - use simpler query for full-text search
            exec_params.append(fulltext_query)  # 5: fulltext_score text
            exec_params.append(fulltext_query)  # 6: fulltext_rank text
            exec_params.append(fulltext_query)  # 7: WHERE text (first plainto_tsquery)
            exec_params.append(fulltext_query)  # 8: WHERE text (empty check)
            exec_params.append(fulltext_query)  # 9: ORDER BY text
            exec_params.append(candidate_limit)  # 10: fulltext_results limit (improved multiplier)

            # Soft filter boost params (using centralized builder)
            exec_params.extend(
                HybridSearchQueryBuilder.build_soft_filter_boost_params(service_val, component_val)
            )  # 11-16: Service and component boost params

            # Combined results params - fulltext query for calculating ts_rank for non-matching chunks
            exec_params.append(
                fulltext_query
            )  # 17: fulltext_query for length check in combined_results
            exec_params.append(fulltext_query)  # 18: fulltext_query for ts_rank in combined_results

            # Final limit
            exec_params.append(limit)  # 19: final limit

            # CRITICAL: Verify we have exactly the right number of parameters
            # Base: 19 params (10 for search + 6 for soft filter boosts + 2 for combined_results fulltext + 1 for final limit)
            # Vector: 3 (score, rank, order by) + 1 (limit) = 4
            # Fulltext: 5 (score, rank, empty check, @@, order by) + 1 (limit) = 6
            # Service boost: 3 params, Component boost: 3 params = 6
            # Combined results fulltext: 2 params (length check, ts_rank)
            # Final limit: 1
            # Total: 4 + 6 + 6 + 2 + 1 = 19
            expected_params = 19

            if len(exec_params) != expected_params:
                raise ValueError(
                    f"Parameter count mismatch: expected {expected_params} params "
                    f"but built {len(exec_params)} params. "
                    f"Service: {repr(service_val)}, Component: {repr(component_val)}. "
                    f"This is a bug in the query parameter building logic."
                )

            # Validate parameter count using centralized validator
            is_valid, error_msg = HybridSearchQueryBuilder.validate_parameter_count(
                query, exec_params, expected_count=19
            )
            if not is_valid:
                logger.error(f"HYBRID_SEARCH ERROR: {error_msg}")
                logger.error(
                    f"Service: {repr(service_val)}, Component: {repr(component_val)}. "
                    f"Params: {[str(p)[:50] if isinstance(p, str) else str(p) for p in exec_params]}"
                )
                raise ValueError(error_msg)

                f"service={repr(service_val)}, component={repr(component_val)}"
            )

            try:
                cur.execute(query, exec_params)
            except Exception as e:
                logger.error(f"HYBRID_SEARCH SQL ERROR: {e}")
                logger.error(f"Query placeholders: {query.count('%s')}, Params: {len(exec_params)}")
                logger.error(f"Service: {repr(service_val)}, Component: {repr(component_val)}")
                raise

            results = cur.fetchall()

            chunks = []
            for row in results:
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
                        "vector_score": (
                            float(row.get("vector_score", 0.0)) if row.get("vector_score") else 0.0
                        ),
                        "fulltext_score": (
                            float(row.get("fulltext_score", 0.0))
                            if row.get("fulltext_score")
                            else 0.0
                        ),
                        "rrf_score": float(row.get("rrf_score", 0.0)),
                        "service_match_boost": float(row.get("service_match_boost", 0.0)),
                        "component_match_boost": float(row.get("component_match_boost", 0.0)),
                        "final_score": float(row.get("final_score", row.get("rrf_score", 0.0))),
                    }
                )

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
                    pass

            return chunks

        finally:
            cur.close()


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
    limit: int = 10,  # Increased from 5 to 10 for better results
    vector_weight: float = 0.7,
    fulltext_weight: float = 0.3,
    rrf_k: int = 60,
    fulltext_query_text: Optional[str] = None,
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
    # Use simpler query for full-text search if provided, otherwise use query_text for both
    fulltext_query = fulltext_query_text if fulltext_query_text is not None else query_text

    # For runbooks, clean the enhanced query_text to remove URLs and special characters
    # that can break plainto_tsquery, but keep more context than the cleaned fulltext_query_text
    import re

    def clean_query_for_runbooks(text: str) -> str:
        """Clean query for runbook full-text search: remove URLs and IPs, keep words"""
        if not text:
            return ""
        # Remove URLs
        cleaned = re.sub(r"https?://\S+|www\.\S+", "", text)
        # Remove IP addresses
        cleaned = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "", cleaned)
        # Remove special characters except spaces and hyphens
        cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", cleaned)
        # Replace multiple spaces with single space
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    # For runbooks, use the enhanced query_text directly (original behavior)
    # This gives runbooks more context to match properly
    # Note: We still clean it to remove URLs/IPs that break plainto_tsquery, but keep more context
    runbook_fulltext_query = clean_query_for_runbooks(query_text) if query_text else fulltext_query
    # If cleaned query is empty or too short, fall back to fulltext_query
    if not runbook_fulltext_query or len(runbook_fulltext_query.strip()) < 10:
        runbook_fulltext_query = fulltext_query
        f"fulltext_query='{fulltext_query[:100]}...', "
        f"service={service}, component={component}, limit={limit}"
    )

    try:
        from retrieval.metrics import record_retrieval
        _track_metrics = True
    except ImportError:
        _track_metrics = False

    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Generate query embedding
            query_embedding = embed_text(query_text)
            if query_embedding is None:
                logger.error(
                    f"Failed to generate query embedding for triage retrieval. Cannot proceed."
                )
                return {"incident_signatures": [], "runbook_metadata": []}
            query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

            # Normalize service and component
            service_val = service if service and str(service).strip() else None
            component_val = component if component and str(component).strip() else None

            # PHASE 1: Soft Filters - Remove hard WHERE filters, use as relevance boosters instead
            # Service/component are now used as score boosters in ORDER BY, not WHERE filters
            # This allows semantic search to find relevant incident signatures even with mismatches
            filter_clause = (
                ""  # No hard filters - all results included, ranked by relevance + match boosts
            )

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
            WHERE s.tsv IS NOT NULL
            AND length(plainto_tsquery('english', %s::text)::text) > 0
            AND s.tsv @@ plainto_tsquery('english', %s::text)
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
                -- Calculate fulltext_score: use from fulltext_results if available,
                -- otherwise calculate ts_rank for incident signatures that have tsv but didn't match the query
                COALESCE(
                    f.fulltext_score,
                    CASE 
                        WHEN v.id IS NOT NULL AND s.tsv IS NOT NULL 
                             AND length(plainto_tsquery('english', %s::text)::text) > 0
                        THEN ts_rank(s.tsv, plainto_tsquery('english', %s::text))
                        ELSE 0.0
                    END
                ) as fulltext_score,
                COALESCE(v.vector_rank, 999) as vector_rank,
                -- Calculate fulltext_rank: use from fulltext_results if available,
                -- otherwise assign a high rank (999) for non-matching signatures
                COALESCE(f.fulltext_rank, 999) as fulltext_rank,
                {HybridSearchQueryBuilder.build_rrf_score_formula(vector_weight, fulltext_weight, rrf_k)} as rrf_score,
                -- PHASE 1: Soft filter boosts for service/component matching
                -- Service match boost: checks both service and affected_service fields
                {HybridSearchQueryBuilder.build_service_boost_case_dual()} as service_match_boost,
                -- Component match boost: allows NULL component boost for incident signatures
                {HybridSearchQueryBuilder.build_component_boost_case(allow_null_boost=True)} as component_match_boost
            FROM vector_results v
            FULL OUTER JOIN fulltext_results f ON v.id = f.id
            LEFT JOIN incident_signatures s ON COALESCE(v.id, f.id) = s.id
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

            # Calculate RRF candidate limit (higher multiplier for better fusion results)
            candidate_limit = HybridSearchQueryBuilder.calculate_rrf_candidate_limit(limit)

            # Build params for incident signatures
            sig_params = []
            # Vector CTE
            sig_params.append(query_embedding_str)  # 1: vector_score
            sig_params.append(query_embedding_str)  # 2: vector_rank
            sig_params.append(query_embedding_str)  # 3: vector ORDER BY
            sig_params.append(candidate_limit)  # 4: vector limit (improved multiplier)
            # Fulltext CTE - use simpler query for full-text search
            sig_params.append(str(fulltext_query))  # 5: fulltext_score
            sig_params.append(str(fulltext_query))  # 6: fulltext_rank
            sig_params.append(str(fulltext_query))  # 7: fulltext WHERE (first plainto_tsquery)
            sig_params.append(str(fulltext_query))  # 8: fulltext WHERE (empty check)
            sig_params.append(str(fulltext_query))  # 9: fulltext ORDER BY
            sig_params.append(candidate_limit)  # 10: fulltext limit (improved multiplier)
            # Soft filter boost params (using centralized builder for dual service matching)
            sig_params.extend(
                HybridSearchQueryBuilder.build_soft_filter_boost_params_dual_service(
                    service_val, component_val
                )
            )  # 11-18: Service (dual) and component boost params
            # Combined results params - fulltext query for calculating ts_rank for non-matching signatures
            sig_params.append(
                str(fulltext_query)
            )  # 19: fulltext_query for length check in combined_results
            sig_params.append(
                str(fulltext_query)
            )  # 20: fulltext_query for ts_rank in combined_results
            # Final limit
            sig_params.append(limit)  # 21: final limit
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
                            "vector_score": (
                                float(row["vector_score"]) if row["vector_score"] else 0.0
                            ),
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
                            "service_match_boost": (
                                float(row[10]) if row_len > 10 and row[10] else 0.0
                            ),
                            "component_match_boost": (
                                float(row[11]) if row_len > 11 and row[11] else 0.0
                            ),
                            "final_score": (
                                float(row[12])
                                if row_len > 12 and row[12]
                                else float(row[9]) if row[9] else 0.0
                            ),
                        }
                    )

            # Retrieve runbook metadata (documents only, NOT steps)
            # Runbook metadata is in documents table, not chunks
            # PHASE 1: No hard filters - use soft filter boosts in ORDER BY
            # Use cleaned enhanced query for runbooks (defined above at function start)
            runbook_params = [
                runbook_fulltext_query
            ]  # For full-text search (use cleaned enhanced query)

            # PHASE 1: Soft Filters - Remove hard WHERE filters for runbook metadata
            # Service/component are now used as relevance boosters, not WHERE filters
            # This allows semantic search to find relevant runbooks even with mismatches
            runbook_filter_clause = (
                ""  # No hard filters - all results included, ranked by relevance
            )
            runbook_params.append(limit)  # For LIMIT

            runbook_meta_query = f"""
            SELECT *
            FROM (
                SELECT 
                    d.id AS document_id,
                    d.doc_type,
                    d.service,
                    d.component,
                    d.title,
                    d.tags,
                    d.last_reviewed_at,
                    ts_rank(
                        to_tsvector('english', COALESCE(d.title, '') || ' ' || COALESCE(d.content, '')),
                        plainto_tsquery('english', %s)
                    ) AS relevance_score,
                    {HybridSearchQueryBuilder.build_service_boost_case("COALESCE(d.service, '')")} AS service_match_boost,
                    {HybridSearchQueryBuilder.build_component_boost_case("COALESCE(d.component, '')")} AS component_match_boost
                FROM documents d
                WHERE d.doc_type = 'runbook'
            ) ranked
            ORDER BY
                (relevance_score + service_match_boost + component_match_boost) DESC,
                last_reviewed_at DESC NULLS LAST
            LIMIT %s
            """

            # Build params for runbook metadata query with soft filter boosts
            # Query params: runbook_fulltext_query (ts_rank), soft filter boosts (SELECT only), limit
            # Note: ORDER BY doesn't use parameters - it just references the calculated columns
            # Use cleaned enhanced query for runbooks (more context than fulltext_query_text, but cleaned)
            runbook_params_extended = [
                runbook_fulltext_query,  # 1: fulltext search for ts_rank
            ]
            # Add soft filter boost params for SELECT only (6 params: 3 for service, 3 for component)
            runbook_params_extended.extend(
                HybridSearchQueryBuilder.build_soft_filter_boost_params(service_val, component_val)
            )
            # Final limit
            runbook_params_extended.append(limit)  # 10: limit
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
                                row["last_reviewed_at"].isoformat()
                                if row["last_reviewed_at"]
                                else None
                            ),
                            "relevance_score": (
                                float(row["relevance_score"]) if row["relevance_score"] else 0.0
                            ),
                            "service_match_boost": (
                                float(row.get("service_match_boost", 0.0))
                                if "service_match_boost" in row
                                else 0.0
                            ),
                            "component_match_boost": (
                                float(row.get("component_match_boost", 0.0))
                                if "component_match_boost" in row
                                else 0.0
                            ),
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
                            "service_match_boost": (
                                float(row[8]) if len(row) > 8 and row[8] else 0.0
                            ),
                            "component_match_boost": (
                                float(row[9]) if len(row) > 9 and row[9] else 0.0
                            ),
                        }
                    )

                f"{len(runbook_metadata)} runbook metadata"
            )

            result = {
                "incident_signatures": incident_signatures,
                "runbook_metadata": runbook_metadata,
            }

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
                    pass

            return result

        finally:
            cur.close()
