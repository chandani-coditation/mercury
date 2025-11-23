"""Embedding generation utilities."""
import os
import tiktoken
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Token limits for embedding models
EMBEDDING_MODEL_LIMITS = {
    "text-embedding-3-small": 8191,
    "text-embedding-3-large": 8191,
    "text-embedding-ada-002": 8191
}

def count_tokens(text: str, model: str = "text-embedding-3-small") -> int:
    """Count tokens in text using the same encoding as the embedding model."""
    encoding = tiktoken.get_encoding("cl100k_base")  # Used by text-embedding-3-small
    return len(encoding.encode(text))


def get_embedding_client():
    """Get OpenAI client for embeddings."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=api_key)


def embed_text(text: str, model: str = "text-embedding-3-small") -> list:
    """
    Generate embedding for text.
    
    Args:
        text: Text to embed
        model: OpenAI embedding model name
    
    Returns:
        List of floats (embedding vector)
    
    Raises:
        ValueError: If text exceeds token limit
    """
    client = get_embedding_client()
    
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
    
    response = client.embeddings.create(
        model=model,
        input=text
    )
    
    return response.data[0].embedding


def embed_texts_batch(texts: List[str], model: str = "text-embedding-3-small", batch_size: int = 100) -> List[List[float]]:
    """
    Generate embeddings for multiple texts in batches.
    
    This is much more efficient than calling embed_text() multiple times.
    OpenAI supports up to 2048 texts per batch, but we use 100 as default
    to avoid rate limits and stay within token limits.
    
    Args:
        texts: List of texts to embed
        model: OpenAI embedding model name
        batch_size: Number of texts to process per API call (default: 100)
    
    Returns:
        List of embedding vectors (same order as input texts)
    
    Raises:
        ValueError: If any text exceeds token limit
    """
    if not texts:
        return []
    
    client = get_embedding_client()
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
    
    # Process texts in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        # Clean texts (replace newlines with spaces)
        cleaned_batch = [text.replace("\n", " ").strip() for text in batch]
        
        # Generate embeddings for batch
        response = client.embeddings.create(
            model=model,
            input=cleaned_batch  # List of texts (batch API)
        )
        
        # Extract embeddings (maintain order)
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
    
    return all_embeddings



