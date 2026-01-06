"""Text chunking utilities."""

import tiktoken
import re
import json
from pathlib import Path
from typing import List

# Load chunking config
_chunking_config = None

def _load_chunking_config():
    """Load chunking configuration from config file."""
    global _chunking_config
    if _chunking_config is None:
        try:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "ingestion.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = json.load(f)
                    _chunking_config = config.get("chunking", {})
            else:
                _chunking_config = {}
        except Exception:
            _chunking_config = {}
    return _chunking_config


def chunk_text(
    text: str,
    min_tokens: int = None,
    max_tokens: int = None,
    target_tokens: int = None,
    overlap: int = None,
) -> List[str]:
    """
    Chunk text into token-sized pieces with overlap.

    Args:
        text: Text to chunk
        min_tokens: Minimum tokens per chunk (defaults to config)
        max_tokens: Maximum tokens per chunk (defaults to config)
        target_tokens: Target tokens per chunk (defaults to config)
        overlap: Number of tokens to overlap between chunks (defaults to config)

    Returns:
        List of text chunks
    """
    # Load config values (graceful degradation with defaults)
    chunking_config = _load_chunking_config()
    min_tokens = min_tokens or chunking_config.get("min_tokens", 180)
    max_tokens = max_tokens or chunking_config.get("max_tokens", 320)
    target_tokens = target_tokens or chunking_config.get("target_tokens", 250)
    overlap = overlap or chunking_config.get("overlap", 30)
    safe_max_tokens_config = chunking_config.get("safe_max_tokens", 3000)
    large_paragraph_threshold = chunking_config.get("large_paragraph_threshold", 100000)
    
    encoding = tiktoken.get_encoding("cl100k_base")  # Used by text-embedding-3-small

    # Safety limit: ensure chunks never exceed embedding model limit (8191 tokens)
    # We use a conservative limit from config (default 3000) to account for headers and safety margin
    SAFE_MAX_TOKENS = min(max_tokens, safe_max_tokens_config)

    # Split by paragraphs first
    paragraphs = re.split(r"\n\s*\n", text.strip())

    # If no paragraph breaks (e.g., large log file), split by single newlines
    if len(paragraphs) == 1 and len(text) > large_paragraph_threshold:  # Large single paragraph (from config)
        paragraphs = text.split("\n")

    chunks = []
    current_chunk = []
    current_tokens = 0

    for para in paragraphs:
        if not para.strip():
            continue

        para_tokens = len(encoding.encode(para))

        # If paragraph itself is too large, split by sentences
        if para_tokens > SAFE_MAX_TOKENS:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            # If no sentence breaks (e.g., log lines), split by newlines
            if len(sentences) == 1:
                sentences = para.split("\n")
            # If still too large, split by character chunks
            if len(sentences) == 1 and para_tokens > SAFE_MAX_TOKENS:
                # Split into character-based chunks as last resort
                char_chunk_size = SAFE_MAX_TOKENS * 4  # Rough estimate: ~4 chars per token
                sentences = [
                    para[j : j + char_chunk_size] for j in range(0, len(para), char_chunk_size)
                ]

            for sentence in sentences:
                sent_tokens = len(encoding.encode(sentence))

                # If sentence itself is still too large, force split it
                if sent_tokens > SAFE_MAX_TOKENS:
                    # Force split by characters
                    char_chunk_size = SAFE_MAX_TOKENS * 4
                    for k in range(0, len(sentence), char_chunk_size):
                        sub_chunk = sentence[k : k + char_chunk_size]
                        sub_tokens = len(encoding.encode(sub_chunk))
                        if current_tokens + sub_tokens > SAFE_MAX_TOKENS and current_chunk:
                            chunk_text = " ".join(current_chunk)
                            chunks.append(chunk_text)
                            current_chunk = [sub_chunk]
                            current_tokens = sub_tokens
                        else:
                            current_chunk.append(sub_chunk)
                            current_tokens += sub_tokens
                    continue

                if current_tokens + sent_tokens > SAFE_MAX_TOKENS and current_chunk:
                    # Save current chunk
                    chunk_text = " ".join(current_chunk)
                    chunks.append(chunk_text)

                    # Start new chunk with overlap
                    if overlap > 0 and chunks:
                        # Get last few sentences for overlap
                        last_chunk = chunks[-1]
                        last_sentences = re.split(r"(?<=[.!?])\s+", last_chunk)
                        if not last_sentences:
                            last_sentences = last_chunk.split("\n")[:2]
                        overlap_text = (
                            " ".join(last_sentences[-2:])
                            if len(last_sentences) >= 2
                            else last_sentences[-1]
                        )
                        overlap_tokens = len(encoding.encode(overlap_text))
                        if overlap_tokens <= overlap * 2:
                            current_chunk = [overlap_text, sentence]
                            current_tokens = overlap_tokens + sent_tokens
                        else:
                            current_chunk = [sentence]
                            current_tokens = sent_tokens
                    else:
                        current_chunk = [sentence]
                        current_tokens = sent_tokens
                else:
                    current_chunk.append(sentence)
                    current_tokens += sent_tokens
        else:
            # Check if adding this paragraph would exceed safe max
            if current_tokens + para_tokens > SAFE_MAX_TOKENS and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(chunk_text)

                # Start new chunk with overlap
                if overlap > 0 and chunks:
                    last_chunk = chunks[-1]
                    last_sentences = re.split(r"(?<=[.!?])\s+", last_chunk)
                    if not last_sentences:
                        last_sentences = last_chunk.split("\n")[:1]
                    overlap_text = " ".join(last_sentences[-1:])
                    overlap_tokens = len(encoding.encode(overlap_text))
                    if overlap_tokens <= overlap * 2:
                        current_chunk = [overlap_text, para]
                        current_tokens = overlap_tokens + para_tokens
                    else:
                        current_chunk = [para]
                        current_tokens = para_tokens
                else:
                    current_chunk = [para]
                    current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

    # Add final chunk if it meets minimum
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunk_tokens = len(encoding.encode(chunk_text))

        # Safety check: if final chunk is too large, split it
        if chunk_tokens > SAFE_MAX_TOKENS:
            # Split the final chunk
            char_chunk_size = SAFE_MAX_TOKENS * 4
            for k in range(0, len(chunk_text), char_chunk_size):
                sub_chunk = chunk_text[k : k + char_chunk_size]
                sub_tokens = len(encoding.encode(sub_chunk))
                if sub_tokens >= min_tokens:
                    chunks.append(sub_chunk)
                elif chunks:
                    chunks[-1] = chunks[-1] + " " + sub_chunk
        elif chunk_tokens >= min_tokens:
            chunks.append(chunk_text)
        # Note: min_tokens is now 180 (target: 180-320), but we still accept chunks >= 120 for edge cases
        elif chunks:
            # Merge with last chunk if too small
            chunks[-1] = chunks[-1] + " " + chunk_text
        else:
            # If no chunks yet and this is too small, add it anyway (it's all we have)
            chunks.append(chunk_text)

    # Final safety check: ensure no chunk exceeds safe limit
    final_chunks = []
    for chunk in chunks:
        chunk_tokens = len(encoding.encode(chunk))
        if chunk_tokens > SAFE_MAX_TOKENS:
            # Force split oversized chunks
            char_chunk_size = SAFE_MAX_TOKENS * 4
            for k in range(0, len(chunk), char_chunk_size):
                final_chunks.append(chunk[k : k + char_chunk_size])
        else:
            final_chunks.append(chunk)

    return final_chunks


def add_chunk_header(
    chunk: str,
    doc_type: str,
    service: str = None,
    component: str = None,
    title: str = None,
    last_reviewed_at: str = None,
) -> str:
    """Add compact metadata header to chunk for context.

    Headers are auto-appended with: doc type, service/component, title, last_reviewed_at
    """
    header_parts = []
    if doc_type:
        header_parts.append(f"Type: {doc_type}")
    if service:
        header_parts.append(f"Service: {service}")
    if component:
        header_parts.append(f"Component: {component}")
    if title:
        header_parts.append(f"Title: {title}")
    if last_reviewed_at:
        header_parts.append(f"Last Reviewed: {last_reviewed_at}")

    if header_parts:
        header = " | ".join(header_parts) + "\n\n"
        return header + chunk
    return chunk
