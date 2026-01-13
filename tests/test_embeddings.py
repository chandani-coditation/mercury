"""Unit tests for embeddings with gateway support."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestEmbeddingsGateway:
    """Test embeddings gateway integration."""

    def setup_method(self):
        """Set up test environment."""
        # Store original env vars
        self.original_env = {
            "PRIVATE_LLM_GATEWAY": os.environ.get("PRIVATE_LLM_GATEWAY"),
            "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL": os.environ.get(
                "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL"
            ),
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

        from ingestion.embeddings import _use_gateway_for_embeddings

        assert _use_gateway_for_embeddings() is False

    def test_gateway_enabled_detection(self):
        """Test that gateway enabled is detected."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"

        from ingestion.embeddings import _use_gateway_for_embeddings

        assert _use_gateway_for_embeddings() is True

    @patch("ingestion.embeddings.requests.post")
    def test_gateway_embeddings_api_call_structure(self, mock_post):
        """Test that gateway embeddings API call has correct structure."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ[
            "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL"
        ] = "https://test-gateway.com/api/v1/ai/openai/embeddings"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3] * 512}],  # 1536 dimensions
            "model": "text-embedding-3-small",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from ingestion.embeddings import _call_gateway_embeddings

        result = _call_gateway_embeddings("Test text", "text-embedding-3-small")

        # Verify API was called
        assert mock_post.called
        call_args = mock_post.call_args

        # Verify URL
        assert call_args[0][0] == "https://test-gateway.com/api/v1/ai/openai/embeddings"

        # Verify headers
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"] == "Basic test_auth_key"

        # Verify payload structure
        payload = call_args[1]["json"]
        assert "input" in payload
        assert "model" in payload
        assert payload["input"] == "Test text"
        assert payload["model"] == "text-embedding-3-small"

        # Verify response
        assert result is not None
        assert "data" in result

    @patch("ingestion.embeddings.requests.post")
    def test_single_embedding_with_gateway(self, mock_post):
        """Test single text embedding with gateway enabled."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ[
            "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL"
        ] = "https://test-gateway.com/api/v1/ai/openai/embeddings"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        # Mock response with 1536-dim embedding
        mock_embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": mock_embedding}],
            "model": "text-embedding-3-small",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from ingestion.embeddings import embed_text

        result = embed_text("Test text")

        assert result is not None
        assert len(result) == 1536
        assert result[0] == 0.1

    @patch("ingestion.embeddings.requests.post")
    def test_batch_embeddings_with_gateway(self, mock_post):
        """Test batch embeddings with gateway enabled."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ[
            "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL"
        ] = "https://test-gateway.com/api/v1/ai/openai/embeddings"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        # Mock response with multiple embeddings
        mock_embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": emb} for emb in mock_embeddings],
            "model": "text-embedding-3-small",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from ingestion.embeddings import embed_texts_batch

        texts = ["Text 1", "Text 2", "Text 3"]
        result = embed_texts_batch(texts)

        assert result is not None
        assert len(result) == 3
        assert len(result[0]) == 1536
        assert result[0][0] == 0.1
        assert result[1][0] == 0.2
        assert result[2][0] == 0.3

    def test_exact_url_used(self):
        """Test that exact URL from env var is used (not SDK path logic)."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"
        os.environ[
            "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL"
        ] = "https://custom-gateway.example.com/custom/path/embeddings"
        os.environ["PRIVATE_LLM_AUTH_KEY"] = "test_auth_key"

        with patch("ingestion.embeddings.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": [{"embedding": [0.1] * 1536}]}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            from ingestion.embeddings import _call_gateway_embeddings

            _call_gateway_embeddings("Test", "text-embedding-3-small")

            # Verify exact URL is used
            call_url = mock_post.call_args[0][0]
            assert call_url == "https://custom-gateway.example.com/custom/path/embeddings"


class TestEmbeddingsIntegration:
    """Integration tests for embeddings (requires actual credentials)."""

    @pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "true",
        reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true to run.",
    )
    def test_single_embedding_with_gateway_enabled(self):
        """Test actual single embedding with gateway enabled."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"

        from ingestion.embeddings import embed_text

        result = embed_text("Test text for integration")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1536  # text-embedding-3-small dimension

    @pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "true",
        reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true to run.",
    )
    def test_batch_embeddings_with_gateway_enabled(self):
        """Test actual batch embeddings with gateway enabled."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "true"

        from ingestion.embeddings import embed_texts_batch

        texts = ["First test text", "Second test text", "Third test text"]
        result = embed_texts_batch(texts)

        assert result is not None
        assert len(result) == 3
        assert all(len(emb) == 1536 for emb in result)

    @pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "true",
        reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=true to run.",
    )
    def test_embeddings_with_gateway_disabled(self):
        """Test actual embeddings with gateway disabled (OpenAI)."""
        os.environ["PRIVATE_LLM_GATEWAY"] = "false"

        from ingestion.embeddings import embed_text

        result = embed_text("Test text for OpenAI")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1536


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
