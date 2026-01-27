"""Embedding generation utilities."""

import os
import sys
import time
import random
from pathlib import Path
import tiktoken
from typing import List, Optional
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
from dotenv import load_dotenv
from ai_service.core import get_llm_handler


# Lazy import for logger
def get_logger(name):
    try:
        from ai_service.core import get_logger as _get_logger

        return _get_logger(name)
    except ImportError:
        import logging

        return logging.getLogger(name)


logger = get_logger(__name__)

load_dotenv()

# Try to load embeddings config, fallback to defaults
try:
    # Add project root to path for config loading
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    from ai_service.core import get_embeddings_config

    embeddings_config = get_embeddings_config()
    DEFAULT_MODEL = embeddings_config.get("model", "text-embedding-3-small")
except Exception:
    DEFAULT_MODEL = "text-embedding-3-small"

# Token limits for embedding models
EMBEDDING_MODEL_LIMITS = {
    "text-embedding-3-small": 8191,
    "text-embedding-3-large": 8191,
    "text-embedding-ada-002": 8191,
    "bge-m3": 8192,
}

# Retry configuration for embedding API calls
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
RETRY_EXPONENTIAL_BASE = 2.0
MAX_RETRY_DELAY = 60.0  # seconds
EMBEDDING_TIMEOUT = 60.0  # seconds


def _should_retry_embedding_error(error: Exception) -> bool:
    """
    Determine if an embedding API error should be retried.

    Args:
        error: Exception from embedding API call

    Returns:
        True if error should be retried, False otherwise
    """
    # Retry on rate limits, connection errors, and timeouts
    if isinstance(error, RateLimitError):
        return True
    if isinstance(error, APIConnectionError):
        return True
    if isinstance(error, APITimeoutError):
        return True
    # Retry on 5xx server errors
    if isinstance(error, APIError):
        if (
            hasattr(error, "status_code")
            and error.status_code
            and 500 <= error.status_code < 600
        ):
            return True
    # Don't retry on client errors (4xx) or validation errors
    return False


def count_tokens(text: str, model: str = None) -> int:
    """Count tokens in text using the same encoding as the embedding model."""
    if model is None:
        model = DEFAULT_MODEL
    encoding = tiktoken.get_encoding(
        "cl100k_base"
    )  # Used by OpenAI embedding models
    return len(encoding.encode(text))


def get_embedding_client():
    """
    Get LLM handler for embeddings (for backward compatibility).

    This function is kept for backward compatibility with existing code.
    New code should use get_llm_handler() directly from ai_service.core.

    Returns:
        LLMHandler: The global LLM handler instance
    """
    # Import here to avoid circular dependencies
    from ai_service.core import get_llm_handler

    return get_llm_handler()


def embed_text(text: str, model: str = None) -> Optional[List[float]]:
    """
    Generate embedding for text with retry logic and error handling.

    Args:
        text: Text to embed
        model: OpenAI embedding model name (defaults to config)

    Returns:
        List of floats (embedding vector) or None if embedding fails after retries

    Raises:
        ValueError: If text exceeds token limit or is empty
    """
    if model is None:
        model = DEFAULT_MODEL

    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    # Replace newlines with spaces for better embeddings
    text = text.replace("\n", " ").strip()

    # Validate token count before API call
    max_tokens = EMBEDDING_MODEL_LIMITS.get(model, 8191)
    token_count = count_tokens(text, model)

    if token_count > max_tokens:
        raise ValueError(
            f"Text exceeds token limit: {token_count} tokens (max: {max_tokens}). "
            f"Text length: {len(text)} characters. "
            f"Please chunk the text before embedding."
        )

    # Get LLM handler (handles both gateway and OpenAI modes)
    handler = get_llm_handler()

    last_error = None

    # Retry logic with exponential backoff
    for attempt in range(MAX_RETRIES):
        try:
            # Use common handler (works for both gateway and OpenAI)
            response = handler.embeddings_create(
                text, model, timeout=EMBEDDING_TIMEOUT
            )
            return response.data[0].embedding

        except Exception as e:
            last_error = e

            # Check if we should retry
            if (
                not _should_retry_embedding_error(e)
                or attempt == MAX_RETRIES - 1
            ):
                error_type = type(e).__name__
                logger.error(
                    f"Embedding API error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                    f"Text length: {len(text)} chars, tokens: {token_count}",
                    exc_info=True,
                )

                # For non-retryable errors or final attempt, log and return None
                # This allows ingestion to continue with other chunks
                if attempt == MAX_RETRIES - 1:
                    logger.warning(
                        f"Failed to generate embedding after {MAX_RETRIES} attempts. "
                        f"Skipping this chunk. Error: {str(e)}"
                    )
                    return None
                raise

            # Calculate exponential backoff with jitter
            if isinstance(e, RateLimitError):
                base_delay = (
                    INITIAL_RETRY_DELAY * 2
                )  # Start with 2s for rate limits
            else:
                base_delay = INITIAL_RETRY_DELAY

            delay = min(
                base_delay * (RETRY_EXPONENTIAL_BASE**attempt), MAX_RETRY_DELAY
            )
            jitter = random.uniform(0, delay * 0.1)  # Add up to 10% jitter
            total_delay = delay + jitter

            error_type = type(e).__name__
            logger.warning(
                f"Embedding API error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                f"Retrying in {total_delay:.2f}s..."
            )
            time.sleep(total_delay)

    # Should never reach here, but just in case
    if last_error:
        logger.error(f"Embedding failed after all retries: {last_error}")
        return None

    return None


def embed_texts_batch(
    texts: List[str], model: str = None, batch_size: int = None
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts in batches.

    This is much more efficient than calling embed_text() multiple times.
    OpenAI supports up to 2048 texts per batch, but we use config value (default 100)
    to avoid rate limits and stay within token limits.

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model name (defaults to config)
        batch_size: Number of texts to process per API call (defaults to config, fallback: 100)

    Returns:
        List of embedding vectors (same order as input texts)

    Raises:
        ValueError: If any text exceeds token limit
    """
    if not texts:
        return []

    if model is None:
        model = DEFAULT_MODEL

    # Load batch size from config if not provided (graceful degradation)
    if batch_size is None:
        try:
            import json
            from pathlib import Path

            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "ingestion.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    ingestion_config = json.load(f)
                    batch_size = ingestion_config.get("batch_sizes", {}).get(
                        "embedding_batch_default", 100
                    )
            else:
                batch_size = 100  # Fallback to default
        except Exception:
            batch_size = 100  # Fallback to default

    # Get LLM handler (handles both gateway and OpenAI modes)
    from ai_service.core import get_llm_handler

    handler = get_llm_handler()

    all_embeddings = []
    max_tokens = EMBEDDING_MODEL_LIMITS.get(model, 8191)

    # Validate all texts before processing
    invalid_texts = []
    for idx, text in enumerate(texts):
        token_count = count_tokens(text, model)
        if token_count > max_tokens:
            invalid_texts.append((idx, token_count, len(text)))

    if invalid_texts:
        error_msg = f"Found {len(invalid_texts)} text(s) exceeding token limit ({max_tokens}):\n"
        for idx, tokens, chars in invalid_texts[:5]:  # Show first 5
            error_msg += f"  Text {idx}: {tokens} tokens ({chars} chars)\n"
        if len(invalid_texts) > 5:
            error_msg += f"  ... and {len(invalid_texts) - 5} more\n"
        error_msg += "Please ensure chunks are properly sized before embedding."
        raise ValueError(error_msg)

    # Process texts in batches with retry logic
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]

        # Clean texts (replace newlines with spaces)
        cleaned_batch = [text.replace("\n", " ").strip() for text in batch]

        # Retry logic for batch embedding
        batch_embeddings = None
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                # Use common handler (works for both gateway and OpenAI)
                response = handler.embeddings_create(
                    cleaned_batch, model, timeout=EMBEDDING_TIMEOUT
                )
                # Extract embeddings (maintain order)
                batch_embeddings = [item.embedding for item in response.data]

                break  # Success, exit retry loop

            except Exception as e:
                last_error = e

                # Check if we should retry
                if (
                    not _should_retry_embedding_error(e)
                    or attempt == MAX_RETRIES - 1
                ):
                    error_type = type(e).__name__
                    logger.error(
                        f"Batch embedding API error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                        f"Batch size: {len(batch)}",
                        exc_info=True,
                    )

                    # For final attempt, generate embeddings individually as fallback
                    if attempt == MAX_RETRIES - 1:
                        logger.warning(
                            f"Batch embedding failed after {MAX_RETRIES} attempts. "
                            f"Falling back to individual embedding calls for batch of {len(batch)} texts."
                        )
                        # Fallback: try individual embeddings
                        batch_embeddings = []
                        for text in cleaned_batch:
                            individual_embedding = embed_text(text, model=model)
                            if individual_embedding:
                                batch_embeddings.append(individual_embedding)
                            else:
                                # If individual embedding also fails, use zero vector as last resort
                                logger.warning(
                                    f"Individual embedding failed for text, using zero vector"
                                )
                                # Use zero vector of appropriate dimension (1536 for text-embedding-3-small)
                                dim = (
                                    1536
                                    if "small" in model
                                    else 3072 if "large" in model else 1536
                                )
                                batch_embeddings.append([0.0] * dim)
                        break
                    raise

                # Calculate exponential backoff with jitter
                if isinstance(e, RateLimitError):
                    base_delay = INITIAL_RETRY_DELAY * 2
                else:
                    base_delay = INITIAL_RETRY_DELAY

                delay = min(
                    base_delay * (RETRY_EXPONENTIAL_BASE**attempt),
                    MAX_RETRY_DELAY,
                )
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter

                error_type = type(e).__name__
                logger.warning(
                    f"Batch embedding API error ({error_type}, attempt {attempt + 1}/{MAX_RETRIES}): {str(e)}. "
                    f"Retrying in {total_delay:.2f}s..."
                )
                time.sleep(total_delay)

        if batch_embeddings:
            all_embeddings.extend(batch_embeddings)
        else:
            # Last resort: use zero vectors if all retries failed
            logger.error(
                f"Failed to generate embeddings for batch after all retries. Using zero vectors."
            )
            dim = (
                1536 if "small" in model else 3072 if "large" in model else 1536
            )
            all_embeddings.extend([[0.0] * dim] * len(cleaned_batch))

    return all_embeddings
