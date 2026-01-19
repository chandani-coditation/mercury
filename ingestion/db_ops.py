"""Database operations for ingestion."""

import uuid
import json
from datetime import datetime
from typing import List, Optional
from db.connection import get_db_connection_context
from ingestion.embeddings import (
    embed_text,
    embed_texts_batch,
    DEFAULT_MODEL,
)
from ingestion.chunker import add_chunk_header
from ingestion.models import RunbookStep, IncidentSignature



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

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
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
                                subchunk_text,
                                doc_type,
                                service,
                                component,
                                title,
                                last_reviewed_str,
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
            # Load batch size from config (graceful degradation if config missing)
            from ingestion.embeddings import embed_texts_batch

            try:
                from ingestion.normalizers import INGESTION_CONFIG

                default_batch_size = INGESTION_CONFIG.get("batch_sizes", {}).get(
                    "embedding_batch", 50
                )
            except Exception:
                default_batch_size = 50  # Fallback to default
            batch_size = (
                default_batch_size if len(chunks_with_headers) > 10 else len(chunks_with_headers)
            )
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
            for idx, (chunk_with_header, embedding) in enumerate(
                zip(chunks_with_headers, embeddings)
            ):
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


def _create_runbook_step_embedding_text(
    step: RunbookStep, prerequisites: Optional[List[str]] = None
) -> str:
    """
    Create embedding text for a runbook step.

    Per architecture: Embeddings represent conditions, failure patterns, and resolution references.
    This text should capture:
    - Condition (when this step applies)
    - Action (what to do)
    - Expected outcome
    - Prerequisites (what must be true before this step)
    - Rollback procedures
    - Failure patterns this addresses
    """
    parts = []

    # Prerequisites - important context for when step applies
    if prerequisites:
        prereq_text = ", ".join(prerequisites)
        parts.append(f"Prerequisites: {prereq_text}")

    # Condition (when this applies) - critical for matching
    if step.condition:
        parts.append(f"Condition: {step.condition}")

    # Action (what to do) - core resolution reference
    parts.append(f"Action: {step.action}")

    # Expected outcome - helps with validation
    if step.expected_outcome:
        parts.append(f"Expected Outcome: {step.expected_outcome}")

    # Rollback - important for safety
    if step.rollback:
        parts.append(f"Rollback: {step.rollback}")

    # Service/component context
    if step.service:
        parts.append(f"Service: {step.service}")
    if step.component:
        parts.append(f"Component: {step.component}")

    return "\n".join(parts)


def _create_incident_signature_embedding_text(
    signature: IncidentSignature,
    incident_title: Optional[str] = None,
    incident_description: Optional[str] = None,
) -> str:
    """
    Create embedding text for an incident signature.


    """
    parts = []

    # ONLY include title and description - this matches what's in the query text
    if incident_title:
        parts.append(incident_title)
    if incident_description:
        # Truncate description to first 1000 chars (increased from 500 for better context)
        # Query text can be long, so we need enough context in embedding
        desc_truncated = incident_description[:1000] + (
            "..." if len(incident_description) > 1000 else ""
        )
        parts.append(desc_truncated)

    # Join with space (same as query text format)
    embedding_text = " ".join(parts).strip()

    return embedding_text


def insert_runbook_with_steps(
    doc_type: str,
    service: Optional[str],
    component: Optional[str],
    title: str,
    content: str,
    tags: dict,
    last_reviewed_at: Optional[datetime],
    steps: List[RunbookStep],
    prerequisites: Optional[List[str]] = None,
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

    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Check if runbook with same title already exists (deduplication)
            cur.execute(
                """
                SELECT id FROM documents 
                WHERE doc_type = 'runbook' AND LOWER(TRIM(title)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                (title,),
            )
            existing_doc = cur.fetchone()

            if existing_doc:
                # Delete existing runbook and its chunks/steps
                existing_doc_id = existing_doc["id"]
                try:
                    from ai_service.core import get_logger

                    logger = get_logger(__name__)
                    logger.info(
                        f"Found existing runbook with title '{title}' (id={existing_doc_id}). Replacing it."
                    )
                except:
                    pass

                # Delete chunks first (CASCADE will handle runbook_steps if they exist)
                cur.execute("DELETE FROM chunks WHERE document_id = %s", (existing_doc_id,))
                # Delete the document
                cur.execute("DELETE FROM documents WHERE id = %s", (existing_doc_id,))
                # Use existing doc_id for replacement
                doc_id = existing_doc_id
            else:
                # New runbook - generate new ID
                doc_id = uuid.uuid4()

            # Insert runbook metadata document
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
                    logger.warning(
                        f"No steps extracted for runbook {title}. Creating fallback step from content."
                    )
                except:
                    pass

                # Create a single fallback step from the full content
                if content and content.strip():
                    # Load max length from config (graceful degradation if config missing)
                    try:
                        from ingestion.normalizers import INGESTION_CONFIG

                        max_action_length = INGESTION_CONFIG.get("formatting", {}).get(
                            "max_fallback_action_length", 2000
                        )
                    except Exception:
                        max_action_length = 2000  # Fallback to default

                    fallback_step = RunbookStep(
                        step_id=f"{tags.get('runbook_id', 'RB-UNKNOWN')}-S1",
                        runbook_id=tags.get("runbook_id", "RB-UNKNOWN"),
                        condition="Runbook applies",
                        action=content.strip()[:max_action_length],  # Limit from config
                        expected_outcome=None,
                        rollback=None,
                        risk_level=None,
                        service=service,
                        component=component,
                    )
                    steps = [fallback_step]
                else:
                    # Even if no content, create a minimal step
                    runbook_id = tags.get("runbook_id", f"RB-{uuid.uuid4().hex[:8].upper()}")
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
                # Create embedding text for this step (include prerequisites from runbook)
                step_text = _create_runbook_step_embedding_text(step, prerequisites=prerequisites)
                step_texts.append(step_text)

            # Generate embeddings for all steps in batch
            embedding_model = DEFAULT_MODEL
            # Load batch size from config (graceful degradation if config missing)
            try:
                from ingestion.normalizers import INGESTION_CONFIG

                default_batch_size = INGESTION_CONFIG.get("batch_sizes", {}).get(
                    "embedding_batch", 50
                )
            except Exception:
                default_batch_size = 50  # Fallback to default
            batch_size = min(default_batch_size, len(step_texts))
            embeddings = embed_texts_batch(step_texts, model=embedding_model, batch_size=batch_size)

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
                logger.info(
                    f"About to insert {len(steps)} steps into runbook_steps table for runbook {title}"
                )
                for i, step in enumerate(steps):
                    logger.debug(
                        f"Step {i+1}: step_id={step.step_id}, condition='{step.condition[:50]}...', action='{step.action[:50]}...'"
                    )
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
                        # Don't commit here - commit all steps and chunks together at the end
                        # This ensures atomicity: either all steps are stored or none
                        try:
                            from ai_service.core import get_logger

                            logger = get_logger(__name__)
                            logger.debug(f"Created chunk for runbook step {step.step_id}")
                        except:
                            pass
                    except Exception as chunk_error:
                        # Log error - chunk creation is critical for retrieval
                        try:
                            from ai_service.core import get_logger

                            logger = get_logger(__name__)
                            logger.error(
                                f"Failed to create chunk for runbook step {step.step_id}: {chunk_error}"
                            )
                        except:
                            pass
                        # Don't re-raise - log and continue with other steps
                        # Chunk creation failure shouldn't prevent step storage
                        continue

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
                            exc_info=True,
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
                    logger.info(
                        f"Successfully inserted {inserted_count}/{len(steps)} steps into runbook_steps table for runbook {title}"
                    )
                else:
                    logger.error(
                        f"Only inserted {inserted_count}/{len(steps)} steps into runbook_steps table for runbook {title}"
                    )
            except:
                pass

            if inserted_count == 0:
                # If no steps were inserted into runbook_steps, fall back to chunks table
                try:
                    from ai_service.core import get_logger

                    logger = get_logger(__name__)
                    logger.warning(
                        f"Failed to insert any steps into runbook_steps table for runbook {title}. Using fallback chunks insertion."
                    )
                except:
                    pass

                # Create a single chunk from the first step as fallback
                if steps:
                    step = steps[0]
                    step_text = _create_runbook_step_embedding_text(step)
                    embedding = embeddings[0] if embeddings else embed_text(step_text)
                    if embedding is None:
                        try:
                            from ai_service.core import get_logger

                            logger = get_logger(__name__)
                            logger.error(
                                f"Failed to generate embedding for fallback chunk. Skipping chunk creation."
                            )
                        except:
                            pass
                        # Skip chunk creation if embedding fails - no chunk will be created
                    else:
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
                logger.info(
                    f"About to commit transaction for runbook {title} with {inserted_count} steps inserted"
                )
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
                logger.error(
                    f"Transaction rolled back for runbook {title}: {str(e)}", exc_info=True
                )
            except:
                pass
            raise e
        finally:
            cur.close()


def insert_incident_signature(
    signature: IncidentSignature,
    source_incident_id: Optional[str] = None,
    source_document_id: Optional[str] = None,
    incident_title: Optional[str] = None,
    incident_description: Optional[str] = None,
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
    # Use context manager to ensure connection is returned to pool
    with get_db_connection_context() as conn:
        cur = conn.cursor()

        try:
            # Clean description to ensure consistency with query text normalization
            from ingestion.normalizers import clean_description_text

            cleaned_description = (
                clean_description_text(incident_description) if incident_description else None
            )

            # Create embedding text for signature (include original title/description for better matching)
            signature_text = _create_incident_signature_embedding_text(
                signature,
                incident_title=incident_title,
                incident_description=cleaned_description,
            )

            # Generate embedding
            embedding_model = DEFAULT_MODEL
            embedding = embed_text(signature_text, model=embedding_model)
            if embedding is None:
                try:
                    from ai_service.core import get_logger

                    logger = get_logger(__name__)
                    logger.error(
                        f"Failed to generate embedding for incident signature {signature.incident_signature_id}. Skipping signature."
                    )
                except:
                    pass
                cur.close()
                raise ValueError(
                    f"Failed to generate embedding for incident signature {signature.incident_signature_id}"
                )
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"

            # Prepare arrays for PostgreSQL
            symptoms_array = signature.symptoms if signature.symptoms else []
            resolution_refs_array = signature.resolution_refs if signature.resolution_refs else []
            source_incident_ids_array = [source_incident_id] if source_incident_id else []

            # Insert signature into incident_signatures table
            # Build tsv text for full-text search - include title/description FIRST for better matching
            # Priority: Original text (title/description) comes first for better fulltext matching
            # IMPORTANT: Clean description to match query normalization during triage
            tsv_text_parts = []
            if incident_title:
                tsv_text_parts.append(incident_title)
            if cleaned_description:
                desc_for_tsv = cleaned_description[:1000]
                tsv_text_parts.append(desc_for_tsv)
            # Then add structured fields
            tsv_text_parts.extend(
                [
                    signature.failure_type or "",
                    signature.error_class or "",
                    signature.assignment_group or "",
                    signature.impact or "",
                    signature.urgency or "",
                    " ".join(signature.symptoms) if signature.symptoms else "",
                ]
            )
            tsv_text = " ".join([p for p in tsv_text_parts if p]).strip()

            signature_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO incident_signatures (
                    id, incident_signature_id, failure_type, error_class, symptoms,
                    affected_service, service, component, assignment_group, impact, urgency, close_notes, resolution_refs, embedding,
                    source_incident_ids, source_document_id, last_seen_at, tsv
                )
                VALUES (%s, %s, %s, %s, %s::TEXT[], %s, %s, %s, %s, %s, %s, %s, %s::TEXT[], %s::vector, %s::TEXT[], %s, %s, to_tsvector('english', %s))
                ON CONFLICT (incident_signature_id) DO UPDATE SET
                    failure_type = EXCLUDED.failure_type,
                    error_class = EXCLUDED.error_class,
                    symptoms = EXCLUDED.symptoms,
                    affected_service = COALESCE(EXCLUDED.affected_service, incident_signatures.affected_service),
                    service = COALESCE(EXCLUDED.service, incident_signatures.service),
                    component = COALESCE(EXCLUDED.component, incident_signatures.component),
                    -- Aggregate assignment_group, impact, urgency using most common value from all tickets
                    -- Use a subquery to find the mode (most common value) from source_incident_ids
                    -- For now, keep existing value to prevent overwriting with wrong values from later tickets
                    -- TODO: Implement proper aggregation using arrays to track all values and calculate mode
                    assignment_group = COALESCE(
                        incident_signatures.assignment_group,
                        EXCLUDED.assignment_group
                    ),
                    impact = COALESCE(
                        incident_signatures.impact,
                        EXCLUDED.impact
                    ),
                    urgency = COALESCE(
                        incident_signatures.urgency,
                        EXCLUDED.urgency
                    ),
                    close_notes = COALESCE(EXCLUDED.close_notes, incident_signatures.close_notes),
                    resolution_refs = EXCLUDED.resolution_refs,
                    embedding = EXCLUDED.embedding,
                    source_incident_ids = array_cat(incident_signatures.source_incident_ids, EXCLUDED.source_incident_ids),
                    source_document_id = COALESCE(EXCLUDED.source_document_id, incident_signatures.source_document_id),
                    last_seen_at = EXCLUDED.last_seen_at,
                    match_count = incident_signatures.match_count + 1,
                    updated_at = now(),
                    tsv = to_tsvector('english', 
                        COALESCE(%s, '') || ' ' ||  -- incident_title (first for better matching)
                        COALESCE(%s, '') || ' ' ||  -- incident_description (first for better matching)
                        COALESCE(EXCLUDED.failure_type, '') || ' ' || 
                        COALESCE(EXCLUDED.error_class, '') || ' ' || 
                        COALESCE(EXCLUDED.assignment_group, '') || ' ' ||
                        COALESCE(EXCLUDED.impact, '') || ' ' ||
                        COALESCE(EXCLUDED.urgency, '') || ' ' ||
                        COALESCE(array_to_string(EXCLUDED.symptoms, ' '), '')
                    )
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
                    signature.assignment_group,
                    signature.impact,
                    signature.urgency,
                    signature.close_notes,
                    resolution_refs_array,
                    embedding_str,
                    source_incident_ids_array,
                    source_document_id,
                    datetime.now(),  # last_seen_at
                    tsv_text,  # tsv text for full-text search
                    incident_title or "",  # For ON CONFLICT UPDATE (tsv - first param)
                    (
                        clean_description_text(incident_description)[:1000]
                        if incident_description
                        else ""
                    ),  # For ON CONFLICT UPDATE (tsv - second param, cleaned and truncated)
                ),
            )

            conn.commit()

            return str(signature_id)

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
