"""Utilities for processing and formatting ticket logs from InfluxDB.

This module handles:
1. Fetching logs from InfluxDB for new tickets
2. Formatting logs as context chunks for LLM
3. Searching for similar historical logs from previous tickets
4. Combining current and historical logs for enriched triage context
"""

from datetime import datetime
from typing import Optional, List, Dict
from ai_service.core import get_logger
from retrieval.influxdb_client import get_influxdb_client

logger = get_logger(__name__)


def fetch_ticket_logs(
    ticket_id: str,
    ticket_creation_date: datetime,
    window_minutes: Optional[int] = None,
) -> Optional[List[Dict]]:
    """
    Fetch and parse logs from InfluxDB for a specific ticket.

    This function fetches logs from InfluxDB within a time window before the ticket
    creation time, parses them using the same LogParser used for ingestion, and
    filters to keep only error/important logs.

    Args:
        ticket_id: Ticket/incident ID (e.g., INC6052852)
        ticket_creation_date: Ticket creation datetime (UTC)
        window_minutes: Time window in minutes before ticket creation (defaults to env var or 15)

    Returns:
        List of parsed error log dictionaries if successful, None if logs unavailable
        Returns empty list if no error logs found in the time window

    Notes:
        - Gracefully handles errors (returns None if fetch fails)
        - Uses same LogParser as ingestion for consistent filtering
        - Only returns error/important logs (filtered by log_parser)
        - Logs are fetched from: ticket_creation_date - window_minutes to ticket_creation_date
    """
    try:
        influx_client = get_influxdb_client()

        # Check if InfluxDB is configured
        if not influx_client.is_configured():
            logger.debug("InfluxDB not configured - skipping log fetch")
            return None

        logger.info(f"Fetching logs for ticket {ticket_id} created at {ticket_creation_date}")

        # Fetch and parse logs (uses same LogParser as ingestion)
        ticket_logs = influx_client.fetch_and_parse_logs_for_ticket(
            ticket_id=ticket_id,
            ticket_creation_date=ticket_creation_date,
            window_minutes=window_minutes,
            include_warnings=False,  # Only errors, not warnings
        )

        if ticket_logs:
            logger.info(f"Fetched {len(ticket_logs)} error logs for ticket {ticket_id}")
            return ticket_logs
        else:
            logger.info(f"No error logs found for ticket {ticket_id}")
            return []

    except Exception as e:
        logger.warning(
            f"Failed to fetch logs for ticket {ticket_id}: {str(e)}. "
            "Continuing with triage without logs.",
            exc_info=True,
        )
        return None


def format_logs_as_context_chunks(ticket_logs: List[Dict], ticket_id: str) -> List[Dict]:
    """
    Format fetched logs as context chunks for retrieval (like incidents/runbooks).

    This converts parsed log entries into the same format used by incident signatures
    and runbooks, so they can be used as context in triage LLM calls.

    Args:
        ticket_logs: List of parsed log dictionaries from InfluxDB
        ticket_id: Ticket/incident ID

    Returns:
        List of context chunk dictionaries formatted for LLM consumption
    """
    context_chunks = []

    for idx, log in enumerate(ticket_logs):
        # Format log as context chunk (similar to incident/runbook format)
        timestamp = log.get("timestamp", "N/A")
        hostname = log.get("hostname", "unknown")
        severity = log.get("severity", "unknown")
        appname = log.get("appname", "N/A")
        log_message = log.get("value", "")

        # Create formatted content
        content = f"""[Error Log #{idx+1}]
        Timestamp: {timestamp}
        Hostname: {hostname}
        Severity: {severity.upper()}
        Application: {appname}
        Message: {log_message}"""

        # Create context chunk (same structure as incidents/runbooks)
        chunk = {
            "chunk_id": f"ticket_log_{ticket_id}_{idx}",
            "content": content,
            "doc_type": "log",
            "source": "influxdb",
            "metadata": {
                "ticket_id": ticket_id,
                "timestamp": timestamp,
                "hostname": hostname,
                "severity": severity,
                "appname": appname,
            },
        }
        context_chunks.append(chunk)

    logger.debug(
        f"Formatted {len(context_chunks)} log entries as context chunks for ticket {ticket_id}"
    )
    return context_chunks


def parse_ticket_creation_date(date_value: any) -> Optional[datetime]:
    """
    Parse ticket creation date from various formats.

    Handles:
    - datetime objects (returns as-is)
    - ISO format strings (with or without Z suffix)
    - Invalid formats (logs warning and returns None)

    Args:
        date_value: Date value to parse (datetime, str, or other)

    Returns:
        Parsed datetime object or None if parsing fails
    """
    # Already a datetime object
    if isinstance(date_value, datetime):
        return date_value

    # Parse string format
    if isinstance(date_value, str):
        try:
            # Handle ISO format with Z suffix
            date_str = date_value.replace("Z", "+00:00")
            return datetime.fromisoformat(date_str)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not parse ticket_created_date '{date_value}': {e}")
            return None

    # Unsupported type
    logger.warning(f"Unsupported ticket_created_date type: {type(date_value)}")
    return None


def search_similar_historical_logs(
    current_logs: List[Dict], limit: int = 5
) -> Optional[List[Dict]]:
    """
    Search for similar historical logs from previous tickets.

    Uses hybrid search (vector + full-text) to find logs from past incidents
    that are similar to the current ticket's error logs.

    Args:
        current_logs: Current ticket's error logs from InfluxDB
        limit: Maximum number of similar logs to return

    Returns:
        List of similar historical log dictionaries with scores, or None if search fails
    """
    if not current_logs:
        logger.debug("No current logs provided for historical search")
        return None

    try:
        from retrieval.log_search import search_similar_logs

        similar_logs = search_similar_logs(
            query_logs=current_logs,
            limit=limit,
            vector_weight=0.7,
            fulltext_weight=0.3,
        )

        if similar_logs:
            logger.info(f"Found {len(similar_logs)} similar historical logs")
            return similar_logs
        else:
            logger.info("No similar historical logs found")
            return []

    except Exception as e:
        logger.warning(
            f"Failed to search historical logs: {str(e)}. Continuing without historical context.",
            exc_info=True,
        )
        return None


def format_historical_logs_as_context_chunks(
    historical_logs: List[Dict], limit: int = 5
) -> List[Dict]:
    """
    Format historical logs as context chunks for LLM (like incidents/runbooks).

    Args:
        historical_logs: List of historical log dictionaries from database
        limit: Maximum number of logs to format

    Returns:
        List of context chunk dictionaries formatted for LLM consumption
    """
    context_chunks = []

    for idx, log in enumerate(historical_logs[:limit]):
        # Extract fields
        ticket_id = log.get("ticket_id", "UNKNOWN")
        timestamp = log.get("log_timestamp", "N/A")
        hostname = log.get("hostname", "unknown")
        severity = log.get("severity", "unknown")
        appname = log.get("appname", "N/A")
        log_message = log.get("log_message", "")
        rrf_score = log.get("rrf_score", 0.0)

        # Create formatted content
        content = f"""[Historical Log #{idx+1} - Similar Error from {ticket_id}]
Timestamp: {timestamp}
Hostname: {hostname}
Severity: {severity.upper()}
Application: {appname}
Similarity Score: {rrf_score:.3f}
Message: {log_message}"""

        # Create context chunk (same structure as incidents/runbooks/logs)
        chunk = {
            "chunk_id": f"historical_log_{ticket_id}_{idx}",
            "content": content,
            "doc_type": "historical_log",
            "source": "database",
            "metadata": {
                "ticket_id": ticket_id,
                "timestamp": timestamp,
                "hostname": hostname,
                "severity": severity,
                "appname": appname,
                "rrf_score": rrf_score,
                "log_id": log.get("log_id"),
                "incident_id": log.get("incident_id"),
            },
        }
        context_chunks.append(chunk)

    logger.debug(
        f"Formatted {len(context_chunks)} historical logs as context chunks"
    )
    return context_chunks


def process_ticket_logs_for_triage(alert_dict: Dict) -> None:
    """
    Process and add ticket logs to alert context for triage.

    This is the main entry point for integrating InfluxDB logs into triage.
    It orchestrates the entire log processing pipeline:

    1. Extracts ticket_id and ticket_creation_date from alert
    2. Fetches logs from InfluxDB using the same LogParser as ingestion
    3. Formats logs as context chunks (like incidents/runbooks)
    4. Adds logs to alert_dict for use in triage

    Args:
        alert_dict: Alert dictionary to be enriched with logs

    Returns:
        None (modifies alert_dict in place)

    Side Effects:
        - Adds "ticket_log_chunks" to alert_dict (formatted context chunks)
        - Adds "ticket_logs" to alert_dict (raw logs for backward compatibility)
    """
    ticket_id = alert_dict.get("alert_id")  # Use alert_id as ticket_id
    ticket_creation_date = alert_dict.get("ticket_created_date")

    # Skip if ticket_id or ticket_creation_date is missing
    if not ticket_id or not ticket_creation_date:
        logger.debug("Skipping log fetch: ticket_id or ticket_created_date missing")
        return

    # Parse ticket_created_date if it's a string
    parsed_date = parse_ticket_creation_date(ticket_creation_date)
    if not parsed_date:
        logger.warning("Could not parse ticket_created_date - skipping log fetch")
        return

    # Fetch and parse logs (uses same LogParser as ingestion)
    ticket_logs = fetch_ticket_logs(
        ticket_id=ticket_id,
        ticket_creation_date=parsed_date,
        window_minutes=None,  # Will use env var or default to 15
    )

    # Format logs as context chunks for retrieval (like incidents/runbooks)
    if ticket_logs:
        log_chunks = format_logs_as_context_chunks(ticket_logs, ticket_id)

        # Search for similar historical logs from previous tickets
        similar_historical_logs = search_similar_historical_logs(
            current_logs=ticket_logs, limit=5
        )

        # Format historical logs as context chunks
        historical_log_chunks = []
        if similar_historical_logs:
            historical_log_chunks = format_historical_logs_as_context_chunks(
                historical_logs=similar_historical_logs, limit=5
            )
            logger.info(
                f"Added {len(historical_log_chunks)} historical log context chunks"
            )

        # Add to alert_dict so triage agent can use them as context
        alert_dict["ticket_log_chunks"] = log_chunks  # Current ticket logs
        alert_dict["historical_log_chunks"] = (
            historical_log_chunks  # Similar logs from past tickets
        )

        # Also keep raw logs for backward compatibility
        alert_dict["ticket_logs"] = ticket_logs
        alert_dict["similar_historical_logs"] = similar_historical_logs or []

        logger.info(
            f"Added {len(log_chunks)} current log chunks + "
            f"{len(historical_log_chunks)} historical log chunks for triage"
        )
