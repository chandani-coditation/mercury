"""Database operations for ingestion."""

import uuid
import json
from datetime import datetime
from db.connection import get_db_connection
from ingestion.embeddings import embed_text
from ingestion.chunker import chunk_text, add_chunk_header


def create_tsvector(text: str) -> str:
    """Create tsvector from text for full-text search."""
    # Simple tsvector creation - Postgres will handle the actual parsing
    return text


def insert_document_and_chunks(
    doc_type: str,
    service: str,
    component: str,
    title: str,
    content: str,
    tags: dict = None,
    last_reviewed_at: datetime = None,
) -> str:
    """
    Insert document and its chunks into database.

    Returns:
        Document ID (UUID as string)
    """
    # Validate required fields BEFORE any database operations or embedding generation
    if not title or not title.strip():
        raise ValueError("Title is required and cannot be empty")
    if not content or not content.strip():
        raise ValueError("Content is required and cannot be empty")
    if not doc_type or not doc_type.strip():
        raise ValueError("Document type is required and cannot be empty")

    # Trim content and validate it's not empty
    content_trimmed = content.strip()
    if not content_trimmed:
        raise ValueError("Content is empty after trimming whitespace")

    # Validate content can be chunked (pre-check before database operations)
    # This prevents storing documents that can't be processed
    from ingestion.chunker import chunk_text

    test_chunks = chunk_text(content_trimmed)
    if not test_chunks or len(test_chunks) == 0:
        raise ValueError(
            "Content produced no chunks after chunking - content may be too short or invalid"
        )

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Insert document (only after all validations pass)
        doc_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO documents (id, doc_type, service, component, title, content, tags, last_reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                doc_id,
                doc_type,
                service,
                component,
                title,
                content_trimmed,
                json.dumps(tags) if tags else None,
                last_reviewed_at,
            ),
        )

        # Chunk the content (already validated above, but re-chunk for consistency)
        chunks = chunk_text(content_trimmed)

        # Validate chunks are not empty
        empty_chunks = [i for i, chunk in enumerate(chunks) if not chunk or not chunk.strip()]
        if empty_chunks:
            raise ValueError(
                f"Found {len(empty_chunks)} empty chunk(s) at indices: {empty_chunks[:5]}"
            )

        # Prepare chunks with headers for embedding
        chunks_with_headers = []
        from ingestion.embeddings import count_tokens, EMBEDDING_MODEL_LIMITS, DEFAULT_MODEL

        embedding_model = DEFAULT_MODEL
        max_tokens = EMBEDDING_MODEL_LIMITS.get(embedding_model, 8191)

        # Format last_reviewed_at for header
        last_reviewed_str = None
        if last_reviewed_at:
            if isinstance(last_reviewed_at, datetime):
                last_reviewed_str = last_reviewed_at.strftime("%Y-%m-%d")
            else:
                last_reviewed_str = str(last_reviewed_at)

        for chunk in chunks:
            chunk_with_header = add_chunk_header(
                chunk, doc_type, service, component, title, last_reviewed_str
            )
            # Validate token count after adding header
            token_count = count_tokens(chunk_with_header, embedding_model)

            # If chunk with header exceeds limit, split the chunk further
            if token_count > max_tokens:
                # Split chunk by lines to stay under limit
                import tiktoken

                encoding = tiktoken.get_encoding("cl100k_base")

                # Calculate header token count once
                header_only = add_chunk_header(
                    "", doc_type, service, component, title, last_reviewed_str
                )
                header_tokens = count_tokens(header_only, embedding_model)
                available_tokens = max_tokens - header_tokens - 100  # Safety margin

                # Try splitting by lines first
                lines = chunk.split("\n")
                current_subchunk = []
                current_tokens = 0

                for line in lines:
                    line_tokens = len(encoding.encode(line + "\n"))  # Include newline

                    if current_tokens + line_tokens > available_tokens and current_subchunk:
                        # Save current subchunk
                        subchunk_text = "\n".join(current_subchunk)
                        chunks_with_headers.append(
                            add_chunk_header(
                                subchunk_text,
                                doc_type,
                                service,
                                component,
                                title,
                                last_reviewed_str,
                            )
                        )
                        current_subchunk = [line]
                        current_tokens = line_tokens
                    else:
                        current_subchunk.append(line)
                        current_tokens += line_tokens

                # Add final subchunk
                if current_subchunk:
                    subchunk_text = "\n".join(current_subchunk)
                    chunks_with_headers.append(
                        add_chunk_header(
                            subchunk_text, doc_type, service, component, title, last_reviewed_str
                        )
                    )
            else:
                chunks_with_headers.append(chunk_with_header)

        # Validate we have chunks to embed before generating embeddings
        if not chunks_with_headers or len(chunks_with_headers) == 0:
            raise ValueError(
                "No chunks with headers to embed - cannot proceed with embedding generation"
            )

        # Generate embeddings in batches (much faster for large documents)
        # Use batch size of 50 for safety (OpenAI supports up to 2048, but we want to avoid rate limits)
        from ingestion.embeddings import embed_texts_batch

        batch_size = 50 if len(chunks_with_headers) > 10 else len(chunks_with_headers)
        embeddings = embed_texts_batch(
            chunks_with_headers, model=embedding_model, batch_size=batch_size
        )

        # Validate embeddings were generated successfully
        if not embeddings or len(embeddings) != len(chunks_with_headers):
            raise ValueError(
                f"Embedding generation failed: expected {len(chunks_with_headers)} embeddings, "
                f"got {len(embeddings) if embeddings else 0}"
            )

        # Insert chunks with embeddings
        metadata_dict = {
            "doc_type": doc_type,
            "service": service,
            "component": component,
            "title": title,
        }
        for idx, (chunk_with_header, embedding) in enumerate(zip(chunks_with_headers, embeddings)):
            # Convert embedding to string format for pgvector: '[1,2,3,...]'
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"

            # Create tsvector (Postgres will parse it)
            cur.execute(
                """
                INSERT INTO chunks (document_id, chunk_index, content, metadata, embedding, tsv)
                VALUES (%s, %s, %s, %s::jsonb, %s::vector, to_tsvector('english', %s))
                """,
                (
                    doc_id,
                    idx,
                    chunk_with_header,
                    json.dumps(metadata_dict),  # Convert dict to JSON string for JSONB
                    embedding_str,  # pgvector string format
                    create_tsvector(chunk_with_header),
                ),
            )

        conn.commit()
        return str(doc_id)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
