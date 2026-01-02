"""Private LLM Gateway client with retry logic."""
import os
import json
import time
import random
import uuid
import requests
from dotenv import load_dotenv
from ai_service.core import get_logger

load_dotenv()

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds
RETRY_EXPONENTIAL_BASE = 2.0

# Gateway configuration
DEFAULT_BASE_URL = "https://llmg.int.mgc.com/api/v1/ai/call"
DEFAULT_CERT_PATH = "llm_server.crt"


def get_gateway_config():
    """Get private gateway configuration from environment variables."""
    return {
        "base_url": os.getenv("PRIVATE_LLM_GATEWAY_URL", DEFAULT_BASE_URL),
        "cert_path": os.getenv("PRIVATE_LLM_GATEWAY_CERT", DEFAULT_CERT_PATH),
        "auth_key": os.getenv("PRIVATE_LLM_GATEWAY_AUTH_KEY"),
        "use_auth": os.getenv("PRIVATE_LLM_GATEWAY_USE_AUTH", "true").lower() == "true",
        "model": os.getenv("PRIVATE_LLM_GATEWAY_MODEL", "gpt-4o")
    }


def _should_retry_gateway(status_code: int = None, error: Exception = None) -> bool:
    """
    Determine if a gateway error should trigger a retry.

    Args:
        status_code: HTTP status code if available
        error: The exception that occurred

    Returns:
        True if the error is retryable, False otherwise
    """
    # Retry on connection errors
    if isinstance(error, (requests.exceptions.ConnectionError,
                         requests.exceptions.Timeout,
                         requests.exceptions.RequestException)):
        return True

    # Retry on 5xx server errors and 429 (rate limit)
    if status_code:
        if 500 <= status_code < 600 or status_code == 429:
            return True

    # Don't retry on 4xx client errors (except 429)
    return False


def _call_gateway_with_retry(
    base_url: str,
    headers: dict,
    payload: dict,
    cert_path: str
) -> dict:
    """
    Call private gateway API with exponential backoff retry logic.

    Args:
        base_url: Gateway API endpoint URL
        headers: Request headers
        payload: Request payload
        cert_path: Path to SSL certificate

    Returns:
        API response as dictionary

    Raises:
        Exception: If all retries are exhausted
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Determine verification method
            verify = cert_path if os.path.exists(cert_path) else True

            # Make the request with timeout
            response = requests.post(
                base_url,
                headers=headers,
                json=payload,
                verify=verify,
                timeout=60.0
            )
            response.raise_for_status()

            # Return the JSON response
            return response.json()

        except requests.exceptions.RequestException as e:
            last_error = e
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else None

            # Check if we should retry
            if not _should_retry_gateway(status_code, e) or attempt == MAX_RETRIES - 1:
                logger.error(
                    f"Gateway API error (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}",
                    exc_info=True
                )
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Error response body: {e.response.text}")
                raise

            # Calculate exponential backoff with jitter
            # For rate limits (429), use longer initial delay
            if status_code == 429:
                base_delay = INITIAL_RETRY_DELAY * 2  # Start with 2s for rate limits
            else:
                base_delay = INITIAL_RETRY_DELAY

            delay = min(
                base_delay * (RETRY_EXPONENTIAL_BASE ** attempt),
                MAX_RETRY_DELAY
            )
            jitter = random.uniform(0, delay * 0.1)  # Add up to 10% jitter
            total_delay = delay + jitter

            error_type = type(e).__name__
            logger.warning(
                f"Gateway API error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                f"Retrying in {total_delay:.2f}s..."
            )
            time.sleep(total_delay)

    # Should never reach here, but just in case
    if last_error:
        raise last_error


def call_private_gateway(
    prompt_text: str,
    model: str = None
) -> dict:
    """
    Call the private LLM gateway API.

    Args:
        prompt_text: The complete prompt to send to the LLM
        model: Optional model override

    Returns:
        Response dictionary from the gateway

    Raises:
        ValueError: If required configuration is missing
        requests.exceptions.RequestException: If the API call fails
    """
    config = get_gateway_config()

    # Validate required configuration
    if config["use_auth"] and not config["auth_key"]:
        raise ValueError(
            "PRIVATE_LLM_GATEWAY_AUTH_KEY not set in environment. "
            "Either set the auth key or disable authentication."
        )

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "accept": "*/*"
    }

    if config["use_auth"]:
        headers["Authorization"] = f"Basic {config['auth_key']}"

    # Build payload
    payload = {
        "chatId": str(uuid.uuid4()),
        "input": prompt_text,
        "model": model or config["model"]
    }

    logger.debug(
        f"Calling private gateway: model={payload['model']}, "
        f"chat_id={payload['chatId']}"
    )

    try:
        result = _call_gateway_with_retry(
            config["base_url"],
            headers,
            payload,
            config["cert_path"]
        )
        logger.debug(f"Gateway response received successfully")
        return result

    except Exception as e:
        logger.error(f"Gateway call failed after retries: {str(e)}", exc_info=True)
        raise


def format_gateway_response_for_triage(gateway_response: dict) -> dict:
    """
    Format the gateway response to match expected triage output format.

    Args:
        gateway_response: Raw response from the gateway

    Returns:
        Formatted triage output dictionary
    """
    # The gateway might return the response in different formats
    # We need to extract the actual content and parse it as JSON

    # Try to get the response text from common response fields
    response_text = None
    if isinstance(gateway_response, dict):
        # Common response field names
        for key in ['output', 'response', 'text', 'content', 'answer', 'result']:
            if key in gateway_response:
                response_text = gateway_response[key]
                break

        # If no common field found, the entire response might be the answer
        if response_text is None:
            response_text = gateway_response

    # If response_text is already a dict, return it
    if isinstance(response_text, dict):
        return response_text

    # Otherwise, try to parse it as JSON
    if isinstance(response_text, str):
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse gateway response as JSON: {response_text}")
            raise ValueError("Gateway response is not valid JSON")

    raise ValueError(f"Unexpected gateway response format: {type(gateway_response)}")


def format_gateway_response_for_resolution(gateway_response: dict) -> dict:
    """
    Format the gateway response to match expected resolution output format.

    Args:
        gateway_response: Raw response from the gateway

    Returns:
        Formatted resolution output dictionary
    """
    # Same logic as triage formatting
    return format_gateway_response_for_triage(gateway_response)
