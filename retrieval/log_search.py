"""Search and retrieval for historical error logs."""

import time
from typing import List, Dict, Optional
from db.connection import get_db_connection_context
from ingestion.embeddings import embed_text
from ai_service.core import get_logger

logger = get_logger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def search_similar_logs(
    query_logs: List[Dict],
    limit: int = 10,
    vector_weight: float = 0.7,
    fulltext_weight: float = 0.3,
    rrf_k: int = 60,
    hostname_filter: Optional[str] = None,
    severity_filter: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Search for similar historical logs using hybrid search (vector + full-text).
    
    This uses the current ticket's error logs to find similar historical logs
    from previous tickets, helping identify patterns and resolutions.
    
    Args:
        query_logs: Current ticket's error logs (from InfluxDB)
        limit: Maximum number of similar logs to return
        vector_weight: Weight for vector search (0-1)
        fulltext_weight: Weight for full-text search (0-1)
        rrf_k: RRF (Reciprocal Rank Fusion) parameter
        hostname_filter: Optional hostname to filter by
        severity_filter: Optional list of severities (e.g., ['error', 'critical'])
        
    Returns:
        List of similar historical log dictionaries with scores
    """
    if not query_logs:
        logger.warning("No query logs provided for similarity search")
        return []
    
    start_time = time.time()
    
    # Combine all query logs into a single query text
    # Format: [severity1] app1 host1: message1 | [severity2] app2 host2: message2
    query_parts = []
    for log in query_logs[:5]:  # Use top 5 error logs
        severity = log.get("severity", "").upper()
        appname = log.get("appname", "")
        hostname = log.get("hostname", "")
        message = log.get("value", log.get("log_message", ""))
        
        if severity and message:
            part = f"[{severity}] {appname} {hostname}: {message}"
            query_parts.append(part)
    
    if not query_parts:
        logger.warning("No valid log messages to search")
        return []
    
    query_text = " | ".join(query_parts)
    
    # Generate embedding for query
    try:
        query_embedding = embed_text(query_text, model=DEFAULT_EMBEDDING_MODEL)
        if query_embedding is None:
            logger.error("Failed to generate embedding for log query")
            return []
        
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}", exc_info=True)
        return []
    
    # Build filter clause
    filter_conditions = []
    filter_params = []
    
    if hostname_filter:
        filter_conditions.append("hostname = %s")
        filter_params.append(hostname_filter)
    
    if severity_filter:
        placeholders = ",".join(["%s"] * len(severity_filter))
        filter_conditions.append(f"severity IN ({placeholders})")
        filter_params.extend(severity_filter)
    
    filter_clause = ""
    if filter_conditions:
        filter_clause = "AND " + " AND ".join(filter_conditions)
    
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        
        try:
            # Hybrid search query using RRF
            query = f"""
            WITH vector_results AS (
                SELECT 
                    id,
                    ticket_id,
                    log_timestamp,
                    hostname,
                    severity,
                    appname,
                    log_message,
                    metadata,
                    incident_id,
                    1 - (embedding <=> %s::vector) as vector_score,
                    ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) as vector_rank
                FROM historical_logs
                WHERE embedding IS NOT NULL
                {filter_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            ),
            fulltext_results AS (
                SELECT 
                    id,
                    ticket_id,
                    log_timestamp,
                    hostname,
                    severity,
                    appname,
                    log_message,
                    metadata,
                    incident_id,
                    ts_rank(tsv, plainto_tsquery('english', %s)) as fulltext_score,
                    ROW_NUMBER() OVER (ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC) as fulltext_rank
                FROM historical_logs
                WHERE tsv IS NOT NULL
                AND length(plainto_tsquery('english', %s)::text) > 0
                AND tsv @@ plainto_tsquery('english', %s)
                {filter_clause}
                ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC
                LIMIT %s
            ),
            combined_results AS (
                SELECT 
                    COALESCE(v.id, f.id) as id,
                    COALESCE(v.ticket_id, f.ticket_id) as ticket_id,
                    COALESCE(v.log_timestamp, f.log_timestamp) as log_timestamp,
                    COALESCE(v.hostname, f.hostname) as hostname,
                    COALESCE(v.severity, f.severity) as severity,
                    COALESCE(v.appname, f.appname) as appname,
                    COALESCE(v.log_message, f.log_message) as log_message,
                    COALESCE(v.metadata, f.metadata) as metadata,
                    COALESCE(v.incident_id, f.incident_id) as incident_id,
                    COALESCE(v.vector_score, 0.0) as vector_score,
                    COALESCE(f.fulltext_score, 0.0) as fulltext_score,
                    COALESCE(v.vector_rank, 999) as vector_rank,
                    COALESCE(f.fulltext_rank, 999) as fulltext_rank
                FROM vector_results v
                FULL OUTER JOIN fulltext_results f ON v.id = f.id
            )
            SELECT 
                id,
                ticket_id,
                log_timestamp,
                hostname,
                severity,
                appname,
                log_message,
                metadata,
                incident_id,
                vector_score,
                fulltext_score,
                -- RRF score calculation
                (1.0 / (%s + vector_rank)) * %s + (1.0 / (%s + fulltext_rank)) * %s as rrf_score
            FROM combined_results
            ORDER BY rrf_score DESC
            LIMIT %s
            """
            
            # Build parameter list for query
            # Vector search params (3x: embedding_str for vector search)
            params = [embedding_str, embedding_str, embedding_str]
            params.extend(filter_params)  # Add filter params for vector search
            params.append(limit * 2)  # Vector search limit
            
            # Fulltext search params (5x: query_text)
            params.extend([query_text] * 5)
            params.extend(filter_params)  # Add filter params for fulltext search
            params.append(limit * 2)  # Fulltext search limit
            
            # RRF params
            params.extend([rrf_k, vector_weight, rrf_k, fulltext_weight])
            params.append(limit)  # Final result limit
            
            cur.execute(query, params)
            results = cur.fetchall()
            
            # Format results
            similar_logs = []
            for row in results:
                log_dict = {
                    "log_id": str(row[0]) if row[0] else None,
                    "ticket_id": row[1],
                    "log_timestamp": row[2].isoformat() if row[2] else None,
                    "hostname": row[3],
                    "severity": row[4],
                    "appname": row[5],
                    "log_message": row[6],
                    "metadata": row[7] if isinstance(row[7], dict) else {},
                    "incident_id": str(row[8]) if row[8] else None,
                    "vector_score": float(row[9]) if row[9] else 0.0,
                    "fulltext_score": float(row[10]) if row[10] else 0.0,
                    "rrf_score": float(row[11]) if row[11] else 0.0,
                }
                similar_logs.append(log_dict)
            
            elapsed = time.time() - start_time
            logger.info(
                f"Found {len(similar_logs)} similar historical logs in {elapsed:.3f}s "
                f"(query: {len(query_text)} chars, {len(query_logs)} logs)"
            )
            
            return similar_logs
            
        except Exception as e:
            logger.error(f"Failed to search similar logs: {e}", exc_info=True)
            return []
        finally:
            cur.close()


def get_logs_by_ticket_id(ticket_id: str, limit: int = 50) -> List[Dict]:
    """
    Retrieve all historical logs for a specific ticket.
    
    Args:
        ticket_id: Ticket/incident ID (e.g., INC6052852)
        limit: Maximum number of logs to return
        
    Returns:
        List of log dictionaries
    """
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        
        try:
            cur.execute(
                """
                SELECT 
                    id, ticket_id, log_timestamp, hostname, severity, appname,
                    log_message, metadata, incident_id
                FROM historical_logs
                WHERE ticket_id = %s
                ORDER BY log_timestamp DESC
                LIMIT %s
                """,
                (ticket_id, limit),
            )
            
            results = cur.fetchall()
            
            logs = []
            for row in results:
                log_dict = {
                    "log_id": str(row[0]) if row[0] else None,
                    "ticket_id": row[1],
                    "log_timestamp": row[2].isoformat() if row[2] else None,
                    "hostname": row[3],
                    "severity": row[4],
                    "appname": row[5],
                    "log_message": row[6],
                    "metadata": row[7] if isinstance(row[7], dict) else {},
                    "incident_id": str(row[8]) if row[8] else None,
                }
                logs.append(log_dict)
            
            return logs
            
        except Exception as e:
            logger.error(f"Failed to get logs for ticket {ticket_id}: {e}", exc_info=True)
            return []
        finally:
            cur.close()


def get_log_statistics() -> Dict:
    """
    Get statistics about historical logs in the database.
    
    Returns:
        Dictionary with statistics (total_logs, unique_tickets, severities, etc.)
    """
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        
        try:
            # Get basic stats
            cur.execute(
                """
                SELECT 
                    COUNT(*) as total_logs,
                    COUNT(DISTINCT ticket_id) as unique_tickets,
                    COUNT(DISTINCT hostname) as unique_hosts,
                    MIN(log_timestamp) as oldest_log,
                    MAX(log_timestamp) as newest_log
                FROM historical_logs
                """
            )
            row = cur.fetchone()
            
            stats = {
                "total_logs": int(row[0]) if row[0] else 0,
                "unique_tickets": int(row[1]) if row[1] else 0,
                "unique_hosts": int(row[2]) if row[2] else 0,
                "oldest_log": row[3].isoformat() if row[3] else None,
                "newest_log": row[4].isoformat() if row[4] else None,
            }
            
            # Get severity breakdown
            cur.execute(
                """
                SELECT severity, COUNT(*) as count
                FROM historical_logs
                GROUP BY severity
                ORDER BY count DESC
                """
            )
            
            severity_counts = {}
            for row in cur.fetchall():
                severity_counts[row[0]] = int(row[1])
            
            stats["severity_counts"] = severity_counts
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get log statistics: {e}", exc_info=True)
            return {}
        finally:
            cur.close()
