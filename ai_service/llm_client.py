"""LLM client for OpenAI with retry logic."""

import os
import json
import time
import random
from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
from dotenv import load_dotenv
from ai_service.core import get_llm_config, get_logger
from ai_service.prompts import (
    TRIAGE_USER_PROMPT_TEMPLATE,
    TRIAGE_SYSTEM_PROMPT_DEFAULT,
    RESOLUTION_USER_PROMPT_TEMPLATE,
    RESOLUTION_SYSTEM_PROMPT_DEFAULT,
)

load_dotenv()

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds
RETRY_EXPONENTIAL_BASE = 2.0


def get_llm_client():
    """Get OpenAI client."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=api_key)


def _should_retry(error: Exception) -> bool:
    """
    Determine if an error should trigger a retry.

    Args:
        error: The exception that occurred

    Returns:
        True if the error is retryable, False otherwise
    """
    # Retry on rate limits, connection errors, and timeouts
    if isinstance(error, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True

    # Retry on 5xx server errors (internal server errors)
    if isinstance(error, APIError):
        if hasattr(error, "status_code") and error.status_code:
            status = error.status_code
            # Retry on 5xx errors, but also on 429 (Too Many Requests) which might be temporary
            if 500 <= status < 600 or status == 429:
                return True

    # Don't retry on 4xx client errors (except 429) or other errors
    return False


def _call_llm_with_retry(client, request_params, agent_type: str, model: str):
    """
    Call LLM API with exponential backoff retry logic.

    Args:
        client: OpenAI client instance
        request_params: Parameters for the API call
        agent_type: Type of agent (triage or resolution)
        model: Model name for metrics

    Returns:
        API response

    Raises:
        Exception: If all retries are exhausted
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Add timeout to prevent hanging (60 seconds default)
            request_params_with_timeout = {**request_params, "timeout": 60.0}
            response = client.chat.completions.create(**request_params_with_timeout)
            return response

        except Exception as e:
            last_error = e

            # Check if we should retry
            if not _should_retry(e) or attempt == MAX_RETRIES - 1:
                logger.error(
                    f"LLM {agent_type} error (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}",
                    exc_info=True,
                )
                raise

            # Calculate exponential backoff with jitter
            # For rate limits, use longer initial delay
            if isinstance(e, RateLimitError):
                base_delay = INITIAL_RETRY_DELAY * 2  # Start with 2s for rate limits
            else:
                base_delay = INITIAL_RETRY_DELAY

            delay = min(base_delay * (RETRY_EXPONENTIAL_BASE**attempt), MAX_RETRY_DELAY)
            jitter = random.uniform(0, delay * 0.1)  # Add up to 10% jitter
            total_delay = delay + jitter

            error_type = type(e).__name__
            logger.warning(
                f"LLM {agent_type} error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                f"Retrying in {total_delay:.2f}s..."
            )
            time.sleep(total_delay)

    # Should never reach here, but just in case
    if last_error:
        raise last_error


def call_llm_for_triage(alert: dict, context_chunks: list, model: str = None) -> dict:
    """
    Call LLM to triage an alert.

    Args:
        alert: Alert dictionary
        context_chunks: Retrieved context chunks
        model: Optional OpenAI model to use (overrides config if provided)

    Returns:
        Triage output as dictionary
    """
    client = get_llm_client()

    # Get LLM config (with defaults)
    llm_config = get_llm_config()
    triage_config = llm_config.get("triage", {})

    # Use provided model or config, with fallback
    model = model or triage_config.get("model", "gpt-4-turbo-preview")
    temperature = triage_config.get("temperature", 0.3)
    system_prompt = triage_config.get("system_prompt", TRIAGE_SYSTEM_PROMPT_DEFAULT)
    response_format_type = triage_config.get("response_format", "json_object")
    max_tokens = triage_config.get("max_tokens")

    logger.debug(
        f"Calling LLM for triage: model={model}, temperature={temperature}, chunks={len(context_chunks)}"
    )

    # Build context from chunks
    context_text = "\n\n---\n\n".join(
        [
            f"Document: {chunk.get('doc_title', 'Unknown')}\n{chunk['content']}"
            for chunk in context_chunks[:5]  # Top 5 chunks
        ]
    )

    # Build user prompt from template
    prompt = TRIAGE_USER_PROMPT_TEMPLATE.format(
        alert_title=alert["title"],
        alert_description=alert["description"],
        alert_labels=json.dumps(alert.get("labels", {}), indent=2),
        alert_source=alert["source"],
        context_text=context_text,
    )

    # Build request parameters
    request_params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }

    # Add response format if json_object
    if response_format_type == "json_object":
        request_params["response_format"] = {"type": "json_object"}

    # Add max_tokens if specified
    if max_tokens:
        request_params["max_tokens"] = max_tokens

    # Call LLM with retry logic
    try:
        response = _call_llm_with_retry(client, request_params, "triage", model)

        # Extract token usage if available
        usage = response.usage
        if usage:
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0
            logger.debug(
                f"LLM triage tokens: prompt={prompt_tokens}, completion={completion_tokens}"
            )

        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        logger.debug(f"LLM triage response parsed successfully")
        return result

    except Exception as e:
        logger.error(f"LLM triage failed after retries: {str(e)}", exc_info=True)
        raise


def call_llm_for_resolution(
    alert: dict, triage_output: dict, context_chunks: list, model: str = None
) -> dict:
    """
    Call LLM to generate resolution steps.

    Args:
        alert: Alert dictionary
        triage_output: Previous triage output
        context_chunks: Retrieved context chunks (prefer runbooks)
        model: Optional OpenAI model to use (overrides config if provided)

    Returns:
        Resolution output as dictionary
    """
    client = get_llm_client()

    # Get LLM config (with defaults)
    llm_config = get_llm_config()
    resolution_config = llm_config.get("resolution", {})

    # Use provided model or config, with fallback
    model = model or resolution_config.get("model", "gpt-4-turbo-preview")
    temperature = resolution_config.get("temperature", 0.2)
    system_prompt = resolution_config.get("system_prompt", RESOLUTION_SYSTEM_PROMPT_DEFAULT)
    response_format_type = resolution_config.get("response_format", "json_object")
    max_tokens = resolution_config.get("max_tokens")

    logger.debug(
        f"Calling LLM for resolution: model={model}, temperature={temperature}, chunks={len(context_chunks)}"
    )

    # Build context from chunks (prefer runbooks) with provenance info
    context_parts = []
    for chunk in context_chunks[:10]:  # Include more chunks for better context
        chunk_id = chunk.get("chunk_id", "unknown")
        doc_id = chunk.get("document_id", "unknown")
        doc_title = chunk.get("doc_title", "Unknown")
        context_parts.append(
            f"Document: {doc_title}\n"
            f"Chunk ID: {chunk_id}\n"
            f"Document ID: {doc_id}\n"
            f"Content: {chunk['content']}"
        )
    context_text = "\n\n---\n\n".join(context_parts)

    # Build user prompt from template
    prompt = RESOLUTION_USER_PROMPT_TEMPLATE.format(
        alert_title=alert["title"],
        alert_description=alert["description"],
        severity=triage_output.get("severity", "unknown"),
        category=triage_output.get("category", "unknown"),
        likely_cause=triage_output.get("likely_cause", "unknown"),
        context_text=context_text,
    )

    # Build request parameters
    request_params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }

    # Add response format if json_object
    if response_format_type == "json_object":
        request_params["response_format"] = {"type": "json_object"}

    # Add max_tokens if specified
    if max_tokens:
        request_params["max_tokens"] = max_tokens

    # Call LLM with retry logic
    try:
        response = _call_llm_with_retry(client, request_params, "resolution", model)

        # Extract token usage if available
        usage = response.usage
        if usage:
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0
            logger.debug(
                f"LLM resolution tokens: prompt={prompt_tokens}, completion={completion_tokens}"
            )

        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        logger.debug(f"LLM resolution response parsed successfully")
        return result

    except Exception as e:
        logger.error(f"LLM resolution failed after retries: {str(e)}", exc_info=True)
        raise
