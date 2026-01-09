"""Retrieval functions for Resolution Agent.

Per architecture: Resolution agent retrieves:
- Runbook steps (by runbook_id from triage output, using semantic search for relevance)
- Historical resolution references (from incident signatures)
"""

from typing import List, Dict, Optional, Union
from db.connection import get_db_connection_context
from ai_service.core import get_logger
from ingestion.embeddings import embed_text
import uuid

logger = get_logger(__name__)


def _normalize_uuid_list(ids: Optional[List[Union[str, uuid.UUID]]]) -> List[str]:
    """
    Normalize a list of IDs to strings (handles UUID objects, strings, None values).

    Args:
        ids: List of IDs (can be UUID objects, strings, or None)

    Returns:
        List of string IDs (None values and invalid IDs are filtered out)
    """
    if not ids:
        return []

    normalized = []
    for id_val in ids:
        if id_val is None:
            continue
        try:
            # Convert UUID to string if needed
            if isinstance(id_val, uuid.UUID):
                normalized.append(str(id_val))
            elif isinstance(id_val, str):
                # Validate it's a valid UUID string format
                uuid.UUID(id_val)  # Will raise ValueError if invalid
                normalized.append(id_val)
            else:
                # Try to convert to string
                str_val = str(id_val).strip()
                if str_val:
                    uuid.UUID(str_val)  # Validate
                    normalized.append(str_val)
        except (ValueError, AttributeError, TypeError):
            logger.warning(f"Invalid ID format, skipping: {repr(id_val)}")
            continue

    return normalized


def _normalize_limit(limit: Union[int, str, float, None], default: int = 20) -> int:
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


def _normalize_query_text(query_text: Optional[str]) -> Optional[str]:
    """
    Normalize query text parameter.

    Args:
        query_text: Query text (can be None, empty string, or string)

    Returns:
        Normalized query text (None if empty/invalid)
    """
    if query_text is None:
        return None

    if isinstance(query_text, str):
        text = query_text.strip()
        return text if text else None

    # Try to convert to string
    try:
        text = str(query_text).strip()
        return text if text else None
    except Exception:
        return None


def retrieve_runbook_chunks_by_document_id(
    document_ids: List[str], query_text: Optional[str] = None, limit: int = 20
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
    # Normalize and validate parameters
    document_ids = _normalize_uuid_list(document_ids) if document_ids else []
    query_text = _normalize_query_text(query_text)
    limit = _normalize_limit(limit, default=20)

    if not document_ids:
        return []

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Safety check: ensure we have valid IDs (should already be validated, but double-check)
            if not document_ids or len(document_ids) == 0:
                logger.warning("Empty document_ids list, returning empty results")
                return []

            placeholders = ",".join(["%s"] * len(document_ids))

            # If query_text is provided, use semantic search
            semantic_search_success = False
            if query_text:
                try:
                    query_embedding = embed_text(query_text)
                    if query_embedding is None:
                        logger.warning(
                            f"Failed to generate query embedding for semantic search. Falling back to direct retrieval."
                        )
                        query_text = None
                    else:
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
                    logger.info(
                        f"Retrieved runbook chunks using semantic search for document_ids: {document_ids}, query_text length: {len(query_text) if query_text else 0}"
                    )
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
                    NULL as similarity_score,
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
                    metadata = (
                        row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
                    )
                    # IMPORTANT: Use metadata.action (structured) instead of content (embedding text with prerequisites)
                    # The content field contains full embedding text: "Prerequisites: ... Condition: ... Action: ..."
                    # The metadata.action field contains just the action text that should be displayed
                    action_text = metadata.get("action") or ""
                    if not action_text and row.get("content"):
                        # Fallback: extract action from content if metadata doesn't have it
                        content = row.get("content", "")
                        if "Action:" in content:
                            # Extract action part from content
                            action_parts = content.split("Action:", 1)
                            if len(action_parts) > 1:
                                action_text = action_parts[1].strip()
                                # Remove trailing Service/Component info
                                if "\nService:" in action_text:
                                    action_text = action_text.split("\nService:")[0].strip()
                                if "\nComponent:" in action_text:
                                    action_text = action_text.split("\nComponent:")[0].strip()
                        else:
                            # Use content as fallback if no Action: marker
                            action_text = content

                    step = {
                        "step_id": metadata.get("step_id") or f"chunk-{row['id']}",
                        "runbook_id": row.get("runbook_id") or metadata.get("runbook_id"),
                        "condition": metadata.get("condition") or "Step applies",
                        "action": action_text,
                        "expected_outcome": metadata.get("expected_outcome"),
                        "rollback": metadata.get("rollback"),
                        "service": metadata.get("service"),
                        "component": metadata.get("component"),
                        "runbook_title": row.get("runbook_title"),
                        "runbook_document_id": str(row.get("document_id")),
                        "chunk_id": str(row.get("id")),
                        "document_id": str(row.get("document_id")),
                    }
                    if "similarity_score" in row:
                        similarity = (
                            float(row["similarity_score"])
                            if row["similarity_score"] is not None
                            else None
                        )
                        # Validate similarity score - 1.0 is suspicious (perfect match)
                        if similarity is not None and similarity >= 0.999:
                            logger.warning(
                                f"Suspicious similarity score {similarity} for chunk {row.get('id')} - "
                                f"perfect matches (>=0.999) are rare and may indicate an issue"
                            )
                            # Cap at 0.99 to avoid misleading 100% scores
                            similarity = min(similarity, 0.99)
                        step["similarity_score"] = similarity
                    steps.append(step)
                else:
                    metadata = row[4] if isinstance(row[4], dict) else {}
                    # IMPORTANT: Use metadata.action (structured) instead of content (embedding text with prerequisites)
                    action_text = ""
                    if isinstance(metadata, dict) and metadata.get("action"):
                        action_text = metadata.get("action")
                    elif row[3]:  # row[3] is content
                        # Fallback: extract action from content if metadata doesn't have it
                        content = row[3]
                        if "Action:" in content:
                            action_parts = content.split("Action:", 1)
                            if len(action_parts) > 1:
                                action_text = action_parts[1].strip()
                                if "\nService:" in action_text:
                                    action_text = action_text.split("\nService:")[0].strip()
                                if "\nComponent:" in action_text:
                                    action_text = action_text.split("\nComponent:")[0].strip()
                        else:
                            action_text = content

                    step = {
                        "step_id": (
                            metadata.get("step_id")
                            if isinstance(metadata, dict)
                            else f"chunk-{row[0]}"
                        ),
                        "runbook_id": row[7]
                        or (metadata.get("runbook_id") if isinstance(metadata, dict) else None),
                        "condition": (
                            metadata.get("condition")
                            if isinstance(metadata, dict)
                            else "Step applies"
                        ),
                        "action": action_text,
                        "expected_outcome": (
                            metadata.get("expected_outcome") if isinstance(metadata, dict) else None
                        ),
                        "rollback": (
                            metadata.get("rollback") if isinstance(metadata, dict) else None
                        ),
                        "service": metadata.get("service") if isinstance(metadata, dict) else None,
                        "component": (
                            metadata.get("component") if isinstance(metadata, dict) else None
                        ),
                        "runbook_title": row[6],
                        "runbook_document_id": str(row[1]),
                        "chunk_id": str(row[0]),
                        "document_id": str(row[1]),
                    }
                    if len(row) > 5:
                        similarity = float(row[5]) if row[5] is not None else None
                        # Validate similarity score - 1.0 is suspicious (perfect match)
                        if similarity is not None and similarity >= 0.999:
                            logger.warning(
                                f"Suspicious similarity score {similarity} for chunk {row[0]} - "
                                f"perfect matches (>=0.999) are rare and may indicate an issue"
                            )
                            # Cap at 0.99 to avoid misleading 100% scores
                            similarity = min(similarity, 0.99)
                        step["similarity_score"] = similarity
                    steps.append(step)

            logger.info(f"Retrieved {len(steps)} runbook chunks for document_ids: {document_ids}")
            return steps

        finally:
            cur.close()


def retrieve_close_notes_from_signatures(
    incident_signature_ids: Optional[List[str]] = None, limit: int = 10
) -> List[Dict]:
    """
    Retrieve close_notes from incident signatures.

    This retrieves resolution notes/close notes from historical incidents
    that match the incident signatures. These notes provide valuable context
    about how similar incidents were resolved.

    Args:
        incident_signature_ids: List of incident_signature_id values from triage output (normalized to strings)
        limit: Maximum number of close_notes to return (normalized to int)

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
    # Normalize and validate parameters
    # Note: incident_signature_ids are strings (not UUIDs), so we just validate they're strings
    if incident_signature_ids:
        incident_signature_ids = [
            str(id_val).strip()
            for id_val in incident_signature_ids
            if id_val and str(id_val).strip()
        ]
    else:
        incident_signature_ids = []

    limit = _normalize_limit(limit, default=10)

    if not incident_signature_ids:
        return []

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Safety check: ensure we have valid IDs (should already be validated, but double-check)
            if not incident_signature_ids or len(incident_signature_ids) == 0:
                logger.warning("Empty incident_signature_ids list, returning empty results")
                return []

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
                    close_notes_list.append(
                        {
                            "incident_signature_id": row["incident_signature_id"],
                            "close_notes": row["close_notes"],
                            "failure_type": row["failure_type"],
                            "error_class": row["error_class"],
                            "match_count": row["match_count"],
                        }
                    )
                else:
                    close_notes_list.append(
                        {
                            "incident_signature_id": row[0],
                            "close_notes": row[1],
                            "failure_type": row[2],
                            "error_class": row[3],
                            "match_count": row[4],
                        }
                    )

            logger.debug(
                f"Retrieved {len(close_notes_list)} close_notes "
                f"for signature_ids: {incident_signature_ids}"
            )
            return close_notes_list

        finally:
            cur.close()


def retrieve_historical_resolutions(
    incident_signature_ids: Optional[List[str]] = None, limit: int = 10
) -> List[Dict]:
    """
    Retrieve historical resolutions from incidents that match incident signatures.

    Per architecture: Historical resolutions are stored in incidents.resolution_output.
    We find incidents that were resolved using steps referenced by the incident signatures.

    Args:
        incident_signature_ids: List of incident_signature_id values from triage output (normalized to strings)
        limit: Maximum number of historical resolutions to return (normalized to int)

    Returns:
        List of historical resolution records with success indicators
    """
    # Normalize and validate parameters
    # Note: incident_signature_ids are strings (not UUIDs), so we just validate they're strings
    if incident_signature_ids:
        incident_signature_ids = [
            str(id_val).strip()
            for id_val in incident_signature_ids
            if id_val and str(id_val).strip()
        ]
    else:
        incident_signature_ids = []

    limit = _normalize_limit(limit, default=10)

    if not incident_signature_ids:
        return []

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
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
                    triage_output = (
                        row["triage_output"] if isinstance(row["triage_output"], dict) else {}
                    )
                    resolution_output = (
                        row["resolution_output"]
                        if isinstance(row["resolution_output"], dict)
                        else {}
                    )

                    # Determine success: accepted = successful, proposed but not accepted = partial
                    is_successful = row["resolution_accepted_at"] is not None
                    rollback_triggered = row["rollback_status"] in [
                        "initiated",
                        "in_progress",
                        "completed",
                    ]

                    historical_resolutions.append(
                        {
                            "incident_id": str(row["id"]),
                            "alert_id": row["alert_id"],
                            "triage_output": triage_output,
                            "resolution_output": resolution_output,
                            "resolution_evidence": row["resolution_evidence"],
                            "resolution_proposed_at": (
                                row["resolution_proposed_at"].isoformat()
                                if row["resolution_proposed_at"]
                                else None
                            ),
                            "resolution_accepted_at": (
                                row["resolution_accepted_at"].isoformat()
                                if row["resolution_accepted_at"]
                                else None
                            ),
                            "is_successful": is_successful,
                            "rollback_triggered": rollback_triggered,
                            "rollback_status": row["rollback_status"],
                            "created_at": (
                                row["created_at"].isoformat() if row["created_at"] else None
                            ),
                        }
                    )
                else:
                    # Handle tuple result
                    triage_output = row[2] if isinstance(row[2], dict) else {}
                    resolution_output = row[3] if isinstance(row[3], dict) else {}

                    is_successful = row[6] is not None
                    rollback_triggered = row[7] in ["initiated", "in_progress", "completed"]

                    historical_resolutions.append(
                        {
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
                        }
                    )

            logger.debug(
                f"Retrieved {len(historical_resolutions)} historical resolutions "
                f"for signature_ids: {incident_signature_ids}"
            )
            return historical_resolutions

        finally:
            cur.close()


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

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
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
                return {
                    step_id: {
                        "total_uses": 0,
                        "successful_uses": 0,
                        "success_rate": 0.5,
                        "last_used": None,
                    }
                    for step_id in step_ids
                }

            # Safety check: ensure we have valid chunk_ids
            if not all_chunk_ids or len(all_chunk_ids) == 0:
                logger.warning("Empty all_chunk_ids list, returning empty statistics")
                return {}

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
            stats = {
                step_id: {"total_uses": 0, "successful_uses": 0, "last_used": None}
                for step_id in step_ids
            }

            for row in rows:
                if isinstance(row, dict):
                    resolution_output = (
                        row["resolution_output"]
                        if isinstance(row["resolution_output"], dict)
                        else {}
                    )
                    is_successful = row["resolution_accepted_at"] is not None
                    proposed_at = row["resolution_proposed_at"]
                else:
                    resolution_output = row[0] if isinstance(row[0], dict) else {}
                    is_successful = row[1] is not None
                    proposed_at = row[2]

                # Get provenance chunk_ids from this resolution
                provenance = resolution_output.get("provenance", [])
                prov_chunk_ids = [
                    p.get("chunk_id")
                    for p in provenance
                    if isinstance(p, dict) and p.get("chunk_id")
                ]

                # Check which step_ids are referenced via their chunk_ids
                for step_id, chunk_ids in step_to_chunks.items():
                    if any(cid in prov_chunk_ids for cid in chunk_ids):
                        stats[step_id]["total_uses"] += 1
                        if is_successful:
                            stats[step_id]["successful_uses"] += 1
                        if proposed_at and (
                            stats[step_id]["last_used"] is None
                            or proposed_at > stats[step_id]["last_used"]
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
