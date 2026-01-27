"""API endpoints for managing documents (runbooks, incidents, etc.)."""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from db.connection import get_db_connection_context
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/documents")
def list_documents(
    doc_type: Optional[str] = Query(
        None, description="Filter by document type (e.g., 'runbook', 'incident')"
    ),
    service: Optional[str] = Query(None, description="Filter by service"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List documents (runbooks, incidents, etc.).

    Query Parameters:
    - doc_type: Filter by document type (e.g., 'runbook')
    - service: Filter by service
    - limit: Maximum number of documents to return (1-200, default: 50)
    - offset: Number of documents to skip (default: 0)

    Returns:
    List of documents with metadata
    """
    try:
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            # Build query
            conditions = []
            params = []

            if doc_type:
                conditions.append("doc_type = %s")
                params.append(doc_type)

            if service:
                conditions.append("service = %s")
                params.append(service)

            where_clause = (
                f"WHERE {' AND '.join(conditions)}" if conditions else ""
            )

            # Get total count
            count_query = f"SELECT COUNT(*) FROM documents {where_clause}"
            cur.execute(count_query, params)
            total = cur.fetchone()["count"]

            # Get documents
            query = f"""
                SELECT id, doc_type, service, component, title, content, tags, 
                       last_reviewed_at, created_at
                FROM documents
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            cur.execute(query, params)
            rows = cur.fetchall()

            documents = [dict(row) for row in rows]

            return {
                "documents": documents,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
    except Exception as e:
        logger.error(f"Failed to list documents: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list documents: {str(e)}"
        )


@router.get("/documents/{document_id}")
def get_document(document_id: str):
    """
    Get a single document by ID.

    Returns:
    Document details
    """
    try:
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT id, doc_type, service, component, title, content, tags, last_reviewed_at, created_at FROM documents WHERE id = %s",
                (document_id,),
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Document not found")

            return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get document {document_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get document: {str(e)}"
        )


@router.put("/documents/{document_id}")
def update_document(
    document_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    service: Optional[str] = None,
    component: Optional[str] = None,
    tags: Optional[dict] = None,
):
    """
    Update a document.

    Request Body (all fields optional):
    - title: Document title
    - content: Document content
    - service: Service name
    - component: Component name
    - tags: Tags dictionary
    """
    try:
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            # Check if document exists
            cur.execute("SELECT id FROM documents WHERE id = %s", (document_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Document not found")

            # Build update query dynamically
            updates = []
            params = []

            if title is not None:
                updates.append("title = %s")
                params.append(title)

            if content is not None:
                updates.append("content = %s")
                params.append(content)

            if service is not None:
                updates.append("service = %s")
                params.append(service)

            if component is not None:
                updates.append("component = %s")
                params.append(component)

            if tags is not None:
                import json

                updates.append("tags = %s::jsonb")
                params.append(json.dumps(tags))

            if not updates:
                raise HTTPException(
                    status_code=400, detail="No fields to update"
                )

            updates.append("last_reviewed_at = now()")
            params.append(document_id)

            query = f"UPDATE documents SET {', '.join(updates)} WHERE id = %s"
            cur.execute(query, params)
            conn.commit()

            logger.info(f"Document updated: {document_id}")

            # Return updated document
            cur.execute(
                "SELECT id, doc_type, service, component, title, content, tags, last_reviewed_at, created_at FROM documents WHERE id = %s",
                (document_id,),
            )
            return dict(cur.fetchone())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update document {document_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to update document: {str(e)}"
        )


@router.delete("/documents/{document_id}")
def delete_document(document_id: str):
    """
    Delete a document.

    Note: This will also delete associated chunks (CASCADE).
    """
    try:
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            # Check if document exists
            cur.execute("SELECT id FROM documents WHERE id = %s", (document_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Document not found")

            cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            conn.commit()

            logger.info(f"Document deleted: {document_id}")

            return {"status": "ok", "message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete document {document_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to delete document: {str(e)}"
        )
