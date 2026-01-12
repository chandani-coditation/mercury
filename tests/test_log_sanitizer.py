"""Unit tests for log sanitization utilities."""

import pytest
from ai_service.core.log_sanitizer import (
    sanitize_log_message,
    sanitize_dict,
    sanitize_exception_args,
)


class TestLogMessageSanitization:
    """Test log message sanitization."""

    def test_sanitize_openai_api_key(self):
        """Test that OpenAI API keys are redacted."""
        message = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
        sanitized = sanitize_log_message(message)
        assert "sk-***REDACTED***" in sanitized
        assert "1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized

    def test_sanitize_generic_api_key(self):
        """Test that generic API keys are redacted."""
        message = "api_key=abc123def456ghi789jkl012mno345pqr678"
        sanitized = sanitize_log_message(message)
        assert "api_key=***REDACTED***" in sanitized
        assert "abc123def456ghi789jkl012mno345pqr678" not in sanitized

    def test_sanitize_password(self):
        """Test that passwords are redacted."""
        message = "password=mySecretPassword123"
        sanitized = sanitize_log_message(message)
        assert "password=***REDACTED***" in sanitized
        assert "mySecretPassword123" not in sanitized

    def test_sanitize_postgres_password(self):
        """Test that PostgreSQL passwords are redacted."""
        message = "postgres_password=dbpass123"
        sanitized = sanitize_log_message(message)
        assert "postgres_password=***REDACTED***" in sanitized
        assert "dbpass123" not in sanitized

    def test_sanitize_connection_string(self):
        """Test that connection strings with passwords are redacted."""
        message = "postgresql://user:password123@localhost:5432/dbname"
        sanitized = sanitize_log_message(message)
        assert "***REDACTED***:***REDACTED***@" in sanitized
        assert "password123" not in sanitized

    def test_sanitize_token(self):
        """Test that tokens are redacted."""
        message = "token=abc123def456ghi789jkl012mno345pqr678"
        sanitized = sanitize_log_message(message)
        assert "token=***REDACTED***" in sanitized
        assert "abc123def456ghi789jkl012mno345pqr678" not in sanitized

    def test_sanitize_multiple_sensitive_fields(self):
        """Test that multiple sensitive fields are redacted."""
        message = "api_key=abc123 password=secret123 token=xyz789"
        sanitized = sanitize_log_message(message)
        assert "api_key=***REDACTED***" in sanitized
        assert "password=***REDACTED***" in sanitized
        assert "token=***REDACTED***" in sanitized
        assert "abc123" not in sanitized
        assert "secret123" not in sanitized
        assert "xyz789" not in sanitized

    def test_non_sensitive_message_unchanged(self):
        """Test that non-sensitive messages are unchanged."""
        message = "This is a normal log message without sensitive data"
        sanitized = sanitize_log_message(message)
        assert sanitized == message

    def test_empty_message(self):
        """Test that empty messages are handled."""
        message = ""
        sanitized = sanitize_log_message(message)
        assert sanitized == ""


class TestDictSanitization:
    """Test dictionary sanitization."""

    def test_sanitize_dict_with_password(self):
        """Test that dictionary values with sensitive keys are redacted."""
        data = {
            "username": "user123",
            "password": "secret123",
            "api_key": "key123",
        }
        sanitized = sanitize_dict(data)
        assert sanitized["username"] == "user123"
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["api_key"] == "***REDACTED***"

    def test_sanitize_nested_dict(self):
        """Test that nested dictionaries are sanitized."""
        data = {
            "user": {
                "name": "John",
                "password": "secret123",
            },
            "config": {
                "api_key": "key123",
            },
        }
        sanitized = sanitize_dict(data)
        assert sanitized["user"]["name"] == "John"
        assert sanitized["user"]["password"] == "***REDACTED***"
        assert sanitized["config"]["api_key"] == "***REDACTED***"

    def test_sanitize_dict_with_string_values(self):
        """Test that string values in dictionaries are sanitized."""
        data = {
            "message": "api_key=abc123 password=secret123",
        }
        sanitized = sanitize_dict(data)
        assert "***REDACTED***" in sanitized["message"]
        assert "abc123" not in sanitized["message"]
        assert "secret123" not in sanitized["message"]

    def test_non_sensitive_dict_unchanged(self):
        """Test that dictionaries without sensitive data are unchanged."""
        data = {
            "name": "John",
            "age": 30,
            "city": "New York",
        }
        sanitized = sanitize_dict(data)
        assert sanitized == data


class TestExceptionArgsSanitization:
    """Test exception arguments sanitization."""

    def test_sanitize_exception_args_with_password(self):
        """Test that exception arguments with passwords are sanitized."""
        args = ("Error occurred", "password=secret123")
        sanitized = sanitize_exception_args(args)
        assert "password=***REDACTED***" in sanitized[1]
        assert "secret123" not in sanitized[1]

    def test_sanitize_exception_args_with_dict(self):
        """Test that exception arguments with dictionaries are sanitized."""
        args = ("Error occurred", {"password": "secret123"})
        sanitized = sanitize_exception_args(args)
        assert sanitized[1]["password"] == "***REDACTED***"

    def test_sanitize_exception_args_non_sensitive(self):
        """Test that non-sensitive exception arguments are unchanged."""
        args = ("Error occurred", 123, {"key": "value"})
        sanitized = sanitize_exception_args(args)
        assert sanitized == args
