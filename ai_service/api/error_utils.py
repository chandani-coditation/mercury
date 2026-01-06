"""Utility helpers for formatting user-friendly API error messages."""

from typing import List


def format_user_friendly_error(error: Exception, error_type: str = None) -> str:
    """
    Create a standardized, actionable error message for API responses.
    
    TASK #10: Standardized error message format with consistent structure and helpful hints.
    
    Args:
        error: Exception that occurred
        error_type: Optional error type classification (e.g., "validation", "not_found", "permission_denied")
    
    Returns:
        Human-friendly error message with optional hints in consistent format
    """
    # Get base message
    if isinstance(error, str):
        message = error
    else:
        message = str(error) if error else "Unknown error"
    
    # Standardize message format
    message = message.strip()
    if not message:
        message = "An unexpected error occurred"
    
    lower = message.lower()
    hints: List[str] = []
    
    # Classification-based hints
    if error_type == "validation":
        hints.append("Please check your input data and ensure all required fields are provided correctly.")
    elif error_type == "not_found":
        hints.append("The requested resource may not exist or may have been deleted.")
    elif error_type == "permission_denied" or error_type == "approval_required":
        hints.append("This operation requires approval. Please review and approve the request.")
    
    # Content-based hints (more specific)
    if "openai" in lower and ("api key" in lower or "authentication" in lower):
        hints.append("Verify OPENAI_API_KEY is set and restart the AI service.")
    
    if "rate limit" in lower or "429" in lower:
        hints.append("Wait a few seconds before retrying or reduce concurrent requests.")
    
    if "no historical data" in lower or "no matching evidence" in lower or "no evidence found" in lower:
        hints.append(
            "Ingest relevant incidents/runbooks using: `python scripts/data/ingest_runbooks.py` and `python scripts/data/ingest_servicenow_tickets.py`."
        )
    
    if "could not connect to server" in lower or "connection refused" in lower or "connection" in lower and "failed" in lower:
        hints.append("Ensure PostgreSQL is running and POSTGRES_HOST/PORT are correct.")
    
    if "timeout" in lower:
        hints.append("Try again shortly or increase timeout settings if the workload is large.")
    
    if "embedding" in lower and "failed" in lower:
        hints.append("Check OpenAI API status and ensure embeddings model is accessible.")
    
    if "incident" in lower and ("not found" in lower or "does not exist" in lower):
        hints.append("Verify the incident_id is correct and the incident exists in the database.")
    
    if "triage" in lower and ("required" in lower or "first" in lower):
        hints.append("Please triage the alert first before requesting resolution.")
    
    # Format final message consistently
    if hints:
        hint_text = " ".join(hints)
        return f"{message} 💡 Hint: {hint_text}"
    
    return f"{message} 💡 If the issue persists, retry or check the service logs for more details."
