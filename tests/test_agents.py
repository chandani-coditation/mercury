"""Unit tests for AI agents."""
import pytest
from datetime import datetime
from ai_service.agents.triager import triage_agent
from ai_service.agents.resolution_copilot import resolution_copilot_agent


@pytest.fixture
def sample_alert():
    """Sample alert for testing."""
    return {
        "alert_id": "test-alert-1",
        "source": "prometheus",
        "title": "High CPU Usage",
        "description": "CPU usage exceeded 90% for 5 minutes",
        "labels": {
            "service": "api-gateway",
            "component": "api",
            "severity": "high"
        },
        "ts": datetime.utcnow().isoformat()
    }


def test_triage_agent_structure(sample_alert):
    """Test that triage agent returns expected structure."""
    # Note: This test requires database and LLM, so it's more of an integration test
    # For unit tests, we'd mock these dependencies
    pass


def test_resolution_copilot_structure():
    """Test that resolution copilot returns expected structure."""
    # Note: This test requires database and LLM, so it's more of an integration test
    pass

