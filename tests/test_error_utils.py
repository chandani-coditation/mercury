"""Unit tests for error utility functions."""

import pytest
from ai_service.api.error_utils import format_user_friendly_error


class TestErrorUtils:
    """Test error formatting utilities."""

    def test_format_string_error(self):
        """Test formatting a string error."""
        error = "Something went wrong"
        result = format_user_friendly_error(error)
        assert "Something went wrong" in result
        assert "Hint:" in result

    def test_format_exception_error(self):
        """Test formatting an exception error."""
        error = ValueError("Invalid input")
        result = format_user_friendly_error(error)
        assert "Invalid input" in result
        assert "Hint:" in result

    def test_format_error_with_validation_type(self):
        """Test formatting error with validation type."""
        error = "Invalid field"
        result = format_user_friendly_error(error, error_type="validation")
        assert "Invalid field" in result
        assert "check your input data" in result.lower()

    def test_format_error_with_not_found_type(self):
        """Test formatting error with not_found type."""
        error = "Resource not found"
        result = format_user_friendly_error(error, error_type="not_found")
        assert "Resource not found" in result
        assert "may not exist" in result.lower()

    def test_format_error_with_openai_api_key(self):
        """Test formatting error related to OpenAI API key."""
        error = "OpenAI API key authentication failed"
        result = format_user_friendly_error(error)
        assert "OPENAI_API_KEY" in result
        assert "restart" in result.lower()

    def test_format_error_with_rate_limit(self):
        """Test formatting error related to rate limiting."""
        error = "Rate limit exceeded"
        result = format_user_friendly_error(error)
        assert "rate limit" in result.lower() or "429" in result
        assert "retry" in result.lower()

    def test_format_error_with_database_connection(self):
        """Test formatting error related to database connection."""
        error = "Could not connect to server"
        result = format_user_friendly_error(error)
        assert "PostgreSQL" in result or "POSTGRES" in result
        assert "running" in result.lower()

    def test_format_error_with_timeout(self):
        """Test formatting error related to timeout."""
        error = "Request timeout"
        result = format_user_friendly_error(error)
        assert "timeout" in result.lower()
        assert "try again" in result.lower() or "retry" in result.lower()

    def test_format_error_with_incident_not_found(self):
        """Test formatting error related to incident not found."""
        error = "Incident not found"
        result = format_user_friendly_error(error)
        assert "incident" in result.lower()
        assert "verify" in result.lower() or "correct" in result.lower()

    def test_format_error_with_triage_required(self):
        """Test formatting error related to triage requirement."""
        error = "Triage required first"
        result = format_user_friendly_error(error)
        assert "triage" in result.lower()
        assert "first" in result.lower()

    def test_format_empty_error(self):
        """Test formatting an empty error."""
        error = ""
        result = format_user_friendly_error(error)
        assert "unexpected error" in result.lower() or "error occurred" in result.lower()
