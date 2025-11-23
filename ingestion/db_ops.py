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
    last_reviewed_at: datetime = None
) -> str:
    """
    Insert document and its chunks into database.
    
    Returns:
        Document ID (UUID as string)
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Insert document
        doc_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO documents (id, doc_type, service, component, title, content, tags, last_reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (doc_id, doc_type, service, component, title, content, json.dumps(tags) if tags else None, last_reviewed_at)
        )
        
        # Chunk the content
        chunks = chunk_text(content)
        
        # Prepare chunks with headers for embedding
        chunks_with_headers = []
        from ingestion.embeddings import count_tokens, EMBEDDING_MODEL_LIMITS
        max_tokens = EMBEDDING_MODEL_LIMITS.get("text-embedding-3-small", 8191)
        
        for chunk in chunks:
            chunk_with_header = add_chunk_header(chunk, doc_type, service, component, title)
            # Validate token count after adding header
            token_count = count_tokens(chunk_with_header, "text-embedding-3-small")
            
            # If chunk with header exceeds limit, split the chunk further
            if token_count > max_tokens:
                # Split chunk by lines to stay under limit
                import tiktoken
                encoding = tiktoken.get_encoding("cl100k_base")
                
                # Calculate header token count once
                header_only = add_chunk_header("", doc_type, service, component, title)
                header_tokens = count_tokens(header_only, "text-embedding-3-small")
                available_tokens = max_tokens - header_tokens - 100  # Safety margin
                
                # Try splitting by lines first
                lines = chunk.split('\n')
                current_subchunk = []
                current_tokens = 0
                
                for line in lines:
                    line_tokens = len(encoding.encode(line + '\n'))  # Include newline
                    
                    if current_tokens + line_tokens > available_tokens and current_subchunk:
                        # Save current subchunk
                        subchunk_text = '\n'.join(current_subchunk)
                        chunks_with_headers.append(add_chunk_header(subchunk_text, doc_type, service, component, title))
                        current_subchunk = [line]
                        current_tokens = line_tokens
                    else:
                        current_subchunk.append(line)
                        current_tokens += line_tokens
                
                # Add final subchunk
                if current_subchunk:
                    subchunk_text = '\n'.join(current_subchunk)
                    chunks_with_headers.append(add_chunk_header(subchunk_text, doc_type, service, component, title))
            else:
                chunks_with_headers.append(chunk_with_header)
        
        # Generate embeddings in batches (much faster for large documents)
        # Use batch size of 50 for safety (OpenAI supports up to 2048, but we want to avoid rate limits)
        from ingestion.embeddings import embed_texts_batch
        batch_size = 50 if len(chunks_with_headers) > 10 else len(chunks_with_headers)
        embeddings = embed_texts_batch(chunks_with_headers, batch_size=batch_size)
        
        # Insert chunks with embeddings
        metadata_dict = {"doc_type": doc_type, "service": service, "component": component, "title": title}
        for idx, (chunk_with_header, embedding) in enumerate(zip(chunks_with_headers, embeddings)):
            # Convert embedding to string format for pgvector: '[1,2,3,...]'
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            
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
                    create_tsvector(chunk_with_header)
                )
            )
        
        conn.commit()
        return str(doc_id)
    
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

