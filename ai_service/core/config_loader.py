"""Configuration loader for config files."""

import os
import json
from typing import Dict, Optional
from ai_service.core import get_logger

logger = get_logger(__name__)

_CONFIG_CACHE: Optional[Dict] = None


def _get_config_dir() -> str:
    """
    Get the absolute path to the configuration directory.

    Calculates the path relative to this module's location. The config directory
    is expected to be at the project root level, containing JSON configuration files.

    Returns:
        str: Absolute path to the config directory (typically <project_root>/config)
    """
    # __file__ is ai_service/core/config_loader.py
    # Go up 3 levels: ai_service/core/ -> ai_service/ -> project root
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(current_dir, "config")


def load_config(config_dir: Optional[str] = None) -> Dict:
    """
    Load configuration from config directory (multiple JSON files).

    Loads and merges the following config files:
    - policy.json
    - guardrails.json
    - llm.json
    - retrieval.json
    - workflow.json
    - schemas.json
    - field_mappings.json

    Args:
        config_dir: Optional path to config directory. If None, uses default location.

    Returns:
        Merged configuration dictionary
    """
    global _CONFIG_CACHE

    # Return cached config if available
    if _CONFIG_CACHE is not None:
        logger.debug("Returning cached configuration")
        return _CONFIG_CACHE

    # Determine config directory
    if config_dir is None:
        config_dir = _get_config_dir()

    logger.info(f"Loading configuration from: {config_dir}")

    # Config files to load (in order)
    config_files = {
        "policy_gate": "policy.json",
        "guardrails": "guardrails.json",
        "llm": "llm.json",
        "retrieval": "retrieval.json",
        "workflow": "workflow.json",
        "field_mappings": "field_mappings.json",
        "embeddings": "embeddings.json",
        "historical_data_inputs": "schemas.json",  # Will extract this key
        "alert_metadata": "schemas.json",  # Will extract this key
    }

    merged_config = {}

    # Load each config file
    for key, filename in config_files.items():
        config_path = os.path.join(config_dir, filename)

        try:
            with open(config_path, "r") as f:
                file_config = json.load(f)

            logger.debug(f"Loaded config file: {filename}")

            # Special handling for schemas.json (contains multiple top-level keys)
            if filename == "schemas.json":
                merged_config["historical_data_inputs"] = file_config.get(
                    "historical_data_inputs", {}
                )
                merged_config["alert_metadata"] = file_config.get("alert_metadata", {})
            else:
                merged_config[key] = file_config

        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file {config_path}: {e}")
            raise ValueError(f"Invalid JSON in configuration file {config_path}: {e}")

    _CONFIG_CACHE = merged_config
    logger.debug("Configuration loaded and cached")
    return merged_config


def reload_config(config_dir: Optional[str] = None) -> Dict:
    """
    Force reload configuration (clears cache).

    Args:
        config_dir: Optional path to config directory.

    Returns:
        Configuration dictionary
    """
    global _CONFIG_CACHE
    logger.info("Reloading configuration (clearing cache)")
    _CONFIG_CACHE = None
    return load_config(config_dir)


def get_policy_config() -> Dict:
    """
    Get policy gate configuration.

    Returns the policy gate configuration which defines automated action policies
    (AUTO, PROPOSE, REVIEW) based on triage output and resolution risk levels.

    Returns:
        Dict: Policy gate configuration dictionary
    """
    config = load_config()
    return config.get("policy_gate", {})


def get_guardrail_config() -> Dict:
    """
    Get guardrails configuration.

    Returns the guardrails configuration which defines validation rules for LLM outputs,
    including hallucination detection, duplication checks, and architectural boundary enforcement.

    Returns:
        Dict: Guardrails configuration dictionary
    """
    config = load_config()
    return config.get("guardrails", {})


def get_retrieval_config() -> Dict:
    """
    Get retrieval configuration.

    Returns the retrieval configuration which defines parameters for hybrid search,
    including vector similarity search, full-text search, RRF (Reciprocal Rank Fusion),
    and MMR (Maximal Marginal Relevance) settings.

    Returns:
        Dict: Retrieval configuration dictionary
    """
    config = load_config()
    return config.get("retrieval", {})


def get_workflow_config() -> Dict:
    """
    Get workflow configuration.

    Returns the workflow configuration which defines feature flags and settings
    for feedback collection, policy enforcement, and other workflow-related features.

    Returns:
        Dict: Workflow configuration dictionary containing feedback and policy flags
    """
    config = load_config()
    return config.get("workflow", {})


def get_llm_config() -> Dict:
    """
    Get LLM configuration.

    Returns the LLM configuration which defines model settings, temperature,
    max tokens, and other parameters for OpenAI API calls.

    Returns:
        Dict: LLM configuration dictionary containing model name, temperature, max_tokens, etc.
    """
    config = load_config()
    return config.get("llm", {})


def get_field_mappings_config() -> Dict:
    """
    Get field mappings configuration.

    Returns the field mappings configuration which defines how external data formats
    (CSV columns, DOCX sections) map to internal data models and database schemas.

    Returns:
        Dict: Field mappings configuration dictionary
    """
    config = load_config()
    return config.get("field_mappings", {})


def get_embeddings_config() -> Dict:
    """
    Get embeddings configuration.

    Returns the embeddings configuration which defines the embedding model,
    dimensions, and other parameters for vector embedding generation.

    Returns:
        Dict: Embeddings configuration dictionary containing model name, dimensions, etc.
    """
    config = load_config()
    return config.get("embeddings", {})
