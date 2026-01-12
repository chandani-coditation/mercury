"""Password validation utilities for production security."""

import os
import re
from typing import List, Tuple


# Common weak passwords that should be rejected
WEAK_PASSWORDS = [
    "password",
    "123456",
    "12345678",
    "qwerty",
    "abc123",
    "password123",
    "admin",
    "root",
    "postgres",
    "nocdb",
    "noc_ai",
    "test",
    "default",
]


def validate_password_strength(password: str, is_production: bool = None) -> Tuple[bool, List[str]]:
    """
    Validate password strength based on security requirements.

    Args:
        password: Password to validate
        is_production: Whether running in production. If None, auto-detects from ENVIRONMENT variable.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    if is_production is None:
        is_production = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")

    errors = []

    # Check if password is provided
    if not password or password.strip() == "":
        errors.append("Password cannot be empty")
        return False, errors

    # Check minimum length
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    # Check for weak passwords (case-insensitive)
    if password.lower() in [p.lower() for p in WEAK_PASSWORDS]:
        errors.append("Password is too common or weak. Please use a stronger password.")

    # Production-specific requirements
    if is_production:
        # Require at least 12 characters in production
        if len(password) < 12:
            errors.append("Production passwords must be at least 12 characters long")

        # Require at least one uppercase letter
        if not re.search(r"[A-Z]", password):
            errors.append("Production passwords must contain at least one uppercase letter")

        # Require at least one lowercase letter
        if not re.search(r"[a-z]", password):
            errors.append("Production passwords must contain at least one lowercase letter")

        # Require at least one digit
        if not re.search(r"\d", password):
            errors.append("Production passwords must contain at least one digit")

        # Require at least one special character
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            errors.append("Production passwords must contain at least one special character")

        # Check for common patterns
        if re.search(r"(.)\1{2,}", password):  # Same character repeated 3+ times
            errors.append("Password contains repeated characters (e.g., 'aaa')")

        # Check for sequential characters
        if re.search(
            r"(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)",
            password.lower(),
        ):
            errors.append("Password contains sequential characters")

    return len(errors) == 0, errors


def validate_database_password() -> Tuple[bool, List[str]]:
    """
    Validate the database password from environment variables.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    password = os.getenv("POSTGRES_PASSWORD", "")
    is_production = os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")

    # In development, allow default passwords but warn
    if not is_production:
        if password in ("postgres", "nocdb", "noc_ai", "", "<db_password>"):
            return True, []  # Allow in development
        # Still validate strength if a custom password is provided
        return validate_password_strength(password, is_production=False)

    # In production, enforce strict validation
    if password in ("postgres", "nocdb", "noc_ai", "", "<db_password>"):
        return False, [
            "Default or placeholder database password detected in production. "
            "Please set a strong, unique password in POSTGRES_PASSWORD environment variable."
        ]

    return validate_password_strength(password, is_production=True)
