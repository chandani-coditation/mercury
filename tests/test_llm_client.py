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

    def test_gateway_disabled_uses_openai(self):
        """Test that gateway disabled uses OpenAI client."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "false"

        from ai_service.llm_client import _use_private_gateway

        assert _use_private_gateway() is False

    def test_gateway_enabled_detection(self):
        """Test that gateway enabled is detected."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"

        from ai_service.llm_client import _use_private_gateway

        assert _use_private_gateway() is True

    @patch("ai_service.llm_client.requests.post")
    def test_gateway_api_call_structure(self, mock_post):
        """Test that gateway API call has correct structure."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ["PRIVATE_LLM_GATEWAY_URL"] = "https://test-gateway.com/api/v1/ai/call"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": '{"incident_signature": {}}'}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from ai_service.llm_client import _call_private_gateway

        request_params = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Test system"},
                {"role": "user", "content": "Test user"},
            ],
            "temperature": 0.3,
            "timeout": 60.0,
        }

        _call_private_gateway(request_params)

        # Verify API was called
        assert mock_post.called
        call_args = mock_post.call_args

        # Verify URL
        assert call_args[0][0] == "https://test-gateway.com/api/v1/ai/call"

        # Verify headers
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"] == "Basic test_auth_key"

        # Verify payload structure
        payload = call_args[1]["json"]
        assert "chatId" in payload
        assert "input" in payload
        assert "model" in payload
        assert payload["model"] == "gpt-4o"

    @patch("ai_service.llm_client.requests.post")
    def test_gateway_response_transformation(self, mock_post):
        """Test that gateway response is transformed to OpenAI format."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ["PRIVATE_LLM_GATEWAY_URL"] = "https://test-gateway.com/api/v1/ai/call"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        # Mock gateway response
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test response from gateway"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from ai_service.llm_client import _call_private_gateway

        request_params = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Test"}],
            "timeout": 60.0,
        }

        response = _call_private_gateway(request_params)

        # Verify response has OpenAI structure
        assert hasattr(response, "choices")
        assert len(response.choices) == 1
        assert hasattr(response.choices[0], "message")
        assert hasattr(response.choices[0].message, "content")
        assert response.choices[0].message.content == "Test response from gateway"

        # Verify usage structure
        assert hasattr(response, "usage")
        assert hasattr(response.usage, "prompt_tokens")
        assert hasattr(response.usage, "completion_tokens")

    def test_model_name_from_config(self):
        """Test that model name comes from request params."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ["PRIVATE_LLM_GATEWAY_URL"] = "https://test-gateway.com/api/v1/ai/call"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        with patch("ai_service.llm_client.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"response": "test"}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            from ai_service.llm_client import _call_private_gateway

            request_params = {
                "model": "gpt-5-mini",
                "messages": [{"role": "user", "content": "Test"}],
                "timeout": 60.0,
            }

            _call_private_gateway(request_params)

            payload = mock_post.call_args[1]["json"]
            assert payload["model"] == "gpt-5-mini"


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
