"""Functions to retrieve original incident descriptions from documents table."""

from typing import List, Dict, Optional
from db.connection import get_db_connection_context
from ai_service.core import get_logger

logger = get_logger(__name__)


def get_incident_descriptions(incident_ids: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Get original incident titles and descriptions from documents table.

    Args:
        incident_ids: List of ServiceNow incident IDs (e.g., ["INC6036026", "INC6035934"])

    Returns:
        Dictionary mapping incident_id to {title, description}
        Example: {"INC6036026": {"title": "...", "description": "..."}}
    """
    if not incident_ids:
        return {}

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Safety check: ensure we have valid IDs
            if not incident_ids or len(incident_ids) == 0:
                logger.warning("Empty incident_ids list, returning empty results")
                return {}
            
            # Query documents table for incidents matching the incident_ids in tags
            placeholders = ",".join(["%s"] * len(incident_ids))

            query = f"""
            SELECT 
                d.title,
                d.content,
                d.tags->>'ticket_id' as incident_id,
                d.tags->>'incident_id' as alt_incident_id
            FROM documents d
            WHERE d.doc_type = 'incident'
            AND (
                d.tags->>'ticket_id' IN ({placeholders})
                OR d.tags->>'incident_id' IN ({placeholders})
                OR d.tags->>'canonical_incident_key' IN ({placeholders})
            )
            """

            # Execute with incident_ids (need to pass twice for the OR conditions)
            cur.execute(query, tuple(incident_ids) * 3)
            rows = cur.fetchall()

            result = {}
            for row in rows:
                if isinstance(row, dict):
                    incident_id = row.get("incident_id") or row.get("alt_incident_id")
                    title = row.get("title", "")
                    description = row.get("content", "")
                else:
                    incident_id = row[2] or row[3]
                    title = row[0] or ""
                    description = row[1] or ""

                if incident_id and incident_id in incident_ids:
                    result[incident_id] = {"title": title, "description": description}

            logger.debug(f"Retrieved descriptions for {len(result)}/{len(incident_ids)} incidents")
            return result

        finally:
            cur.close()
