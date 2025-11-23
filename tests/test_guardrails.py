"""Unit tests for guardrails."""
import pytest
from ai_service.guardrails import validate_triage_output, validate_resolution_output


def test_validate_triage_output_valid():
    """Test validation of valid triage output."""
    triage_output = {
        "severity": "high",
        "category": "application",
        "confidence": 0.85,
        "summary": "High CPU usage detected",
        "likely_cause": "Increased traffic load",
        "affected_services": ["api-gateway"],
        "recommended_actions": ["Scale up", "Check load balancer"]
    }
    
    is_valid, errors = validate_triage_output(triage_output)
    assert is_valid is True
    assert len(errors) == 0


def test_validate_triage_output_missing_field():
    """Test validation fails when required field is missing."""
    triage_output = {
        "severity": "high",
        "category": "application",
        # Missing confidence
        "summary": "High CPU usage detected"
    }
    
    is_valid, errors = validate_triage_output(triage_output)
    assert is_valid is False
    assert len(errors) > 0
    assert any("confidence" in error.lower() for error in errors)


def test_validate_triage_output_invalid_severity():
    """Test validation fails with invalid severity."""
    triage_output = {
        "severity": "invalid",
        "category": "application",
        "confidence": 0.85,
        "summary": "Test",
        "likely_cause": "Test",
        "affected_services": [],
        "recommended_actions": []
    }
    
    is_valid, errors = validate_triage_output(triage_output)
    assert is_valid is False
    assert any("severity" in error.lower() for error in errors)


def test_validate_resolution_output_valid():
    """Test validation of valid resolution output."""
    resolution_output = {
        "resolution_steps": ["Step 1", "Step 2"],
        "estimated_time_minutes": 15,
        "risk_level": "low",
        "requires_approval": False
    }
    
    is_valid, errors = validate_resolution_output(resolution_output)
    assert is_valid is True
    assert len(errors) == 0


def test_validate_resolution_output_dangerous_command():
    """Test validation fails with dangerous command."""
    resolution_output = {
        "resolution_steps": ["Step 1"],
        "estimated_time_minutes": 15,
        "risk_level": "low",
        "requires_approval": False,
        "commands": ["rm -rf /tmp/test"]
    }
    
    is_valid, errors = validate_resolution_output(resolution_output)
    assert is_valid is False
    assert any("dangerous" in error.lower() for error in errors)

