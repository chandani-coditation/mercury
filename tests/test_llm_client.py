"""Unit tests for LLM client with gateway support."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestLLMClientGateway:
    """Test LLM client gateway integration."""

    def setup_method(self):
        """Set up test environment."""
        # Store original env vars
        self.original_env = {
            "PRIVATE_LLM_GATEWAY": os.environ.get("PRIVATE_LLM_GATEWAY"),
            "PRIVATE_LLM_GATEWAY_URL": os.environ.get("PRIVATE_LLM_GATEWAY_URL"),
            "PRIVATE_LLM_AUTH_KEY": os.environ.get("PRIVATE_LLM_AUTH_KEY"),
        }

    def teardown_method(self):
        """Restore original environment."""
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # Note: Gateway-specific tests removed as functionality moved to ai_service.core.llm_handler
    # Gateway tests should be added to tests/test_llm_handler.py if needed


class TestLLMClientIntegration:
    """Integration tests for LLM client (requires actual credentials)."""

    @pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "true",
        reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true to run.",
    )
    def test_triage_with_gateway_enabled(self):
        """Test actual triage call with gateway enabled."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"

        from ai_service.llm_client import call_llm_for_triage

        test_alert = {
            "title": "Database connection timeout",
            "description": "Application cannot connect to PostgreSQL database",
            "labels": {},
            "source": "test",
        }

        test_evidence = {"incident_signatures": [], "runbook_metadata": []}

        result = call_llm_for_triage(test_alert, test_evidence)

        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "true",
        reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true to run.",
    )
    def test_triage_with_gateway_disabled(self):
        """Test actual triage call with gateway disabled (OpenAI)."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "false"

        from ai_service.llm_client import call_llm_for_triage

        test_alert = {
            "title": "Database connection timeout",
            "description": "Application cannot connect to PostgreSQL database",
            "labels": {},
            "source": "test",
        }

        test_evidence = {"incident_signatures": [], "runbook_metadata": []}

        result = call_llm_for_triage(test_alert, test_evidence)

        assert result is not None
        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
