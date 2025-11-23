"""Utility helpers for formatting user-friendly API error messages."""
from typing import List


def format_user_friendly_error(error: Exception) -> str:
    """
    Create an actionable error message for API responses.

    Args:
        error: Exception that occurred

    Returns:
        Human-friendly error message with optional hints
    """
    message = str(error) if error else "Unknown error"
    lower = message.lower()
    hints: List[str] = []

    if "openai" in lower and "api key" in lower:
        hints.append("Verify OPENAI_API_KEY is set and restart the AI service.")

    if "rate limit" in lower or "429" in lower:
        hints.append("Wait a few seconds before retrying or reduce concurrent requests.")

    if "no historical data" in lower or "no matching evidence" in lower:
        hints.append("Ingest relevant incidents/runbooks or adjust retrieval filters before retrying.")

    if "could not connect to server" in lower or "connection refused" in lower:
        hints.append("Ensure PostgreSQL is running and POSTGRES_HOST/PORT are correct.")

    if "timeout" in lower:
        hints.append("Try again shortly or increase timeout settings if the workload is large.")

    if hints:
        hint_text = " ".join(hints)
        return f"{message} Hint: {hint_text}"

    return f"{message} If the issue persists, retry or check the service logs for more details."

