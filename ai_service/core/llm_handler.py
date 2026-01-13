"""
Common LLM handler that abstracts OpenAI and Private LLM Gateway.

This module provides a unified interface for LLM operations, automatically
handling both OpenAI API and Private LLM Gateway based on configuration.
Only one mode is active at a time (gateway OR OpenAI, never both).
"""

import os
import json
import time
import random
import uuid
from typing import Optional, Dict, List, Any
from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
import requests
from requests.exceptions import (
    RequestException,
    Timeout,
    ConnectionError as RequestsConnectionError,
)

from ai_service.core import get_logger

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds
RETRY_EXPONENTIAL_BASE = 2.0


class LLMHandler:
    """
    Unified handler for LLM operations supporting both OpenAI and Private Gateway.

    Automatically detects which mode to use based on PRIVATE_LLM_GATEWAY environment variable.
    Validates all required configuration before use.
    """

    def __init__(self):
        """Initialize the LLM handler and detect which mode to use."""
        self._use_gateway = self._detect_gateway_mode()
        self._openai_client: Optional[OpenAI] = None
        self._gateway_config: Optional[Dict[str, str]] = None

        if self._use_gateway:
            self._gateway_config = self._load_gateway_config()
            logger.info("LLM Handler initialized in GATEWAY mode")
        else:
            self._openai_client = self._create_openai_client()
            logger.info("LLM Handler initialized in OPENAI mode")

    @staticmethod
    def _detect_gateway_mode() -> bool:
        """
        Detect if gateway mode should be used.

        Returns:
            True if PRIVATE_LLM_GATEWAY is set to "true", False otherwise
        """
        return os.getenv("PRIVATE_LLM_GATEWAY", "false").lower() == "true"

    @staticmethod
    def _load_gateway_config() -> Dict[str, str]:
        """
        Load and validate gateway configuration.

        Returns:
            Dictionary with gateway configuration

        Raises:
            ValueError: If required gateway configuration is missing
        """
        url = os.getenv("PRIVATE_LLM_GATEWAY_URL")
        auth_key = os.getenv("PRIVATE_LLM_AUTH_KEY")
        cert_path = os.getenv("PRIVATE_LLM_CERT_PATH", "")
        embeddings_url = os.getenv("PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL")

        if not url:
            raise ValueError(
                "PRIVATE_LLM_GATEWAY_URL not set when PRIVATE_LLM_GATEWAY=true. "
                "Please set PRIVATE_LLM_GATEWAY_URL in your environment."
            )

        if not auth_key:
            raise ValueError(
                "PRIVATE_LLM_AUTH_KEY not set when PRIVATE_LLM_GATEWAY=true. "
                "Please set PRIVATE_LLM_AUTH_KEY in your environment."
            )

        if not embeddings_url:
            raise ValueError(
                "PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL not set when PRIVATE_LLM_GATEWAY=true. "
                "Please set PRIVATE_LLM_GATEWAY_EMBEDDINGS_URL in your environment."
            )

        return {
            "url": url,
            "auth_key": auth_key,
            "cert_path": cert_path if cert_path else None,
            "embeddings_url": embeddings_url,
        }

    @staticmethod
    def _create_openai_client() -> OpenAI:
        """
        Create and return OpenAI client.

        Returns:
            Initialized OpenAI client

        Raises:
            ValueError: If OPENAI_API_KEY is not set
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not set when PRIVATE_LLM_GATEWAY=false. "
                "Please set OPENAI_API_KEY in your environment."
            )
        return OpenAI(api_key=api_key)

    def is_gateway_mode(self) -> bool:
        """
        Check if handler is in gateway mode.

        Returns:
            True if using gateway, False if using OpenAI
        """
        return self._use_gateway

    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate current configuration and return status.

        Returns:
            Dictionary with validation status and details
        """
        status = {
            "mode": "gateway" if self._use_gateway else "openai",
            "valid": True,
            "errors": [],
        }

        if self._use_gateway:
            if not self._gateway_config:
                status["valid"] = False
                status["errors"].append("Gateway configuration not loaded")
            else:
                # Check if all required fields are present
                required_fields = ["url", "auth_key", "embeddings_url"]
                for field in required_fields:
                    if not self._gateway_config.get(field):
                        status["valid"] = False
                        status["errors"].append(f"Missing gateway config: {field}")
        else:
            if not self._openai_client:
                status["valid"] = False
                status["errors"].append("OpenAI client not initialized")
            try:
                # Try to access API key (doesn't make actual API call)
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    status["valid"] = False
                    status["errors"].append("OPENAI_API_KEY not set")
            except Exception as e:
                status["valid"] = False
                status["errors"].append(f"OpenAI configuration error: {str(e)}")

        return status

    def _call_gateway_chat(self, request_params: Dict[str, Any]) -> Any:
        """
        Call gateway API for chat completions.

        Args:
            request_params: Parameters for the API call (model, messages, temperature, etc.)

        Returns:
            Response object compatible with OpenAI format
        """
        if not self._gateway_config:
            raise ValueError("Gateway configuration not available")

        # Combine messages into single prompt
        messages = request_params.get("messages", [])
        prompt_text = "\n\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in messages])

        # Build request
        headers = {"Content-Type": "application/json", "accept": "*/*"}
        if self._gateway_config["auth_key"]:
            headers["Authorization"] = f"Basic {self._gateway_config['auth_key']}"

        payload = {
            "chatId": str(uuid.uuid4()),
            "input": prompt_text,
            "model": request_params.get("model", "gpt-4o-mini"),
        }

        # Call API
        response = requests.post(
            self._gateway_config["url"],
            headers=headers,
            json=payload,
            verify=self._gateway_config["cert_path"] if self._gateway_config["cert_path"] else True,
            timeout=request_params.get("timeout", 60.0),
        )
        response.raise_for_status()
        gateway_response = response.json()

        # Transform to OpenAI format
        class Response:
            class Choice:
                class Message:
                    def __init__(self, content):
                        self.content = content

                def __init__(self, content):
                    self.message = self.Message(content)

            class Usage:
                def __init__(self):
                    self.prompt_tokens = 0
                    self.completion_tokens = 0

            def __init__(self, content):
                self.choices = [self.Choice(content)]
                self.usage = self.Usage()

        # Extract content (adjust based on actual gateway response)
        content = (
            gateway_response.get("response")
            or gateway_response.get("output")
            or str(gateway_response)
        )
        return Response(content)

    def _call_gateway_embeddings(
        self, text_or_texts: str | List[str], model: str
    ) -> Dict[str, Any]:
        """
        Call gateway API for embeddings.

        Args:
            text_or_texts: Single text string or list of texts
            model: Model name

        Returns:
            Gateway response in OpenAI-compatible format
        """
        if not self._gateway_config:
            raise ValueError("Gateway configuration not available")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self._gateway_config['auth_key']}",
        }

        payload = {
            "input": text_or_texts,
            "model": model,
        }

        # Call gateway with exact URL
        response = requests.post(
            self._gateway_config["embeddings_url"],
            headers=headers,
            json=payload,
            verify=self._gateway_config["cert_path"] if self._gateway_config["cert_path"] else True,
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()

    def _should_retry(self, error: Exception) -> bool:
        """
        Determine if an error should trigger a retry.

        Handles both OpenAI exceptions and HTTP request exceptions from gateway.

        Args:
            error: The exception that occurred

        Returns:
            True if the error is retryable, False otherwise
        """
        # Retry on OpenAI rate limits, connection errors, and timeouts
        if isinstance(error, (RateLimitError, APIConnectionError, APITimeoutError)):
            return True

        # Retry on OpenAI 5xx server errors
        if isinstance(error, APIError):
            if hasattr(error, "status_code") and error.status_code:
                status = error.status_code
                # Retry on 5xx errors, but also on 429 (Too Many Requests)
                if 500 <= status < 600 or status == 429:
                    return True

        # Retry on HTTP request exceptions (gateway mode)
        if isinstance(error, (RequestsConnectionError, Timeout)):
            return True

        # Retry on HTTP 5xx and 429 status codes from gateway
        if isinstance(error, RequestException):
            if hasattr(error, "response") and error.response is not None:
                status = error.response.status_code
                if 500 <= status < 600 or status == 429:
                    return True

        # Don't retry on 4xx client errors (except 429) or other errors
        return False

    def chat_completions_create(
        self, request_params: Dict[str, Any], agent_type: str = "llm"
    ) -> Any:
        """
        Create chat completions with retry logic.

        Works with both OpenAI and gateway modes transparently.

        Args:
            request_params: Parameters for the API call (model, messages, temperature, etc.)
            agent_type: Type of agent (for logging purposes)

        Returns:
            API response (OpenAI-compatible format)

        Raises:
            Exception: If all retries are exhausted
        """
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                # Add timeout to prevent hanging (60 seconds default)
                request_params_with_timeout = {**request_params, "timeout": 60.0}

                if self._use_gateway:
                    response = self._call_gateway_chat(request_params_with_timeout)
                else:
                    response = self._openai_client.chat.completions.create(
                        **request_params_with_timeout
                    )
                return response

            except Exception as e:
                last_error = e

                # Check if we should retry
                if not self._should_retry(e) or attempt == MAX_RETRIES - 1:
                    logger.error(
                        f"LLM {agent_type} error (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}",
                        exc_info=True,
                    )
                    raise

                # Calculate exponential backoff with jitter
                if isinstance(e, (RateLimitError, RequestException)):
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

    def embeddings_create(
        self, text_or_texts: str | List[str], model: str, timeout: float = 60.0
    ) -> Any:
        """
        Create embeddings with retry logic.

        Works with both OpenAI and gateway modes transparently.

        Args:
            text_or_texts: Single text string or list of texts
            model: Model name
            timeout: Request timeout in seconds

        Returns:
            Embeddings response (OpenAI-compatible format)

        Raises:
            Exception: If all retries are exhausted
        """
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                if self._use_gateway:
                    response = self._call_gateway_embeddings(text_or_texts, model)

                    # Gateway returns dict, transform to OpenAI-like object
                    class EmbeddingResponse:
                        class DataItem:
                            def __init__(self, embedding):
                                self.embedding = embedding

                        def __init__(self, data):
                            # Handle both list of dicts and list of lists
                            if data and isinstance(data[0], dict):
                                self.data = [
                                    self.DataItem(item.get("embedding", item)) for item in data
                                ]
                            else:
                                self.data = [self.DataItem(item) for item in data]

                    return EmbeddingResponse(response.get("data", []))
                else:
                    response = self._openai_client.embeddings.create(
                        model=model, input=text_or_texts, timeout=timeout
                    )
                    return response

            except Exception as e:
                last_error = e

                # Check if we should retry
                if not self._should_retry(e) or attempt == MAX_RETRIES - 1:
                    logger.error(
                        f"Embedding API error (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}",
                        exc_info=True,
                    )
                    raise

                # Calculate exponential backoff with jitter
                if isinstance(e, (RateLimitError, RequestException)):
                    base_delay = INITIAL_RETRY_DELAY * 2
                else:
                    base_delay = INITIAL_RETRY_DELAY

                delay = min(base_delay * (RETRY_EXPONENTIAL_BASE**attempt), MAX_RETRY_DELAY)
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter

                error_type = type(e).__name__
                logger.warning(
                    f"Embedding API error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                    f"Retrying in {total_delay:.2f}s..."
                )
                time.sleep(total_delay)

        # Should never reach here, but just in case
        if last_error:
            raise last_error


# Global singleton instance
_llm_handler_instance: Optional[LLMHandler] = None


def get_llm_handler() -> LLMHandler:
    """
    Get the global LLM handler instance (singleton pattern).

    Returns:
        LLMHandler instance
    """
    global _llm_handler_instance
    if _llm_handler_instance is None:
        _llm_handler_instance = LLMHandler()
    return _llm_handler_instance


def reset_llm_handler():
    """
    Reset the global LLM handler instance (useful for testing).
    """
    global _llm_handler_instance
    _llm_handler_instance = None
