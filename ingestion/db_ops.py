"""Database operations for ingestion."""

import uuid
import json
from datetime import datetime
from typing import List, Optional
from db.connection import get_db_connection
from ingestion.embeddings import embed_text, embed_texts_batch, count_tokens, EMBEDDING_MODEL_LIMITS, DEFAULT_MODEL
from ingestion.chunker import chunk_text, add_chunk_header
from ingestion.models import RunbookStep, IncidentSignature

# Lazy import to avoid circular dependency
def get_logger(name):
    from ai_service.core import get_logger as _get_logger
    return _get_logger(name)


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


def _create_runbook_step_embedding_text(step: RunbookStep) -> str:
    """
    Create embedding text for a runbook step.
    
    Per architecture: Embeddings represent conditions, failure patterns, and resolution references.
    This text should capture:
    - Condition (when this step applies)
    - Action (what to do)
    - Expected outcome
    - Failure patterns this addresses
    """
    parts = []
    
    # Condition (when this applies) - critical for matching
    if step.condition:
        parts.append(f"Condition: {step.condition}")
    
    # Action (what to do) - core resolution reference
    parts.append(f"Action: {step.action}")
    
    # Expected outcome - helps with validation
    if step.expected_outcome:
        parts.append(f"Expected Outcome: {step.expected_outcome}")
    
    # Risk level - important for decision making
    if step.risk_level:
        parts.append(f"Risk Level: {step.risk_level}")
    
    # Rollback - important for safety
    if step.rollback:
        parts.append(f"Rollback: {step.rollback}")
    
    # Service/component context
    if step.service:
        parts.append(f"Service: {step.service}")
    if step.component:
        parts.append(f"Component: {step.component}")
    
    return "\n".join(parts)


def _create_incident_signature_embedding_text(signature: IncidentSignature) -> str:
    """
    Create embedding text for an incident signature.
    
    Per architecture: Embeddings represent conditions, failure patterns, and resolution references.
    This text should capture:
    - Failure type (condition)
    - Error class (failure pattern)
    - Symptoms (failure patterns)
    - Resolution references
    """
    parts = []
    
    # Failure type - condition for matching
    parts.append(f"Failure Type: {signature.failure_type}")
    
    # Error class - failure pattern
    parts.append(f"Error Class: {signature.error_class}")
    
    # Symptoms - failure patterns
    if signature.symptoms:
        symptoms_text = ", ".join(signature.symptoms)
        parts.append(f"Symptoms: {symptoms_text}")
    
    # Resolution references - links to runbook steps
    if signature.resolution_refs:
        refs_text = ", ".join(signature.resolution_refs)
        parts.append(f"Resolution References: {refs_text}")
    
    # Service/component context
    if signature.service:
        parts.append(f"Service: {signature.service}")
    if signature.component:
        parts.append(f"Component: {signature.component}")
    if signature.affected_service:
        parts.append(f"Affected Service: {signature.affected_service}")
    
    return "\n".join(parts)


def insert_runbook_with_steps(
    doc_type: str,
    service: Optional[str],
    component: Optional[str],
    title: str,
    content: str,
    tags: dict,
    last_reviewed_at: Optional[datetime],
    steps: List[RunbookStep],
) -> str:
    """
    Insert runbook metadata and atomic steps into database.
    
    Per architecture:
    - Runbook metadata goes in documents table
    - Each step is stored as an atomic chunk (not chunked further)
    - Each step is embedded independently
    
    Args:
        doc_type: Document type (should be "runbook")
        service: Service name
        component: Component name
        title: Runbook title
        content: Runbook metadata content (not steps)
        tags: Document tags
        last_reviewed_at: Last review timestamp
        steps: List of atomic runbook steps
        
    Returns:
        Document ID (UUID as string)
    """
    if not title or not title.strip():
        raise ValueError("Title is required and cannot be empty")
    if not doc_type or not doc_type.strip():
        raise ValueError("Document type is required and cannot be empty")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Insert runbook metadata document
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
                content or "",  # Metadata content can be empty
                json.dumps(tags) if tags else None,
                last_reviewed_at,
            ),
        )
        
        if not steps:
            # No steps extracted - create a fallback step from content
            try:
                from ai_service.core import get_logger
                logger = get_logger(__name__)
                logger.warning(f"No steps extracted for runbook {title}. Creating fallback step from content.")
            except:
                pass
            
            # Create a single fallback step from the full content
            if content and content.strip():
                fallback_step = RunbookStep(
                    step_id=f"{tags.get('runbook_id', 'RB-UNKNOWN')}-S1",
                    runbook_id=tags.get('runbook_id', 'RB-UNKNOWN'),
                    condition="Runbook applies",
                    action=content.strip()[:2000],  # Limit to 2000 chars
                    expected_outcome=None,
                    rollback=None,
                    risk_level=None,
                    service=service,
                    component=component,
                )
                steps = [fallback_step]
            else:
                # Even if no content, create a minimal step
                runbook_id = tags.get('runbook_id', f"RB-{uuid.uuid4().hex[:8].upper()}")
                fallback_step = RunbookStep(
                    step_id=f"{runbook_id}-S1",
                    runbook_id=runbook_id,
                    condition="Runbook applies",
                    action=title,  # Use title as action
                    expected_outcome=None,
                    rollback=None,
                    risk_level=None,
                    service=service,
                    component=component,
                )
                steps = [fallback_step]
        
        # Log step extraction
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.info(f"Inserting {len(steps)} steps for runbook {title} (doc_id={doc_id})")
        except:
            pass
        
        # Prepare step texts for embedding
        step_texts = []
        
        for step in steps:
            # Create embedding text for this step
            step_text = _create_runbook_step_embedding_text(step)
            step_texts.append(step_text)
        
        # Generate embeddings for all steps in batch
        embedding_model = DEFAULT_MODEL
        batch_size = min(50, len(step_texts))
        embeddings = embed_texts_batch(
            step_texts, model=embedding_model, batch_size=batch_size
        )
        
        if not embeddings or len(embeddings) != len(step_texts):
            raise ValueError(
                f"Embedding generation failed: expected {len(step_texts)} embeddings, "
                f"got {len(embeddings) if embeddings else 0}"
            )
        
        # Insert each step into runbook_steps table
        inserted_count = 0
        
        # Log the steps we're about to insert
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.info(f"About to insert {len(steps)} steps into runbook_steps table for runbook {title}")
            for i, step in enumerate(steps):
                logger.debug(f"Step {i+1}: step_id={step.step_id}, condition='{step.condition[:50]}...', action='{step.action[:50]}...'")
        except:
            pass
        
        for step, embedding in zip(steps, embeddings):
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            
            # Use step's service/component or fall back to runbook-level values
            step_service = step.service or service
            step_component = step.component or component
            
            try:
                # Log the step being inserted for debugging
                try:
                    from ai_service.core import get_logger
                    logger = get_logger(__name__)
                    logger.debug(f"Inserting step {step.step_id} for runbook {title}")
                except:
                    pass
                
                cur.execute(
                    """
                    INSERT INTO runbook_steps (
                        step_id, runbook_id, condition, action, expected_outcome,
                        rollback, risk_level, service, component, embedding,
                        runbook_title, runbook_document_id, last_reviewed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
                    ON CONFLICT (step_id) DO UPDATE SET
                        condition = EXCLUDED.condition,
                        action = EXCLUDED.action,
                        expected_outcome = EXCLUDED.expected_outcome,
                        rollback = EXCLUDED.rollback,
                        risk_level = EXCLUDED.risk_level,
                        service = EXCLUDED.service,
                        component = EXCLUDED.component,
                        embedding = EXCLUDED.embedding,
                        runbook_title = EXCLUDED.runbook_title,
                        runbook_document_id = EXCLUDED.runbook_document_id,
                        updated_at = now()
                    """,
                    (
                        step.step_id,
                        step.runbook_id,
                        step.condition,
                        step.action,
                        step.expected_outcome,
                        step.rollback,
                        step.risk_level,
                        step_service,
                        step_component,
                        embedding_str,
                        title,  # runbook_title
                        doc_id,  # runbook_document_id
                        last_reviewed_at,
                    ),
                )
                inserted_count += 1
                
                # NOTE: Chunk creation for runbook steps is NO LONGER NEEDED for triage
                # Triage retrieval only needs runbook metadata (from documents table)
                # Runbook steps are retrieved by Resolution Agent, which may use chunks
                # For now, keeping step chunking for Resolution Agent compatibility
                try:
                    # Create metadata for chunk
                    chunk_metadata = {
                        "step_id": step.step_id,
                        "runbook_id": step.runbook_id,
                        "condition": step.condition,
                        "action": step.action,
                        "expected_outcome": step.expected_outcome,
                        "rollback": step.rollback,
                        "risk_level": step.risk_level,
                        "service": step_service,
                        "component": step_component,
                        "runbook_title": title,
                    }
                    
                    # Insert chunk with step data
                    chunk_id = uuid.uuid4()
                    cur.execute(
                        """
                        INSERT INTO chunks (id, document_id, chunk_index, content, metadata, embedding, tsv)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector, to_tsvector('english', %s))
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            chunk_id,
                            doc_id,
                            inserted_count - 1,  # Use step index as chunk_index
                            step_text,  # Content is the embedding text
                            json.dumps(chunk_metadata),
                            embedding_str,
                            step_text,
                        ),
                    )
                    # Commit chunk creation
                    conn.commit()
                    logger = get_logger(__name__)
                    logger.debug(f"Created chunk for runbook step {step.step_id}")
                except Exception as chunk_error:
                    # Log error - chunk creation is critical for retrieval
                    logger = get_logger(__name__)
                    logger.error(f"Failed to create chunk for runbook step {step.step_id}: {chunk_error}")
                    # Re-raise to ensure we know about the failure
                    raise RuntimeError(f"Chunk creation failed for runbook step {step.step_id}: {chunk_error}") from chunk_error
                
                # Log successful insertion
                try:
                    from ai_service.core import get_logger
                    logger = get_logger(__name__)
                    logger.debug(f"Successfully inserted step {step.step_id}")
                except:
                    pass
                    
            except Exception as step_error:
                # Log error with full details and step data
                try:
                    from ai_service.core import get_logger
                    logger = get_logger(__name__)
                    logger.error(
                        f"Error inserting step {step.step_id} into runbook_steps table: {str(step_error)}. "
                        f"Step data: runbook_id={step.runbook_id}, condition='{step.condition[:100]}', "
                        f"action='{step.action[:100]}', service={step_service}, component={step_component}",
                        exc_info=True
                    )
                except:
                    pass
                # Don't re-raise - continue with other steps and use fallback
                continue
        
        # Log insertion results
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            if inserted_count == len(steps):
                logger.info(f"Successfully inserted {inserted_count}/{len(steps)} steps into runbook_steps table for runbook {title}")
            else:
                logger.error(f"Only inserted {inserted_count}/{len(steps)} steps into runbook_steps table for runbook {title}")
        except:
            pass
        
        if inserted_count == 0:
            # If no steps were inserted into runbook_steps, fall back to chunks table
            try:
                from ai_service.core import get_logger
                logger = get_logger(__name__)
                logger.warning(f"Failed to insert any steps into runbook_steps table for runbook {title}. Using fallback chunks insertion.")
            except:
                pass
            
            # Create a single chunk from the first step as fallback
            if steps:
                step = steps[0]
                step_text = _create_runbook_step_embedding_text(step)
                embedding = embeddings[0] if embeddings else embed_text(step_text)
                embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                
                metadata_dict = {
                    "doc_type": "runbook_step",
                    "step_id": step.step_id,
                    "runbook_id": step.runbook_id,
                    "condition": step.condition,
                    "action": step.action,
                    "service": step.service or service,
                    "component": step.component or component,
                    "title": title,
                }
                
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, chunk_index, content, metadata, embedding, tsv)
                    VALUES (%s, %s, %s, %s::jsonb, %s::vector, to_tsvector('english', %s))
                    """,
                    (
                        doc_id,
                        0,
                        step_text,
                        json.dumps(metadata_dict),
                        embedding_str,
                        step_text,
                    ),
                )
                
                try:
                    from ai_service.core import get_logger
                    logger = get_logger(__name__)
                    logger.info(f"Inserted fallback chunk for runbook {title}")
                except:
                    pass
        
        # Log before commit
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.info(f"About to commit transaction for runbook {title} with {inserted_count} steps inserted")
        except:
            pass
        
        conn.commit()
        
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.info(f"Successfully committed runbook {title} with {inserted_count} steps")
        except:
            pass
        
        return str(doc_id)
    
    except Exception as e:
        conn.rollback()
        try:
            from ai_service.core import get_logger
            logger = get_logger(__name__)
            logger.error(f"Transaction rolled back for runbook {title}: {str(e)}", exc_info=True)
        except:
            pass
        raise e
    finally:
        cur.close()
        conn.close()


def insert_incident_signature(
    signature: IncidentSignature,
    source_incident_id: Optional[str] = None,
    source_document_id: Optional[str] = None,
) -> str:
    """
    Insert incident signature into incident_signatures table.
    
    Per architecture:
    - Incident signatures are stored in dedicated incident_signatures table
    - Each signature represents a failure pattern, not raw incident text
    - Embeddings represent conditions, failure patterns, and resolution references
    
    Args:
        signature: IncidentSignature object
        source_incident_id: Optional source incident ID for tracking
        source_document_id: Optional source document ID for tracking
        
    Returns:
        Signature ID (UUID as string)
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Create embedding text for signature
        signature_text = _create_incident_signature_embedding_text(signature)
        
        # Generate embedding
        embedding_model = DEFAULT_MODEL
        embedding = embed_text(signature_text, model=embedding_model)
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        # Prepare arrays for PostgreSQL
        symptoms_array = signature.symptoms if signature.symptoms else []
        resolution_refs_array = signature.resolution_refs if signature.resolution_refs else []
        source_incident_ids_array = [source_incident_id] if source_incident_id else []
        
        # Insert signature into incident_signatures table
        signature_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO incident_signatures (
                id, incident_signature_id, failure_type, error_class, symptoms,
                affected_service, service, component, resolution_refs, embedding,
                source_incident_ids, source_document_id, last_seen_at
            )
            VALUES (%s, %s, %s, %s, %s::TEXT[], %s, %s, %s, %s::TEXT[], %s::vector, %s::TEXT[], %s, %s)
            ON CONFLICT (incident_signature_id) DO UPDATE SET
                failure_type = EXCLUDED.failure_type,
                error_class = EXCLUDED.error_class,
                symptoms = EXCLUDED.symptoms,
                affected_service = EXCLUDED.affected_service,
                service = EXCLUDED.service,
                component = EXCLUDED.component,
                resolution_refs = EXCLUDED.resolution_refs,
                embedding = EXCLUDED.embedding,
                source_incident_ids = array_cat(incident_signatures.source_incident_ids, EXCLUDED.source_incident_ids),
                source_document_id = COALESCE(EXCLUDED.source_document_id, incident_signatures.source_document_id),
                last_seen_at = EXCLUDED.last_seen_at,
                match_count = incident_signatures.match_count + 1,
                updated_at = now()
            """,
            (
                signature_id,
                signature.incident_signature_id,
                signature.failure_type,
                signature.error_class,
                symptoms_array,
                signature.affected_service,
                signature.service,
                signature.component,
                resolution_refs_array,
                embedding_str,
                source_incident_ids_array,
                source_document_id,
                datetime.now(),  # last_seen_at
            ),
        )
        
        conn.commit()
        
        # NOTE: Chunk creation is NO LONGER NEEDED
        # Triage retrieval now queries incident_signatures table directly
        # (embeddings and tsvector are already in incident_signatures table)
        # Keeping this code commented for reference, but it's not executed
        # 
        # try:
            # Create embedding text for chunk (same as signature)
            chunk_content = signature_text
            
            # Create metadata for chunk
            chunk_metadata = {
                "incident_signature_id": signature.incident_signature_id,
                "failure_type": signature.failure_type,
                "error_class": signature.error_class,
                "symptoms": signature.symptoms,
                "affected_service": signature.affected_service,
                "service": signature.service,
                "component": signature.component,
                "source_incident_ids": source_incident_ids_array,
            }
            
            # Create or get document for this signature (optional, for metadata)
            doc_id = source_document_id
            if not doc_id:
                # Create a minimal document for the signature
                doc_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO documents (id, doc_type, service, component, title, content, tags, last_reviewed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        doc_id,
                        "incident_signature",
                        signature.service,
                        signature.component,
                        f"Incident Signature: {signature.incident_signature_id}",
                        "",  # Empty content - signature data is in chunk
                        json.dumps({
                            "incident_signature_id": signature.incident_signature_id,
                            "failure_type": signature.failure_type,
                            "error_class": signature.error_class,
                        }),
                        datetime.now(),
                    ),
                )
            
            # Insert chunk with signature data
            chunk_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO chunks (id, document_id, chunk_index, content, metadata, embedding, tsv)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector, to_tsvector('english', %s))
                ON CONFLICT DO NOTHING
                """,
                (
                    chunk_id,
                    doc_id,
                    0,  # Single chunk per signature
                    chunk_content,
                    json.dumps(chunk_metadata),
                    embedding_str,
                    chunk_content,
                ),
            )
            
            # conn.commit()
            # logger = get_logger(__name__)
            # logger.info(f"Created chunk for incident signature {signature.incident_signature_id}")
        # except Exception as chunk_error:
        #     # Log error - chunk creation is critical for retrieval
        #     logger = get_logger(__name__)
        #     logger.error(f"Failed to create chunk for signature {signature.incident_signature_id}: {chunk_error}")
        #     # Re-raise to ensure we know about the failure
        #     raise RuntimeError(f"Chunk creation failed for signature {signature.incident_signature_id}: {chunk_error}") from chunk_error
        
        return str(signature_id)
    
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
