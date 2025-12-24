#!/usr/bin/env python3
"""Ingest runbooks from DOCX files.

This script extracts text content from DOCX files in the runbooks/ folder
and ingests them using JSON schema-driven extraction and field mappings configuration.

Usage:
    python scripts/data/ingest_runbooks.py --dir runbooks
    python scripts/data/ingest_runbooks.py --file "runbooks/Runbook - Database Alerts.docx"
"""
import argparse
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table
from docx.text.paragraph import Paragraph

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ai_service.core import get_field_mappings_config, get_logger, setup_logging
from ingestion.models import IngestRunbook
import requests

# Default ingestion service URL
INGESTION_SERVICE_URL = "http://localhost:8002"


def clean_text(text: str) -> str:
    """Clean text by removing formatting artifacts and special characters."""
    if not text:
        return ""
    
    # Remove common formatting artifacts
    text = text.replace("¶", "")  # Remove paragraph markers
    text = text.replace("", "")  # Remove zero-width spaces
    text = text.replace("\u200b", "")  # Remove zero-width spaces (Unicode)
    text = text.replace("\xa0", " ")  # Replace non-breaking spaces with regular spaces
    
    # Remove markdown-style heading markers at the start
    text = text.lstrip("#").strip()
    
    # Remove multiple consecutive spaces
    while "  " in text:
        text = text.replace("  ", " ")
    
    # Remove multiple consecutive newlines
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    
    return text.strip()


def extract_text_from_docx(docx_path: Path) -> Dict[str, any]:
    """Extract structured content from DOCX file.
    
    Returns dict with: title, steps, commands, prerequisites, rollback_procedures, content
    """
    doc = Document(docx_path)
    
    # Extract title (usually first paragraph or document property)
    title = docx_path.stem  # Default to filename
    if doc.paragraphs:
        first_para = clean_text(doc.paragraphs[0].text)
        if first_para and len(first_para) < 200:  # Likely a title
            title = first_para
    
    # Clean the title
    title = clean_text(title)
    
    # Extract all text content
    full_content_parts = []
    steps = []
    commands = []
    prerequisites = []
    rollback_procedures = []
    
    current_section = None
    
    for element in doc.element.body:
        if isinstance(element, CT_P):
            para = Paragraph(element, doc)
            text = clean_text(para.text)
            
            if not text:
                continue
            
            # Detect section headers (usually bold or all caps)
            is_header = False
            for run in para.runs:
                if run.bold or text.isupper():
                    is_header = True
                    break
            
            if is_header:
                text_lower = text.lower()
                if "step" in text_lower or "procedure" in text_lower:
                    current_section = "steps"
                elif "command" in text_lower or "cmd" in text_lower:
                    current_section = "commands"
                elif "prerequisite" in text_lower or "requirement" in text_lower:
                    current_section = "prerequisites"
                elif "rollback" in text_lower or "revert" in text_lower:
                    current_section = "rollback"
                else:
                    current_section = None
                
                # Add header without markdown markers
                full_content_parts.append(f"\n{text.upper()}\n{'='*len(text)}\n")
            else:
                # Add to appropriate section
                if current_section == "steps":
                    steps.append(text)
                    full_content_parts.append(f"  • {text}\n")
                elif current_section == "commands":
                    # Commands might be in code blocks or plain text
                    if text.startswith("$") or text.startswith("#") or "sudo" in text or "kubectl" in text:
                        commands.append(text)
                    full_content_parts.append(f"  $ {text}\n")
                elif current_section == "prerequisites":
                    prerequisites.append(text)
                    full_content_parts.append(f"  • {text}\n")
                elif current_section == "rollback":
                    rollback_procedures.append(text)
                    full_content_parts.append(f"  • {text}\n")
                else:
                    full_content_parts.append(f"{text}\n")
        
        elif isinstance(element, CT_Tbl):
            # Extract text from tables
            table = Table(element, doc)
            for row in table.rows:
                row_text = " | ".join([clean_text(cell.text) for cell in row.cells])
                if row_text:
                    full_content_parts.append(f"{row_text}\n")
    
    full_content = "".join(full_content_parts)
    
    return {
        "title": title,
        "steps": steps,
        "commands": commands,
        "prerequisites": prerequisites,
        "rollback_procedures": "\n".join(rollback_procedures) if rollback_procedures else None,
        "content": full_content
    }


def map_docx_to_runbook(docx_path: Path, field_mappings: Dict) -> IngestRunbook:
    """Map DOCX content to IngestRunbook using field mappings configuration."""
    # Extract structured content
    extracted = extract_text_from_docx(docx_path)
    
    # Use field mappings to determine which fields to use
    mappings = field_mappings.get("field_mappings", {})
    
    # Extract service/component from filename or content (if available)
    service = None
    component = None
    
    # Try to extract from filename with smart pattern matching
    filename_clean = docx_path.stem.replace("Runbook -", "").replace("Runbook –", "").strip()
    filename_lower = filename_clean.lower()
    
    # Pattern matching for common runbook types
    if "database" in filename_lower or "sql" in filename_lower or "db" in filename_lower:
        service = "Database"
        component = filename_clean.replace("Database", "").replace("database", "").strip()
    elif "network" in filename_lower:
        service = "Network"
        component = filename_clean.replace("Network", "").replace("network", "").strip()
    elif "cpu" in filename_lower:
        service = "Infrastructure"
        component = filename_clean
    elif "memory" in filename_lower or "ram" in filename_lower:
        service = "Infrastructure"
        component = filename_clean
    elif "disk" in filename_lower or "volume" in filename_lower or "storage" in filename_lower:
        service = "Storage"
        component = filename_clean
    elif "high" in filename_lower:
        # Generic "High" alerts - categorize as Infrastructure
        service = "Infrastructure"
        component = filename_clean
    else:
        # Fallback: split by spaces
        filename_parts = filename_clean.split()
        if len(filename_parts) >= 2:
            service = filename_parts[0]
            component = " ".join(filename_parts[1:])
        else:
            service = filename_parts[0] if filename_parts else "General"
            component = None
    
    # Clean up component (remove trailing words like "Alerts")
    if component:
        component = component.strip()
        # Normalize common suffixes
        if component.endswith(" Alerts"):
            component = component.replace(" Alerts", "").strip() or "Alerts"
    
    # Build comprehensive tags
    runbook_id = str(uuid.uuid4())
    tags = {
        "type": "runbook",
        "runbook_id": runbook_id,
        "source_file": docx_path.name,
    }
    
    if service:
        tags["service"] = service
    if component:
        tags["component"] = component
    
    # Build metadata
    metadata = {
        "source": "docx",
        "file_path": str(docx_path),
        "has_steps": len(extracted["steps"]) > 0,
        "has_commands": len(extracted["commands"]) > 0,
        "has_rollback": extracted["rollback_procedures"] is not None,
    }
    
    return IngestRunbook(
        title=extracted["title"],
        service=service,
        component=component,
        content=extracted["content"],
        steps=extracted["steps"] if extracted["steps"] else None,
        prerequisites=extracted["prerequisites"] if extracted["prerequisites"] else None,
        rollback_procedures=extracted["rollback_procedures"],
        tags=tags,
        metadata=metadata
    )


def ingest_runbook(runbook: IngestRunbook, ingestion_url: str = INGESTION_SERVICE_URL) -> tuple[bool, Optional[str]]:
    """Ingest a single runbook via the ingestion API.
    
    Returns:
        Tuple of (success: bool, document_id: Optional[str])
    """
    logger = get_logger(__name__)
    try:
        response = requests.post(
            f"{ingestion_url}/ingest/runbook",
            json=runbook.model_dump(mode="json", exclude_none=True),
            timeout=60  # Longer timeout for larger files
        )
        response.raise_for_status()
        result = response.json()
        document_id = result.get("document_id")
        return True, document_id
    except Exception as e:
        logger.error(f"Failed to ingest runbook {runbook.title}: {str(e)}")
        return False, None


def ingest_docx_file(file_path: Path, field_mappings: Dict, ingestion_url: str, file_num: int = None, total_files: int = None) -> tuple[int, int]:
    """Ingest a single DOCX file."""
    logger = get_logger(__name__)
    file_info = f"[{file_num}/{total_files}] " if file_num and total_files else ""
    print(f"  {file_info}Processing: {file_path.name}")
    logger.info(f"Processing DOCX file: {file_path}")
    
    try:
        runbook = map_docx_to_runbook(file_path, field_mappings)
        title_preview = (runbook.title[:50] + "...") if len(runbook.title) > 50 else runbook.title
        print(f"    Title: {title_preview}")
        
        success, document_id = ingest_runbook(runbook, ingestion_url)
        
        if success:
            print(f"     Successfully ingested (document_id: {document_id})")
            logger.info(f"   Ingested: {runbook.title} (document_id: {document_id})")
            return 1, 0
        else:
            print(f"     Failed to ingest runbook")
            logger.error(f"   Failed to ingest: {runbook.title}")
            return 0, 1
            
    except Exception as e:
        error_msg = f"Error processing {file_path.name}: {str(e)}"
        print(f"     {error_msg}")
        logger.error(error_msg)
        return 0, 1


def main():
    # Setup logging first to ensure output is visible
    setup_logging(log_level="INFO", service_name="ingestion_script")
    logger = get_logger(__name__)
    
    parser = argparse.ArgumentParser(description="Ingest runbooks from DOCX files")
    parser.add_argument("--dir", type=str, help="Directory containing DOCX files")
    parser.add_argument("--file", type=str, help="Single DOCX file to ingest")
    parser.add_argument("--ingestion-url", type=str, default=INGESTION_SERVICE_URL,
                       help=f"Ingestion service URL (default: {INGESTION_SERVICE_URL})")
    
    args = parser.parse_args()
    
    if not args.dir and not args.file:
        parser.error("Either --dir or --file must be provided")
    
    # Print startup message
    print("=" * 70)
    print("Runbook Ingestion Script")
    print("=" * 70)
    logger.info("Starting runbook ingestion...")
    
    # Load field mappings configuration
    try:
        print(" Loading field mappings configuration...")
        field_mappings_config = get_field_mappings_config()
        runbook_mappings = field_mappings_config.get("runbook_docx", {})
        print(" Configuration loaded successfully\n")
    except Exception as e:
        print(f" Failed to load field mappings: {str(e)}")
        logger.error(f"Failed to load field mappings: {str(e)}")
        sys.exit(1)
    
    total_success = 0
    total_errors = 0
    
    if args.file:
        # Process single file
        file_path = Path(args.file)
        if not file_path.exists():
            print(f" File not found: {file_path}")
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        
        if not file_path.suffix.lower() == ".docx":
            print(f" File is not a DOCX file: {file_path}")
            logger.error(f"File is not a DOCX file: {file_path}")
            sys.exit(1)
        
        success, errors = ingest_docx_file(file_path, runbook_mappings, args.ingestion_url)
        total_success += success
        total_errors += errors
    
    else:
        # Process directory
        dir_path = Path(args.dir)
        if not dir_path.exists():
            print(f" Directory not found: {dir_path}")
            logger.error(f"Directory not found: {dir_path}")
            sys.exit(1)
        
        docx_files = list(dir_path.glob("*.docx"))
        if not docx_files:
            print(f"  No DOCX files found in {dir_path}")
            logger.warning(f"No DOCX files found in {dir_path}")
            sys.exit(0)
        
        print(f"\n📁 Found {len(docx_files)} DOCX file(s) to process\n")
        logger.info(f"Found {len(docx_files)} DOCX file(s)")
        
        for idx, docx_file in enumerate(docx_files, start=1):
            success, errors = ingest_docx_file(docx_file, runbook_mappings, args.ingestion_url, idx, len(docx_files))
            total_success += success
            total_errors += errors
    
    print(f"\n{'='*70}")
    print(f"Ingestion Summary:")
    print(f"   Successfully ingested: {total_success} runbook(s)")
    print(f"   Errors: {total_errors} runbook(s)")
    print(f"{'='*70}")
    logger.info(f"\n{'='*70}")
    logger.info(f"Ingestion Summary:")
    logger.info(f"   Successfully ingested: {total_success} runbook(s)")
    logger.info(f"   Errors: {total_errors} runbook(s)")
    logger.info(f"{'='*70}")
    
    # Verify embeddings were created
    if total_success > 0:
        print("\n Verifying embeddings in database...")
        logger.info("\nVerifying embeddings in database...")
        try:
            from db.connection import get_db_connection
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Count documents
            cur.execute("SELECT COUNT(*) as doc_count FROM documents WHERE doc_type = %s", ('runbook',))
            doc_result = cur.fetchone()
            doc_count = doc_result['doc_count'] if isinstance(doc_result, dict) else doc_result[0]
            
            # Count chunks
            cur.execute("""
                SELECT COUNT(*) as chunk_count 
                FROM chunks 
                WHERE document_id IN (SELECT id FROM documents WHERE doc_type = %s)
            """, ('runbook',))
            chunk_result = cur.fetchone()
            chunk_count = chunk_result['chunk_count'] if isinstance(chunk_result, dict) else chunk_result[0]
            
            # Count chunks with embeddings
            cur.execute("""
                SELECT COUNT(*) as embed_count 
                FROM chunks 
                WHERE document_id IN (SELECT id FROM documents WHERE doc_type = %s) 
                AND embedding IS NOT NULL
            """, ('runbook',))
            embed_result = cur.fetchone()
            embed_count = embed_result['embed_count'] if isinstance(embed_result, dict) else embed_result[0]
            
            # Get embedding dimension sample
            cur.execute("""
                SELECT embedding::text as embedding_text
                FROM chunks 
                WHERE document_id IN (SELECT id FROM documents WHERE doc_type = %s) 
                AND embedding IS NOT NULL
                LIMIT 1
            """, ('runbook',))
            sample = cur.fetchone()
            embedding_dim = None
            if sample:
                embedding_text = sample['embedding_text'] if isinstance(sample, dict) else sample[0]
                if embedding_text:
                    embedding_dim = embedding_text.count(',') + 1
            
            conn.close()
            
            print(f"\nDatabase Verification:")
            print(f"   Documents stored: {doc_count}")
            print(f"   Chunks created: {chunk_count}")
            print(f"   Chunks with embeddings: {embed_count}/{chunk_count}")
            logger.info(f"\nDatabase Verification:")
            logger.info(f"   Documents stored: {doc_count}")
            logger.info(f"   Chunks created: {chunk_count}")
            logger.info(f"   Chunks with embeddings: {embed_count}/{chunk_count}")
            
            if embedding_dim:
                print(f"   Embedding dimension: {embedding_dim}")
                logger.info(f"   Embedding dimension: {embedding_dim}")
            
            if embed_count == chunk_count and chunk_count > 0:
                print(f"\n   SUCCESS: All {chunk_count} chunks have embeddings!")
                logger.info(f"\n   SUCCESS: All {chunk_count} chunks have embeddings!")
            elif embed_count < chunk_count:
                print(f"\n    WARNING: {chunk_count - embed_count} chunks are missing embeddings!")
                logger.warning(f"\n    WARNING: {chunk_count - embed_count} chunks are missing embeddings!")
            else:
                print(f"\n    WARNING: No chunks found in database!")
                logger.warning(f"\n    WARNING: No chunks found in database!")
                
        except Exception as e:
            print(f"    Could not verify embeddings: {str(e)}")
            print(f"     You can manually verify using: python scripts/db/verify_db.py")
            logger.warning(f"    Could not verify embeddings: {str(e)}")
            logger.warning(f"     You can manually verify using: python scripts/db/verify_db.py")
    
    if total_errors > 0:
        print(f"\n  Completed with {total_errors} error(s). Check logs for details.")
        sys.exit(1)
    else:
        print(f"\n Ingestion completed successfully!")


if __name__ == "__main__":
    main()

