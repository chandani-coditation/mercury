"""Unit tests for password validation utilities."""

import os
import pytest
from ai_service.core.password_validator import (
    validate_password_strength,
    validate_database_password,
)


class TestPasswordStrength:
    """Test password strength validation."""

    def test_empty_password(self):
        """Test that empty passwords are rejected."""
        is_valid, errors = validate_password_strength("")
        assert not is_valid
        assert "cannot be empty" in errors[0].lower()

    def test_short_password(self):
        """Test that passwords shorter than 8 characters are rejected."""
        is_valid, errors = validate_password_strength("short")
        assert not is_valid
        assert any("8 characters" in e for e in errors)

    def test_weak_password(self):
        """Test that common weak passwords are rejected."""
        is_valid, errors = validate_password_strength("password")
        assert not is_valid
        assert any("weak" in e.lower() or "common" in e.lower() for e in errors)

    def test_valid_development_password(self):
        """Test that valid passwords for development are accepted."""
        is_valid, errors = validate_password_strength("validpass123", is_production=False)
        assert is_valid
        assert len(errors) == 0

    def test_production_password_requirements(self):
        """Test that production passwords have stricter requirements."""
        # Too short for production
        is_valid, errors = validate_password_strength("short123", is_production=True)
        assert not is_valid
        assert any("12 characters" in e for e in errors)

        # Missing uppercase
        is_valid, errors = validate_password_strength("lowercase123!", is_production=True)
        assert not is_valid
        assert any("uppercase" in e.lower() for e in errors)

        # Missing lowercase
        is_valid, errors = validate_password_strength("UPPERCASE123!", is_production=True)
        assert not is_valid
        assert any("lowercase" in e.lower() for e in errors)

        # Missing digit
        is_valid, errors = validate_password_strength("NoDigitsHere!", is_production=True)
        assert not is_valid
        assert any("digit" in e.lower() for e in errors)

        # Missing special character
        is_valid, errors = validate_password_strength("NoSpecial123", is_production=True)
        assert not is_valid
        assert any("special" in e.lower() for e in errors)

        # Valid production password
        is_valid, errors = validate_password_strength("ValidPass123!@#", is_production=True)
        assert is_valid
        assert len(errors) == 0

    def test_repeated_characters(self):
        """Test that passwords with repeated characters are rejected in production."""
        is_valid, errors = validate_password_strength("aaaBBB123!", is_production=True)
        assert not is_valid
        assert any("repeated" in e.lower() for e in errors)

    def test_sequential_characters(self):
        """Test that passwords with sequential characters are rejected in production."""
        is_valid, errors = validate_password_strength("abcDEF123!", is_production=True)
        assert not is_valid
        assert any("sequential" in e.lower() for e in errors)


class TestDatabasePasswordValidation:
    """Test database password validation."""

    def test_default_password_in_production(self, monkeypatch):
        """Test that default passwords are rejected in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")

        is_valid, errors = validate_database_password()
        assert not is_valid
        assert any("default" in e.lower() or "placeholder" in e.lower() for e in errors)

    def test_default_password_in_development(self, monkeypatch):
        """Test that default passwords are allowed in development."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")

        is_valid, errors = validate_database_password()
        assert is_valid
        assert len(errors) == 0

    def test_strong_password_in_production(self, monkeypatch):
        """Test that strong passwords are accepted in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("POSTGRES_PASSWORD", "StrongPass123!@#")

        is_valid, errors = validate_database_password()
        assert is_valid
        assert len(errors) == 0
