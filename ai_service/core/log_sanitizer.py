"""Log sanitization utilities to prevent sensitive data from being logged."""

import re
from typing import Any, Dict, List, Optional

# Patterns for sensitive data that should be redacted
SENSITIVE_PATTERNS = [
    # API keys
    r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?([a-zA-Z0-9\-_]{20,})['\"]?",
    r"(?i)(openai[_-]?api[_-]?key)\s*[:=]\s*['\"]?(sk-[a-zA-Z0-9\-_]{20,})['\"]?",
    # Passwords
    r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{3,})['\"]?",
    r"(?i)(postgres[_-]?password)\s*[:=]\s*['\"]?([^\s'\"]{3,})['\"]?",
    # Tokens
    r"(?i)(token|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9\-_]{20,})['\"]?",
    # Connection strings with passwords
    r"(?i)(postgresql://[^:]+):([^@]+)@",
    r"(?i)(postgres://[^:]+):([^@]+)@",
    # AWS credentials
    r"(?i)(aws[_-]?(secret[_-]?access[_-]?key|access[_-]?key[_-]?id))\s*[:=]\s*['\"]?([A-Z0-9]{20,})['\"]?",
]


def sanitize_log_message(message: str) -> str:
    """
    Sanitize a log message by redacting sensitive information.

    Args:
        message: The log message to sanitize

    Returns:
        Sanitized log message with sensitive data redacted
    """
    if not isinstance(message, str):
        return str(message)

    sanitized = message

    # Redact API keys (OpenAI format: sk-...)
    sanitized = re.sub(
        r"sk-[a-zA-Z0-9\-_]{20,}",
        "sk-***REDACTED***",
        sanitized,
        flags=re.IGNORECASE,
    )

    # Redact generic API keys
    sanitized = re.sub(
        r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[a-zA-Z0-9\-_]{20,}['\"]?",
        r"\1=***REDACTED***",
        sanitized,
    )

    # Redact passwords
    sanitized = re.sub(
        r"(?i)(password|passwd|pwd|postgres[_-]?password)\s*[:=]\s*['\"]?[^\s'\"]{3,}['\"]?",
        r"\1=***REDACTED***",
        sanitized,
    )

    # Redact connection strings
    sanitized = re.sub(
        r"(?i)(postgresql://|postgres://)[^:]+:[^@]+@",
        r"\1***REDACTED***:***REDACTED***@",
        sanitized,
    )

    # Redact tokens
    sanitized = re.sub(
        r"(?i)(token|bearer)\s*[:=]\s*['\"]?[a-zA-Z0-9\-_]{20,}['\"]?",
        r"\1=***REDACTED***",
        sanitized,
    )

    # Redact AWS credentials
    sanitized = re.sub(
        r"(?i)(aws[_-]?(secret[_-]?access[_-]?key|access[_-]?key[_-]?id))\s*[:=]\s*['\"]?[A-Z0-9]{20,}['\"]?",
        r"\1=***REDACTED***",
        sanitized,
    )

    return sanitized


def sanitize_dict(
    data: Dict[str, Any], sensitive_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sanitize a dictionary by redacting values for sensitive keys.

    Args:
        data: Dictionary to sanitize
        sensitive_keys: Optional list of keys to redact. If None, uses default list.

    Returns:
        Sanitized dictionary with sensitive values redacted
    """
    if sensitive_keys is None:
        sensitive_keys = [
            "password",
            "passwd",
            "pwd",
            "api_key",
            "apikey",
            "openai_api_key",
            "token",
            "secret",
            "access_key",
            "secret_key",
            "postgres_password",
            "db_password",
            "database_password",
        ]

    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        # Check if this key should be redacted
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, sensitive_keys)
        elif isinstance(value, str):
            sanitized[key] = sanitize_log_message(value)
        else:
            sanitized[key] = value

    return sanitized


def sanitize_exception_args(args: tuple) -> tuple:
    """
    Sanitize exception arguments to prevent sensitive data leakage.

    Args:
        args: Exception arguments tuple

    Returns:
        Sanitized arguments tuple
    """
    sanitized_args = []
    for arg in args:
        if isinstance(arg, str):
            sanitized_args.append(sanitize_log_message(arg))
        elif isinstance(arg, dict):
            sanitized_args.append(sanitize_dict(arg))
        else:
            sanitized_args.append(arg)
    return tuple(sanitized_args)
