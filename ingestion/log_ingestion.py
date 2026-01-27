"""Ingestion module for storing historical error logs in the database."""

import json
from typing import List, Dict, Optional
from datetime import datetime
from db.connection import get_db_connection_context
from ingestion.embeddings import embed_text, embed_texts_batch
from ai_service.core import get_logger

logger = get_logger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _create_log_embedding_text(log: Dict) -> str:
    """
    Create embedding text for a log entry.
    
    This combines key fields into a single text for embedding generation.
    Format: [severity] [appname] [hostname]: message
    
    Args:
        log: Log dictionary with fields (value, severity, hostname, appname, etc.)
        
    Returns:
        Text suitable for embedding generation
    """
    severity = log.get("severity", "unknown").upper()
    appname = log.get("appname", "")
    hostname = log.get("hostname", "")
    message = log.get("value", log.get("log_message", ""))
    
    # Format: [ERROR] nginx web-server-01: Database connection timeout
    parts = []
    if severity:
        parts.append(f"[{severity}]")
    if appname:
        parts.append(appname)
    if hostname:
        parts.append(hostname)
    parts.append(":")
    parts.append(message)
    
    return " ".join(parts)


def insert_historical_log(
    log: Dict,
    ticket_id: str,
    incident_id: Optional[str] = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Optional[str]:
    """
    Insert a single historical log into the database.
    
    Args:
        log: Log dictionary from InfluxDB (parsed by LogParser)
        ticket_id: Ticket/incident ID (e.g., INC6052852)
        incident_id: Optional incident UUID from incidents table
        embedding_model: Model to use for embedding generation
        
    Returns:
        Log ID (UUID as string) if successful, None if skipped (duplicate)
    """
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        
        try:
            # Extract log fields
            log_timestamp = log.get("timestamp")
            if isinstance(log_timestamp, str):
                # Parse ISO format
                try:
                    log_timestamp = datetime.fromisoformat(log_timestamp.replace("Z", "+00:00"))
                except Exception:
                    log_timestamp = datetime.utcnow()
            elif not isinstance(log_timestamp, datetime):
                log_timestamp = datetime.utcnow()
            
            hostname = log.get("hostname", "")
            severity = log.get("severity", "unknown")
            appname = log.get("appname", "")
            facility = log.get("facility", "")
            log_message = log.get("value", log.get("log_message", ""))
            
            # Build metadata
            metadata = {
                "ticket_id": ticket_id,
                "level": log.get("level", ""),
                "matched_pattern": log.get("matched_pattern", ""),
                "is_important": log.get("is_important", True),
                "measurement": log.get("measurement", ""),
            }
            
            # Create embedding text
            embedding_text = _create_log_embedding_text(log)
            
            # Generate embedding
            embedding = embed_text(embedding_text, model=embedding_model)
            if embedding is None:
                logger.warning(f"Failed to generate embedding for log from ticket {ticket_id}")
                return None
            
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            
            # Create full-text search text (prioritize message, then context)
            tsv_text = f"{log_message} {appname} {hostname} {severity}"
            
            # Insert log (skip if duplicate)
            cur.execute(
                """
                INSERT INTO historical_logs (
                    ticket_id, log_timestamp, hostname, severity, appname, facility,
                    log_message, embedding, tsv, metadata, incident_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s), %s::jsonb, %s)
                ON CONFLICT (ticket_id, log_timestamp, log_message) DO NOTHING
                RETURNING id
                """,
                (
                    ticket_id,
                    log_timestamp,
                    hostname,
                    severity,
                    appname,
                    facility,
                    log_message,
                    embedding_str,
                    tsv_text,
                    json.dumps(metadata),
                    incident_id,
                ),
            )
            
            result = cur.fetchone()
            conn.commit()
            
            if result:
                log_id = str(result[0]) if hasattr(result, "__getitem__") else str(result["id"])
                logger.debug(f"Inserted historical log {log_id} for ticket {ticket_id}")
                return log_id
            else:
                logger.debug(f"Skipped duplicate log for ticket {ticket_id}")
                return None
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to insert historical log for ticket {ticket_id}: {e}", exc_info=True)
            raise
        finally:
            cur.close()


def insert_historical_logs_batch(
    logs: List[Dict],
    ticket_id: str,
    incident_id: Optional[str] = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 50,
) -> int:
    """
    Insert multiple historical logs in batch for better performance.
    
    Args:
        logs: List of log dictionaries from InfluxDB (parsed by LogParser)
        ticket_id: Ticket/incident ID (e.g., INC6052852)
        incident_id: Optional incident UUID from incidents table
        embedding_model: Model to use for embedding generation
        batch_size: Number of logs to process in each embedding batch
        
    Returns:
        Number of logs successfully inserted (excluding duplicates)
    """
    if not logs:
        return 0
    
    logger.info(f"Batch inserting {len(logs)} historical logs for ticket {ticket_id}")
    
    # Prepare embedding texts for all logs
    embedding_texts = [_create_log_embedding_text(log) for log in logs]
    
    # Generate embeddings in batches
    try:
        embeddings = embed_texts_batch(embedding_texts, model=embedding_model, batch_size=batch_size)
    except Exception as e:
        logger.error(f"Failed to generate embeddings for logs: {e}", exc_info=True)
        return 0
    
    if not embeddings or len(embeddings) != len(logs):
        logger.error(
            f"Embedding generation failed: expected {len(logs)} embeddings, "
            f"got {len(embeddings) if embeddings else 0}"
        )
        return 0
    
    # Insert logs
    inserted_count = 0
    
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        
        try:
            for log, embedding in zip(logs, embeddings):
                # Extract log fields
                log_timestamp = log.get("timestamp")
                if isinstance(log_timestamp, str):
                    try:
                        log_timestamp = datetime.fromisoformat(log_timestamp.replace("Z", "+00:00"))
                    except Exception:
                        log_timestamp = datetime.utcnow()
                elif not isinstance(log_timestamp, datetime):
                    log_timestamp = datetime.utcnow()
                
                hostname = log.get("hostname", "")
                severity = log.get("severity", "unknown")
                appname = log.get("appname", "")
                facility = log.get("facility", "")
                log_message = log.get("value", log.get("log_message", ""))
                
                # Build metadata
                metadata = {
                    "ticket_id": ticket_id,
                    "level": log.get("level", ""),
                    "matched_pattern": log.get("matched_pattern", ""),
                    "is_important": log.get("is_important", True),
                    "measurement": log.get("measurement", ""),
                }
                
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                tsv_text = f"{log_message} {appname} {hostname} {severity}"
                
                # Insert log (skip if duplicate)
                cur.execute(
                    """
                    INSERT INTO historical_logs (
                        ticket_id, log_timestamp, hostname, severity, appname, facility,
                        log_message, embedding, tsv, metadata, incident_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s), %s::jsonb, %s)
                    ON CONFLICT (ticket_id, log_timestamp, log_message) DO NOTHING
                    RETURNING id
                    """,
                    (
                        ticket_id,
                        log_timestamp,
                        hostname,
                        severity,
                        appname,
                        facility,
                        log_message,
                        embedding_str,
                        tsv_text,
                        json.dumps(metadata),
                        incident_id,
                    ),
                )
                
                result = cur.fetchone()
                if result:
                    inserted_count += 1
            
            conn.commit()
            logger.info(f"Inserted {inserted_count} new historical logs for ticket {ticket_id} (skipped {len(logs) - inserted_count} duplicates)")
            return inserted_count
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to batch insert historical logs: {e}", exc_info=True)
            raise
        finally:
            cur.close()


def ingest_logs_for_ticket(
    ticket_id: str,
    ticket_creation_date: datetime,
    incident_id: Optional[str] = None,
    window_minutes: Optional[int] = None,
) -> int:
    """
    Fetch logs for a ticket from InfluxDB and store them as historical logs.
    
    This is the main entry point for ingesting logs after triage.
    
    Args:
        ticket_id: Ticket/incident ID (e.g., INC6052852)
        ticket_creation_date: Ticket creation datetime (UTC)
        incident_id: Optional incident UUID from incidents table
        window_minutes: Time window in minutes before ticket creation
        
    Returns:
        Number of logs successfully inserted
    """
    from ai_service.utils.log_processing import fetch_ticket_logs
    
    # Fetch logs from InfluxDB
    logs = fetch_ticket_logs(
        ticket_id=ticket_id,
        ticket_creation_date=ticket_creation_date,
        window_minutes=window_minutes,
    )
    
    if not logs:
        logger.info(f"No logs to ingest for ticket {ticket_id}")
        return 0
    
    # Insert logs in batch
    inserted_count = insert_historical_logs_batch(
        logs=logs,
        ticket_id=ticket_id,
        incident_id=incident_id,
    )
    
    return inserted_count
