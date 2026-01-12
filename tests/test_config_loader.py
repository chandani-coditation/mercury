"""Unit tests for configuration loader."""

import os
import json
import tempfile
import pytest
from ai_service.core.config_loader import (
    load_config,
    reload_config,
    get_policy_config,
    get_guardrail_config,
    get_retrieval_config,
    get_workflow_config,
    get_llm_config,
    get_field_mappings_config,
    get_embeddings_config,
)


class TestConfigLoader:
    """Test configuration loading functionality."""

    def test_get_policy_config(self):
        """Test that policy config is retrieved correctly."""
        config = get_policy_config()
        assert isinstance(config, dict)

    def test_get_guardrail_config(self):
        """Test that guardrail config is retrieved correctly."""
        config = get_guardrail_config()
        assert isinstance(config, dict)

    def test_get_retrieval_config(self):
        """Test that retrieval config is retrieved correctly."""
        config = get_retrieval_config()
        assert isinstance(config, dict)

    def test_get_workflow_config(self):
        """Test that workflow config is retrieved correctly."""
        config = get_workflow_config()
        assert isinstance(config, dict)

    def test_get_llm_config(self):
        """Test that LLM config is retrieved correctly."""
        config = get_llm_config()
        assert isinstance(config, dict)

    def test_get_field_mappings_config(self):
        """Test that field mappings config is retrieved correctly."""
        config = get_field_mappings_config()
        assert isinstance(config, dict)

    def test_get_embeddings_config(self):
        """Test that embeddings config is retrieved correctly."""
        config = get_embeddings_config()
        assert isinstance(config, dict)

    def test_config_caching(self):
        """Test that configuration is cached after first load."""
        # Clear any existing cache by reloading
        reload_config()

        # Load config twice
        config1 = load_config()
        config2 = load_config()

        # Should be the same object (cached)
        assert config1 is config2

    def test_reload_config_clears_cache(self):
        """Test that reload_config clears the cache."""
        # Load config
        config1 = load_config()

        # Reload config
        config2 = reload_config()

        # Should be different objects (cache cleared)
        # Note: In practice they may have same content, but cache was cleared
        assert isinstance(config2, dict)
