#!/usr/bin/env python3
"""Ingest data into the knowledge base.

Supports:
- JSONL files (one JSON object per line)
- JSON files (single object or array)
- Plain text files
- Directories with patterns

Usage:
  # Ingest all JSONL files from data/faker_output
  python scripts/data/ingest_data.py --dir data/faker_output

  # Ingest specific file
  python scripts/data/ingest_data.py --file data/alerts.jsonl --type alert

  # Ingest with pattern
  python scripts/data/ingest_data.py --dir data/faker_output --pattern "alert_*.jsonl" --type alert
"""
import sys
import os
import json
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from ai_service.core import get_logger, setup_logging
except ImportError:
    import logging

    def setup_logging(log_level="INFO", service_name="ingest_data_script"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)

# Setup logging
setup_logging(log_level="INFO", service_name="ingest_data_script")
logger = get_logger(__name__)

import requests

INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8002")


def ingest_file(file_path: Path, doc_type: str):
    """Ingest a single file (supports JSON, JSONL, or plain text)."""
    logger.info(f"Ingesting {file_path} as {doc_type}...")

    # Calculate timeout based on file size and type
    # Large log files need more time for embedding generation
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if doc_type == "log" and file_size_mb > 5:
        # Large log files: 10 minutes per MB (minimum 10 minutes)
        timeout = max(600, int(file_size_mb * 600))
        logger.info(
            f"  Large log file detected ({file_size_mb:.1f}MB), using extended timeout: {timeout}s"
        )
    elif doc_type == "log":
        # Smaller log files: 5 minutes
        timeout = 300
    else:
        # Other types: 5 minutes
        timeout = 300

    # Check if it's a JSONL file (one JSON object per line)
    items = []
    with open(file_path, "r", encoding="utf-8") as f:
        # Try to read as JSONL first (one JSON object per line)
        lines = f.readlines()
        if len(lines) > 1 or (len(lines) == 1 and not lines[0].strip().startswith("[")):
            # Likely JSONL format - parse each line as JSON
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    items.append(item)
                except json.JSONDecodeError as e:
                    logger.warning(f"   Warning: Skipping invalid JSON on line {line_num}: {e}")
                    continue

            if items:
                # Batch ingest all items from JSONL
                logger.info(f"  Sending {len(items)} items to ingestion service (timeout: {timeout}s)...")
                response = requests.post(
                    f"{INGESTION_SERVICE_URL}/ingest/batch?doc_type={doc_type}",
                    json=items,
                    timeout=timeout,
                )
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f" Ingested {len(items)} items from JSONL file")
                    return True
                else:
                    logger.error(f" Error: {response.status_code} - {response.text}")
                    return False
            else:
                logger.warning(f" No valid JSON objects found in file")
                return False

    # If not JSONL, try as regular JSON
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        data = json.loads(content)
        if isinstance(data, list):
            # Batch ingest
            response = requests.post(
                f"{INGESTION_SERVICE_URL}/ingest/batch?doc_type={doc_type}",
                json=data,
                timeout=timeout,
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f" Ingested {len(data)} items")
                return True
            else:
                logger.error(f" Error: {response.status_code} - {response.text}")
                return False
        else:
            # Single item - use specific endpoint
            from ingestion.models import IngestAlert, IngestIncident, IngestRunbook, IngestLog

            if doc_type == "alert":
                item = IngestAlert(**data)
                response = requests.post(
                    f"{INGESTION_SERVICE_URL}/ingest/alert", json=item.model_dump(), timeout=timeout
                )
            elif doc_type == "incident":
                item = IngestIncident(**data)
                response = requests.post(
                    f"{INGESTION_SERVICE_URL}/ingest/incident",
                    json=item.model_dump(),
                    timeout=timeout,
                )
            elif doc_type == "runbook":
                item = IngestRunbook(**data)
                response = requests.post(
                    f"{INGESTION_SERVICE_URL}/ingest/runbook",
                    json=item.model_dump(),
                    timeout=timeout,
                )
            elif doc_type == "log":
                item = IngestLog(content=content, **data)
                response = requests.post(
                    f"{INGESTION_SERVICE_URL}/ingest/log", json=item.model_dump(), timeout=timeout
                )
            else:
                # Generic document
                response = requests.post(
                    f"{INGESTION_SERVICE_URL}/ingest",
                    json={
                        "doc_type": doc_type,
                        "title": data.get("title", file_path.name),
                        "content": data.get("content", content),
                        "service": data.get("service"),
                        "component": data.get("component"),
                        "tags": data,
                    },
                    timeout=timeout,
                )

            if response.status_code == 200:
                result = response.json()
                logger.info(f" Ingested: {result.get('document_id', 'N/A')}")
                return True
            else:
                logger.error(f" Error: {response.status_code} - {response.text}")
                return False
    except json.JSONDecodeError:
        # Unstructured text - use batch endpoint
        response = requests.post(
            f"{INGESTION_SERVICE_URL}/ingest/batch?doc_type={doc_type}",
            json=[content],
            timeout=timeout,
        )
        if response.status_code == 200:
            result = response.json()
            logger.info(f" Ingested as text document")
            return True
        else:
            logger.error(f" Error: {response.status_code} - {response.text}")
            return False


def ingest_directory(directory: Path, doc_type: str, pattern: str = "*"):
    """Ingest all files in a directory matching the pattern."""
    files = list(directory.glob(pattern))
    logger.info(f"Found {len(files)} files in {directory}")

    success = 0
    failed = 0
    for file_path in sorted(files):
        if file_path.is_file():
            try:
                if ingest_file(file_path, doc_type):
                    success += 1
                else:
                    failed += 1
                    logger.error(f"   Failed to ingest {file_path.name}")
            except requests.exceptions.ReadTimeout as e:
                failed += 1
                logger.warning(f"   Timeout ingesting {file_path.name}: {e}")
                logger.warning(
                    f"     This file may be too large. Try ingesting it separately with a longer timeout."
                )
            except Exception as e:
                failed += 1
                logger.error(f"   Error ingesting {file_path.name}: {e}")

    logger.info(f"\n Successfully ingested {success}/{len(files)} files")
    if failed > 0:
        logger.error(f" Failed to ingest {failed} files")
    return success


def main():
    global INGESTION_SERVICE_URL

    parser = argparse.ArgumentParser(
        description="Ingest data into NOC Agent AI knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest all JSONL files from data/faker_output (auto-detect type from filename)
  python scripts/data/ingest_data.py --dir data/faker_output

  # Ingest specific type with pattern
  python scripts/data/ingest_data.py --dir data/faker_output --pattern "alert_*.jsonl" --type alert

  # Ingest single file
  python scripts/data/ingest_data.py --file data/alerts.jsonl --type alert
        """,
    )
    parser.add_argument(
        "--type",
        choices=["alert", "incident", "runbook", "log", "document"],
        help="Type of data to ingest (auto-detected from filename if not provided)",
    )
    parser.add_argument("--file", type=Path, help="Single file to ingest")
    parser.add_argument("--dir", type=Path, help="Directory containing files to ingest")
    parser.add_argument("--pattern", default="*", help="File pattern (default: *)")
    parser.add_argument("--url", default=INGESTION_SERVICE_URL, help="Ingestion service URL")

    args = parser.parse_args()

    if args.url:
        INGESTION_SERVICE_URL = args.url
    else:
        INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8002")

    # Check service is up
    try:
        response = requests.get(f"{INGESTION_SERVICE_URL}/health", timeout=5)
        if response.status_code != 200:
            logger.error(f" Ingestion service not healthy: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        logger.error(f" Cannot connect to ingestion service at {INGESTION_SERVICE_URL}: {e}")
        sys.exit(1)

    logger.info(f" Connected to ingestion service at {INGESTION_SERVICE_URL}\n")

    if args.file:
        if not args.file.exists():
            logger.error(f" File not found: {args.file}")
            sys.exit(1)

        # Auto-detect type from filename if not provided
        doc_type = args.type
        if not doc_type:
            filename = args.file.name.lower()
            if "alert" in filename:
                doc_type = "alert"
            elif "incident" in filename:
                doc_type = "incident"
            elif "runbook" in filename:
                doc_type = "runbook"
            elif "log" in filename:
                doc_type = "log"
            else:
                doc_type = "document"
            logger.info(f"Auto-detected type: {doc_type}")

        success = ingest_file(args.file, doc_type)
        sys.exit(0 if success else 1)

    elif args.dir:
        if not args.dir.exists():
            logger.error(f" Directory not found: {args.dir}")
            sys.exit(1)

        # If no type specified, process all types
        if not args.type:
            types = {
                "alert": "alert_*.jsonl",
                "incident": "incident_*.jsonl",
                "runbook": "runbook_*.jsonl",
                "log": "log_*.jsonl",
            }

            total_ingested = 0
            for doc_type, type_pattern in types.items():
                files = list(args.dir.glob(type_pattern))
                if files:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"Processing {doc_type} files...")
                    logger.info(f"{'='*60}")
                    success = ingest_directory(args.dir, doc_type, type_pattern)
                    total_ingested += success

            logger.info(f"\n{'='*60}")
            logger.info(f" Total files ingested: {total_ingested}")
            logger.info(f"{'='*60}")
            sys.exit(0 if total_ingested > 0 else 1)
        else:
            success = ingest_directory(args.dir, args.type, args.pattern)
            sys.exit(0 if success > 0 else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
