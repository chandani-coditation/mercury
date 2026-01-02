"""Retrieval functions for Resolution Agent.

Per architecture: Resolution agent retrieves:
- Runbook steps (by runbook_id from triage output, using semantic search for relevance)
- Historical resolution references (from incident signatures)
"""

from typing import List, Dict, Optional
from db.connection import get_db_connection
from ai_service.core import get_logger
from ingestion.embeddings import embed_text

logger = get_logger(__name__)


def retrieve_runbook_steps(
    runbook_ids: List[str] = None,
    document_ids: List[str] = None,
    query_text: Optional[str] = None,
    failure_type: Optional[str] = None,
    error_class: Optional[str] = None,
    limit: int = 20
) -> List[Dict]:
    """
    Retrieve relevant runbook steps from chunks table using document_id (preferred) or runbook_steps table.
    
    Per architecture Section 7.3: Resolution agent retrieves "only relevant steps".
    
    Preferred method: Use document_id from triage to fetch chunks (contains full recommendations).
    Fallback method: Use runbook_id to fetch from runbook_steps table.
    
    Args:
        runbook_ids: Optional list of runbook_id values (fallback method)
        document_ids: Optional list of document_id values from triage runbook_metadata (preferred method)
        query_text: Optional query text for semantic search (e.g., alert description)
        failure_type: Optional failure type for relevance filtering
        error_class: Optional error class for relevance filtering
        limit: Maximum number of steps to return (default 20)
        
    Returns:
        List of runbook step dictionaries with all step details, ordered by relevance
    """
    # Prefer document_ids over runbook_ids (chunks contain full recommendations)
    if document_ids:
        return retrieve_runbook_chunks_by_document_id(document_ids, query_text, limit)
    
    if not runbook_ids:
        return []
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        placeholders = ",".join(["%s"] * len(runbook_ids))
        
        # If query_text is provided, use semantic search to find relevant steps
        if query_text:
            try:
                # Generate query embedding for semantic search
                query_embedding = embed_text(query_text)
                embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
                
                # Build query with semantic similarity
                # Parameters: $1 = embedding (for similarity), $2-$N = runbook_ids, $N+1 = embedding (for ORDER BY), $N+2 = limit
                query = f"""
                SELECT 
                    rs.id,
                    rs.step_id,
                    rs.runbook_id,
                    rs.condition,
                    rs.action,
                    rs.expected_outcome,
                    rs.rollback,
                    rs.risk_level,
                    rs.service,
                    rs.component,
                    rs.runbook_title,
                    rs.runbook_document_id,
                    1 - (rs.embedding <=> %s::vector) as similarity_score
                FROM runbook_steps rs
                WHERE rs.runbook_id IN ({placeholders})
                AND rs.embedding IS NOT NULL
                ORDER BY rs.embedding <=> %s::vector
                LIMIT %s
                """
                
                # Execute with: embedding (for similarity calc), runbook_ids, embedding (for ORDER BY), limit
                params = (embedding_str,) + tuple(runbook_ids) + (embedding_str, limit)
                cur.execute(query, params)
                logger.info(f"Retrieved relevant runbook steps using semantic search for query: {query_text[:50]}...")
            except Exception as e:
                logger.warning(f"Semantic search failed, falling back to direct retrieval: {e}")
                # Rollback the failed transaction before trying fallback
                conn.rollback()
                # Fall back to direct retrieval without semantic search
                query_text = None
        
        # If no query_text or semantic search failed, retrieve all steps (fallback)
        if not query_text:
            query = f"""
            SELECT 
                id,
                step_id,
                runbook_id,
                condition,
                action,
                expected_outcome,
                rollback,
                risk_level,
                service,
                component,
                runbook_title,
                runbook_document_id,
                1.0 as similarity_score
            FROM runbook_steps
            WHERE runbook_id IN ({placeholders})
            ORDER BY runbook_id, step_id
            LIMIT %s
            """
            
            # Execute with runbook_ids and limit
            params = tuple(runbook_ids) + (limit,)
            cur.execute(query, params)
        
        rows = cur.fetchall()
        
        steps = []
        for row in rows:
            if isinstance(row, dict):
                step = {
                    "step_id": row["step_id"],
                    "runbook_id": row["runbook_id"],
                    "condition": row["condition"],
                    "action": row["action"],
                    "expected_outcome": row.get("expected_outcome"),
                    "rollback": row.get("rollback"),
                    "risk_level": row.get("risk_level", "medium"),
                    "service": row.get("service"),
                    "component": row.get("component"),
                    "runbook_title": row.get("runbook_title"),
                    "runbook_document_id": str(row["runbook_document_id"]) if row.get("runbook_document_id") else None,
                    # For compatibility with existing code that expects chunk_id
                    "chunk_id": str(row["id"]),
                    "document_id": str(row["runbook_document_id"]) if row.get("runbook_document_id") else None,
                }
                # Add similarity score if available (from semantic search)
                if "similarity_score" in row:
                    step["similarity_score"] = float(row["similarity_score"]) if row["similarity_score"] else 0.0
                steps.append(step)
            else:
                # Handle tuple result
                step = {
                    "step_id": row[1],
                    "runbook_id": row[2],
                    "condition": row[3],
                    "action": row[4],
                    "expected_outcome": row[5],
                    "rollback": row[6],
                    "risk_level": row[7] if row[7] else "medium",
                    "service": row[8],
                    "component": row[9],
                    "runbook_title": row[10],
                    "runbook_document_id": str(row[11]) if row[11] else None,
                    # For compatibility
                    "chunk_id": str(row[0]),
                    "document_id": str(row[11]) if row[11] else None,
                }
                # Add similarity score if available (from semantic search)
                if len(row) > 12:
                    step["similarity_score"] = float(row[12]) if row[12] else 0.0
                steps.append(step)
        
        logger.info(f"Retrieved {len(steps)} runbook steps for runbook_ids: {runbook_ids}")
        return steps
        
    finally:
        cur.close()
        conn.close()


def retrieve_runbook_chunks_by_document_id(
    document_ids: List[str],
    query_text: Optional[str] = None,
    limit: int = 20
) -> List[Dict]:
    """
    Retrieve runbook steps from chunks table using document_id.
    
    This is the preferred method because chunks contain full recommendation text.
    Per architecture: Resolution agent should use chunks when available.
    
    Args:
        document_ids: List of document_id values from triage runbook_metadata
        query_text: Optional query text for semantic search
        limit: Maximum number of chunks to return
        
    Returns:
        List of runbook step dictionaries with full content from chunks
    """
    if not document_ids:
        return []
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        placeholders = ",".join(["%s"] * len(document_ids))
        
        # If query_text is provided, use semantic search
        if query_text:
            try:
                query_embedding = embed_text(query_text)
                embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
                
                query = f"""
                SELECT 
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.content,
                    c.metadata,
                    1 - (c.embedding <=> %s::vector) as similarity_score,
                    d.title as runbook_title,
                    d.tags->>'runbook_id' as runbook_id
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.document_id IN ({placeholders})
                AND d.doc_type = 'runbook'
                AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """
                
                # Execute with: embedding (for similarity calc), document_ids, embedding (for ORDER BY), limit
                params = (embedding_str,) + tuple(document_ids) + (embedding_str, limit)
                cur.execute(query, params)
                logger.info(f"Retrieved runbook chunks using semantic search for document_ids: {document_ids}")
            except Exception as e:
                logger.warning(f"Semantic search failed, falling back to direct retrieval: {e}")
                # Rollback the failed transaction before trying fallback
                conn.rollback()
                query_text = None
        
        # Fallback: retrieve all chunks for document_ids
        if not query_text:
            query = f"""
            SELECT 
                c.id,
                c.document_id,
                c.chunk_index,
                c.content,
                c.metadata,
                1.0 as similarity_score,
                d.title as runbook_title,
                d.tags->>'runbook_id' as runbook_id
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.document_id IN ({placeholders})
            AND d.doc_type = 'runbook'
            ORDER BY c.chunk_index
            LIMIT %s
            """
            
            cur.execute(query, tuple(document_ids) + (limit,))
        
        rows = cur.fetchall()
        
        steps = []
        for row in rows:
            if isinstance(row, dict):
                metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
                step = {
                    "step_id": metadata.get("step_id") or f"chunk-{row['id']}",
                    "runbook_id": row.get("runbook_id") or metadata.get("runbook_id"),
                    "condition": metadata.get("condition") or "Step applies",
                    "action": row.get("content") or metadata.get("action") or "",
                    "expected_outcome": metadata.get("expected_outcome"),
                    "rollback": metadata.get("rollback"),
                    "risk_level": metadata.get("risk_level", "medium"),
                    "service": metadata.get("service"),
                    "component": metadata.get("component"),
                    "runbook_title": row.get("runbook_title"),
                    "runbook_document_id": str(row.get("document_id")),
                    "chunk_id": str(row.get("id")),
                    "document_id": str(row.get("document_id")),
                }
                if "similarity_score" in row:
                    step["similarity_score"] = float(row["similarity_score"]) if row["similarity_score"] else 0.0
                steps.append(step)
            else:
                metadata = row[4] if isinstance(row[4], dict) else {}
                step = {
                    "step_id": metadata.get("step_id") if isinstance(metadata, dict) else f"chunk-{row[0]}",
                    "runbook_id": row[7] or (metadata.get("runbook_id") if isinstance(metadata, dict) else None),
                    "condition": metadata.get("condition") if isinstance(metadata, dict) else "Step applies",
                    "action": row[3] or (metadata.get("action") if isinstance(metadata, dict) else ""),
                    "expected_outcome": metadata.get("expected_outcome") if isinstance(metadata, dict) else None,
                    "rollback": metadata.get("rollback") if isinstance(metadata, dict) else None,
                    "risk_level": metadata.get("risk_level", "medium") if isinstance(metadata, dict) else "medium",
                    "service": metadata.get("service") if isinstance(metadata, dict) else None,
                    "component": metadata.get("component") if isinstance(metadata, dict) else None,
                    "runbook_title": row[6],
                    "runbook_document_id": str(row[1]),
                    "chunk_id": str(row[0]),
                    "document_id": str(row[1]),
                }
                if len(row) > 5:
                    step["similarity_score"] = float(row[5]) if row[5] else 0.0
                steps.append(step)
        
        logger.info(f"Retrieved {len(steps)} runbook chunks for document_ids: {document_ids}")
        return steps
        
    finally:
        cur.close()
        conn.close()


def retrieve_close_notes_from_signatures(
    incident_signature_ids: List[str],
    limit: int = 10
) -> List[Dict]:
    """
    Retrieve close_notes from incident signatures.
    
    This retrieves resolution notes/close notes from historical incidents
    that match the incident signatures. These notes provide valuable context
    about how similar incidents were resolved.
    
    Args:
        incident_signature_ids: List of incident_signature_id values from triage output
        limit: Maximum number of close_notes to return
        
    Returns:
        List of dictionaries with close_notes and metadata:
        [
            {
                "incident_signature_id": "SIG-123",
                "close_notes": "Resolution notes...",
                "failure_type": "SQL_AGENT_JOB_FAILURE",
                "error_class": "STEP_EXECUTION_ERROR",
                "match_count": 5
            }
        ]
    """
    if not incident_signature_ids:
        return []
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        placeholders = ",".join(["%s"] * len(incident_signature_ids))
        
        query = f"""
        SELECT 
            incident_signature_id,
            close_notes,
            failure_type,
            error_class,
            match_count
        FROM incident_signatures
        WHERE incident_signature_id IN ({placeholders})
        AND close_notes IS NOT NULL
        AND close_notes != ''
        ORDER BY match_count DESC, last_seen_at DESC
        LIMIT %s
        """
        
        params = list(incident_signature_ids) + [limit]
        cur.execute(query, params)
        rows = cur.fetchall()
        
        close_notes_list = []
        for row in rows:
            if isinstance(row, dict):
                close_notes_list.append({
                    "incident_signature_id": row["incident_signature_id"],
                    "close_notes": row["close_notes"],
                    "failure_type": row["failure_type"],
                    "error_class": row["error_class"],
                    "match_count": row["match_count"],
                })
            else:
                close_notes_list.append({
                    "incident_signature_id": row[0],
                    "close_notes": row[1],
                    "failure_type": row[2],
                    "error_class": row[3],
                    "match_count": row[4],
                })
        
        logger.debug(
            f"Retrieved {len(close_notes_list)} close_notes "
            f"for signature_ids: {incident_signature_ids}"
        )
        return close_notes_list
        
    finally:
        cur.close()
        conn.close()


def retrieve_historical_resolutions(
    incident_signature_ids: List[str],
    limit: int = 10
) -> List[Dict]:
    """
    Retrieve historical resolutions from incidents that match incident signatures.
    
    Per architecture: Historical resolutions are stored in incidents.resolution_output.
    We find incidents that were resolved using steps referenced by the incident signatures.
    
    Args:
        incident_signature_ids: List of incident_signature_id values from triage output
        limit: Maximum number of historical resolutions to return
        
    Returns:
        List of historical resolution records with success indicators
    """
    if not incident_signature_ids:
        return []
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Find incidents that:
        # 1. Have resolution_output (were resolved)
        # 2. Have triage_output with matching incident_signature_ids
        # 3. Have resolution_accepted_at (successfully applied) or resolution_proposed_at (proposed)
        
        # We'll match by checking if the triage_output contains any of the signature IDs
        placeholders = ",".join(["%s"] * len(incident_signature_ids))
        
        query = f"""
        SELECT 
            i.id,
            i.alert_id,
            i.triage_output,
            i.resolution_output,
            i.resolution_evidence,
            i.resolution_proposed_at,
            i.resolution_accepted_at,
            i.rollback_status,
            i.rollback_initiated_at,
            i.created_at
        FROM incidents i
        WHERE i.resolution_output IS NOT NULL
        AND i.triage_output IS NOT NULL
        AND (
            -- Check if triage_output->'matched_evidence'->'incident_signatures' contains any of our IDs
            EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(i.triage_output->'matched_evidence'->'incident_signatures', '[]'::jsonb)
                ) AS sig_id
                WHERE sig_id IN ({placeholders})
            )
        )
        ORDER BY 
            -- Prefer accepted resolutions (successful)
            CASE WHEN i.resolution_accepted_at IS NOT NULL THEN 0 ELSE 1 END,
            -- Then by recency
            i.resolution_proposed_at DESC NULLS LAST,
            i.created_at DESC
        LIMIT %s
        """
        
        params = list(incident_signature_ids) + [limit]
        cur.execute(query, params)
        rows = cur.fetchall()
        
        historical_resolutions = []
        for row in rows:
            if isinstance(row, dict):
                triage_output = row["triage_output"] if isinstance(row["triage_output"], dict) else {}
                resolution_output = row["resolution_output"] if isinstance(row["resolution_output"], dict) else {}
                
                # Determine success: accepted = successful, proposed but not accepted = partial
                is_successful = row["resolution_accepted_at"] is not None
                rollback_triggered = row["rollback_status"] in ["initiated", "in_progress", "completed"]
                
                historical_resolutions.append({
                    "incident_id": str(row["id"]),
                    "alert_id": row["alert_id"],
                    "triage_output": triage_output,
                    "resolution_output": resolution_output,
                    "resolution_evidence": row["resolution_evidence"],
                    "resolution_proposed_at": row["resolution_proposed_at"].isoformat() if row["resolution_proposed_at"] else None,
                    "resolution_accepted_at": row["resolution_accepted_at"].isoformat() if row["resolution_accepted_at"] else None,
                    "is_successful": is_successful,
                    "rollback_triggered": rollback_triggered,
                    "rollback_status": row["rollback_status"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                })
            else:
                # Handle tuple result
                triage_output = row[2] if isinstance(row[2], dict) else {}
                resolution_output = row[3] if isinstance(row[3], dict) else {}
                
                is_successful = row[6] is not None
                rollback_triggered = row[7] in ["initiated", "in_progress", "completed"]
                
                historical_resolutions.append({
                    "incident_id": str(row[0]),
                    "alert_id": row[1],
                    "triage_output": triage_output,
                    "resolution_output": resolution_output,
                    "resolution_evidence": row[4],
                    "resolution_proposed_at": row[5].isoformat() if row[5] else None,
                    "resolution_accepted_at": row[6].isoformat() if row[6] else None,
                    "is_successful": is_successful,
                    "rollback_triggered": rollback_triggered,
                    "rollback_status": row[7],
                    "created_at": row[9].isoformat() if row[9] else None,
                })
        
        logger.debug(
            f"Retrieved {len(historical_resolutions)} historical resolutions "
            f"for signature_ids: {incident_signature_ids}"
        )
        return historical_resolutions
        
    finally:
        cur.close()
        conn.close()


def get_step_success_stats(step_ids: List[str]) -> Dict[str, Dict]:
    """
    Get success statistics for specific runbook steps.
    
    This analyzes historical resolutions to determine which steps have been successful.
    Uses provenance chunk_id to match steps to historical resolutions.
    
    Args:
        step_ids: List of step_id values (e.g., ["RB123-S3"])
        
    Returns:
        Dictionary mapping step_id to success statistics:
        {
            "RB123-S3": {
                "total_uses": 5,
                "successful_uses": 4,
                "success_rate": 0.8,
                "last_used": "2024-01-15T10:30:00"
            }
        }
    """
    if not step_ids:
        return {}
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # First, get chunk_ids for these step_ids
        placeholders = ",".join(["%s"] * len(step_ids))
        
        # Get chunk_ids for the step_ids
        chunk_query = f"""
        SELECT id, metadata->>'step_id' as step_id
        FROM chunks
        WHERE metadata->>'step_id' IN ({placeholders})
        """
        
        cur.execute(chunk_query, step_ids)
        chunk_rows = cur.fetchall()
        
        # Build mapping: step_id -> chunk_ids
        step_to_chunks = {step_id: [] for step_id in step_ids}
        for row in chunk_rows:
            if isinstance(row, dict):
                chunk_id = str(row["id"])
                step_id = row["step_id"]
            else:
                chunk_id = str(row[0])
                step_id = row[1]
            
            if step_id in step_to_chunks:
                step_to_chunks[step_id].append(chunk_id)
        
        # Now find incidents that reference these chunk_ids in provenance
        all_chunk_ids = [cid for chunks in step_to_chunks.values() for cid in chunks]
        
        if not all_chunk_ids:
            # No chunks found for these step_ids
            return {step_id: {"total_uses": 0, "successful_uses": 0, "success_rate": 0.5, "last_used": None}
                    for step_id in step_ids}
        
        chunk_placeholders = ",".join(["%s"] * len(all_chunk_ids))
        
        query = f"""
        SELECT 
            i.resolution_output,
            i.resolution_accepted_at,
            i.resolution_proposed_at
        FROM incidents i
        WHERE i.resolution_output IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
                COALESCE(i.resolution_output->'provenance', '[]'::jsonb)
            ) AS prov
            WHERE prov->>'chunk_id' IN ({chunk_placeholders})
        )
        ORDER BY i.resolution_proposed_at DESC NULLS LAST
        """
        
        cur.execute(query, all_chunk_ids)
        rows = cur.fetchall()
        
        # Build statistics
        stats = {step_id: {"total_uses": 0, "successful_uses": 0, "last_used": None} 
                 for step_id in step_ids}
        
        for row in rows:
            if isinstance(row, dict):
                resolution_output = row["resolution_output"] if isinstance(row["resolution_output"], dict) else {}
                is_successful = row["resolution_accepted_at"] is not None
                proposed_at = row["resolution_proposed_at"]
            else:
                resolution_output = row[0] if isinstance(row[0], dict) else {}
                is_successful = row[1] is not None
                proposed_at = row[2]
            
            # Get provenance chunk_ids from this resolution
            provenance = resolution_output.get("provenance", [])
            prov_chunk_ids = [p.get("chunk_id") for p in provenance if isinstance(p, dict) and p.get("chunk_id")]
            
            # Check which step_ids are referenced via their chunk_ids
            for step_id, chunk_ids in step_to_chunks.items():
                if any(cid in prov_chunk_ids for cid in chunk_ids):
                    stats[step_id]["total_uses"] += 1
                    if is_successful:
                        stats[step_id]["successful_uses"] += 1
                    if proposed_at and (
                        stats[step_id]["last_used"] is None or 
                        proposed_at > stats[step_id]["last_used"]
                    ):
                        stats[step_id]["last_used"] = proposed_at
        
        # Calculate success rates
        for step_id, stat in stats.items():
            if stat["total_uses"] > 0:
                stat["success_rate"] = stat["successful_uses"] / stat["total_uses"]
            else:
                stat["success_rate"] = 0.5  # Default to neutral if no history
        
        logger.debug(f"Step success stats: {stats}")
        return stats
        
    finally:
        cur.close()
        conn.close()

