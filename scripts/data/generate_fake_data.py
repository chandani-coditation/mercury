#!/usr/bin/env python3
"""Generate fake historical data using LLM and ingest via API."""
import sys
import os
import json
import argparse
from typing import Dict, List, Any
import requests
from openai import OpenAI
from dotenv import load_dotenv

# Add project root to path (go up 3 levels: scripts/data -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set")

client = OpenAI(api_key=OPENAI_API_KEY)


def load_schema_config():
    """Load schema configuration from config directory."""
    from ai_service.core.config_loader import load_config
    return load_config()


def generate_with_llm(data_type: str, count: int, schema_config: Dict) -> List[Dict]:
    """Generate fake data using LLM based on schema."""
    import sys
    
    # Get schema for this data type from config files
    historical_inputs = schema_config.get("historical_data_inputs", {})
    type_schema = historical_inputs.get(data_type, {})
    
    fields = type_schema.get("fields", [])
    description = type_schema.get("description", "")
    supported_formats = type_schema.get("supported_formats", [])
    
    # Also get alert_metadata schema if this is an alert
    alert_metadata_schema = schema_config.get("alert_metadata", {})
    required_fields = alert_metadata_schema.get("required_fields", [])
    optional_fields = alert_metadata_schema.get("optional_fields", [])
    labels_structure = alert_metadata_schema.get("labels_structure", {})
    
    # Print progress
    sys.stdout.write(f"      Generating {count} {data_type} entries using config files... ")
    sys.stdout.flush()
    
    # Build comprehensive prompt using config files
    size_profile = os.getenv("FAKER_SIZE", "medium")
    size_notes_map = {
        "small": "Keep entries concise.",
        "medium": "Moderate length with sufficient detail.",
        "large": "Longer entries: multi-section incidents/runbooks, 500-1500 lines logs.",
        "xl": "Very long entries: extensive incident narratives/runbooks, 1500-3000 lines logs with bursts."
    }
    size_notes = size_notes_map.get(size_profile, "Moderate length with sufficient detail.")

    prompt = f"""Generate {count} realistic {data_type} entries for a Network Operations Center (NOC) system.

SCHEMA CONFIGURATION (from config files):
- Description: {description}
- Supported formats: {', '.join(supported_formats) if supported_formats else 'N/A'}
- Fields defined in schema: {', '.join(fields) if fields else 'N/A'}

SCHEMA REQUIREMENTS:
1. Include ALL fields specified in schema: {', '.join(fields) if fields else 'N/A'}
2. For alerts: Include required fields: {', '.join(required_fields) if data_type == 'alert' and required_fields else 'N/A'}
3. For alerts: Include optional fields where appropriate: {', '.join(optional_fields) if data_type == 'alert' and optional_fields else 'N/A'}
4. For alerts: Use labels structure: {json.dumps(labels_structure, indent=2) if data_type == 'alert' and labels_structure else 'N/A'}

DATA GENERATION REQUIREMENTS ({size_profile.upper()} scale):
{size_notes}
1. Generate realistic, varied {data_type} data that represents real-world NOC scenarios
2. Use different services (api-gateway, payment-service, auth-service, database, cache, network, storage)
3. Use different components (api, worker, scheduler, infrastructure, compute, database, network)
4. Vary severity levels (low, medium, high, critical)
5. Make descriptions detailed and realistic with actual technical details
6. Include proper timestamps (within last 6 months, vary across time)
7. For structured data: include ALL fields from config/schemas.json
8. For unstructured data (incidents): provide realistic free-text content
9. Include realistic resolution tags, incident summaries, and context references
10. For logs: generate raw log streams with timestamps, include error patterns, connection issues, performance metrics; vary density with bursts and quiet periods according to the selected scale profile
11. For alerts: include raw alert streams, historical alert patterns, resolution statuses
12. For incidents: include detailed incident summaries, resolution tags, root cause analysis
13. Make data interconnected - some incidents should reference past alerts, some logs should relate to incidents

Output format: JSON object with key "{data_type}" containing an array of {count} entries. Return ONLY valid JSON, no markdown or explanation.

Example structure for {data_type}:"""

    # Add example based on type - using schema fields
    if data_type == "alert":
        prompt += f"""
Example alert structure (following config/schemas.json):
{{
  "alert_id": "alert-1234",  # Required field
  "source": "prometheus",  # Required field
  "title": "High CPU Usage",  # Required field
  "description": "CPU usage on api-gateway exceeded 90% for the last 15 minutes",  # Required field
  "ts": "2024-01-15T10:30:00Z",  # Required field
  "labels": {{  # Optional field - following labels_structure from schema
    "service": "api-gateway",
    "component": "api",
    "environment": "production",
    "severity": "high",
    "alertname": "HighCPUUsage"
  }},
  "severity": "high",  # Optional field
  "resolution_status": "resolved",  # Field from schema
  "resolution_notes": "Scaled up instances from 3 to 5"  # Field from schema
}}"""
    elif data_type == "incident":
        prompt += f"""
Example incident structure (following config/schemas.json fields):
{{
  "incident_id": "inc-001",  # Field from schema
  "alert_id": "alert-1234",  # Field from schema (if linked)
  "title": "Database Connection Pool Exhausted",  # Field from schema
  "description": "Application unable to connect to database",  # Field from schema
  "severity": "critical",  # Field from schema
  "category": "database",  # Field from schema
  "resolution_steps": ["Restarted connection pool", "Increased pool size from 10 to 50"],  # Field from schema
  "root_cause": "Connection pool size too small for current load",  # Field from schema
  "affected_services": ["payment-service", "api-gateway"],  # Field from schema
  "timestamp": "2024-01-15T10:30:00Z"  # Field from schema
}}

OR for unstructured format (supported in schema):
{{
  "title": "Network Outage",
  "raw_content": "On 2024-01-15, we experienced a network outage affecting all services..."
}}"""
    elif data_type == "runbook":
        prompt += f"""
Example runbook structure (following config/schemas.json fields):
{{
  "title": "Database Restart Procedure",  # Field from schema
  "service": "database",  # Field from schema
  "component": "postgres",  # Field from schema
  "content": "## Steps\\n1. Check active connections\\n2. Graceful shutdown\\n3. Restart service",  # Can be markdown/plain text per schema
  "steps": ["Check connections", "Shutdown", "Restart"],  # Field from schema
  "prerequisites": ["Deployment access", "Authorization"],  # Field from schema
  "rollback_procedures": "Restore from backup if restart fails"  # Field from schema
}}"""
    elif data_type == "log":
        prompt += f"""
Example log structure (following config/schemas.json fields):
{{
  "content": "2024-01-15 10:30:00 ERROR [api-gateway] Connection timeout to upstream service",  # Raw log content
  "timestamp": "2024-01-15T10:30:00Z",  # Field from schema
  "level": "error",  # Field from schema
  "service": "api-gateway",  # Field from schema
  "component": "api",  # Field from schema
  "message": "Connection timeout to upstream service",  # Field from schema
  "context": {{"request_id": "req-123", "user_id": "user-456"}},  # Field from schema (JSON)
  "log_format": "plain"  # Supported format from schema
}}"""
    
    # Add specific instructions based on data type
    if data_type == "log":
        prompt += """

For logs, generate:
- Raw log streams with realistic timestamps
- Different log levels (error, warning, info, debug)
- Include relevant context (service, component, request IDs, error codes)
- Make logs look like actual application/system logs
- Include patterns like: connection errors, timeouts, performance issues, authentication failures"""
    elif data_type == "alert":
        prompt += """

For alerts, generate:
- Raw alert streams with alert metadata
- Historical alert patterns (recurring alerts, alert chains)
- Resolution statuses and notes
- Alert labels that connect to services and components
- Some alerts should reference past incidents or known issues"""
    elif data_type == "incident":
        prompt += """

For incidents, generate:
- Detailed incident summaries with timeline
- Resolution tags (e.g., "resolved", "root-cause-identified", "workaround-applied")
- References to past alerts that led to this incident
- Context Lake data: link to related alerts, similar past incidents
- Include both structured (with all fields) and unstructured (raw_content) formats"""
    elif data_type == "runbook":
        prompt += """

For runbooks, generate:
- Standard operating procedures for common scenarios
- Troubleshooting guides
- Step-by-step resolution procedures
- Include rollback procedures and prerequisites"""
    
    prompt += f"\n\nGenerate {count} diverse, realistic {data_type} entries that represent a Context Lake of reference data. Return JSON object with key '{data_type}' containing the array."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a data generator for NOC systems. Generate realistic, diverse data entries that represent raw alert streams, historical logs, and Context Lake reference data (past alerts, incident summaries, resolution tags). Always return valid JSON objects with the data type as key."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            response_format={"type": "json_object"}
        )
        
        sys.stdout.write("✓\n")
        sys.stdout.flush()
        
        result = json.loads(response.choices[0].message.content)
        
        # Handle different response formats
        items = None
        if isinstance(result, dict):
            # Try to find array in response
            if data_type in result:
                items = result[data_type]
                items = items if isinstance(items, list) else [items]
            else:
                # Try common keys
                for key in ["items", "data", "entries", "results"]:
                    if key in result and isinstance(result[key], list):
                        items = result[key]
                        break
                # If no array found, wrap single item
                if items is None:
                    items = [result]
        elif isinstance(result, list):
            items = result
        else:
            items = [result]
        
        # Print details of each generated item
        if items:
            print(f"\n  📦 Generated {len(items)} {data_type}(s):")
            for idx, item in enumerate(items[:10], 1):  # Show first 10
                title = item.get("title") or item.get("alert_id") or item.get("incident_id") or f"Item {idx}"
                print(f"      [{idx}] {title[:60]}")
            if len(items) > 10:
                print(f"      ... and {len(items) - 10} more")
        
        return items if items else []
    
    except Exception as e:
        sys.stdout.write("✗\n")
        sys.stdout.flush()
        print(f"      Error generating with LLM: {type(e).__name__}: {e}")
        import traceback
        print(f"      Details: {traceback.format_exc()[:500]}")
        # Fallback: return empty list
        return []


def ingest_via_api(endpoint: str, data: Dict, item_index: int = None, verbose: bool = True) -> bool:
    """Ingest data via API endpoint."""
    item_type = endpoint.split("/")[-1]  # Extract 'alert', 'incident', etc.
    title = data.get("title") or data.get("alert_id") or data.get("incident_id") or f"Item {item_index}"
    
    try:
        url = f"{INGESTION_SERVICE_URL}{endpoint}"
        print(f"      → POST {url}")
        
        # Increase timeout for large payloads (especially logs)
        content_size = len(json.dumps(data)) if data else 0
        timeout = 120 if content_size > 500000 else 30  # 2 min for large payloads, 30s for normal
        
        response = requests.post(url, json=data, timeout=timeout)
        
        if response.status_code == 200:
            result = response.json()
            doc_id = result.get('document_id', 'N/A')
            if doc_id != 'N/A':
                doc_id = doc_id[:8] if isinstance(doc_id, str) else str(doc_id)[:8]
            print(f"      ✓ Response 200: document_id={doc_id}...")
            return True
        elif response.status_code == 404:
            error_msg = response.text[:200] if len(response.text) > 200 else response.text
            print(f"      ✗ Error 404: Endpoint not found")
            print(f"         URL: {url}")
            print(f"         Response: {error_msg}")
            print(f"         Check if ingestion service is running and endpoint exists")
            # Try to get available endpoints
            try:
                docs_response = requests.get(f"{INGESTION_SERVICE_URL}/openapi.json", timeout=5)
                if docs_response.status_code == 200:
                    docs = docs_response.json()
                    paths = list(docs.get("paths", {}).keys())
                    print(f"         Available endpoints: {', '.join(paths[:10])}")
            except:
                pass
            return False
        else:
            # Try to parse JSON error response
            try:
                error_json = response.json()
                error_detail = error_json.get('detail', str(error_json))
                if isinstance(error_detail, list):
                    error_detail = '; '.join(str(e) for e in error_detail)
            except:
                error_detail = response.text[:1000] if len(response.text) > 1000 else response.text
            
            print(f"      ✗ Error {response.status_code}: {error_detail}")
            if verbose:
                print(f"         Data keys: {list(data.keys())}")
                # For large content, show size instead of content
                if 'content' in data and isinstance(data['content'], str):
                    content_size = len(data['content'])
                    print(f"         Content size: {content_size:,} characters ({content_size/1024:.1f} KB)")
                    if content_size > 10000:
                        print(f"         Content preview (first 200 chars): {data['content'][:200]}...")
                    else:
                        print(f"         Content: {data['content'][:500]}")
                else:
                    sample = {k: (str(v)[:100] + '...' if isinstance(v, str) and len(str(v)) > 100 else v) 
                             for k, v in list(data.items())[:3]}
                    print(f"         Sample data: {json.dumps(sample, indent=2, default=str)}")
            return False
    except requests.exceptions.ConnectionError as e:
        print(f"      ✗ Connection Error: Cannot connect to {INGESTION_SERVICE_URL}")
        print(f"         Make sure ingestion service is running:")
        print(f"         python -m uvicorn ingestion.main:app --port 8000")
        return False
    except Exception as e:
        print(f"      ✗ Exception: {type(e).__name__}: {str(e)}")
        if verbose:
            import traceback
            print(f"         {traceback.format_exc()[:500]}")
        return False


def save_items_to_disk(items: List[Dict], data_type: str, output_dir: str) -> str:
    """Save generated items to disk as JSONL and return file path."""
    os.makedirs(output_dir, exist_ok=True)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = os.path.join(output_dir, f"{data_type}_{ts}.jsonl")
    with open(outfile, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"\n  💾 Saved {len(items)} {data_type}(s) to {outfile}")
    return outfile


def _chunk_large_content_for_upload(content: str, max_size_bytes: int = 900000, chunk_by_lines: bool = True) -> List[Dict[str, Any]]:
    """
    Chunk large content into smaller pieces for upload.
    
    This is a client-side chunking layer to handle FastAPI's 1MB request body limit.
    The server will still chunk these pieces for RAG (token-based chunking).
    
    Args:
        content: Content to chunk
        max_size_bytes: Maximum size per chunk (default: 900KB to stay under 1MB limit)
        chunk_by_lines: If True, split by lines (good for logs). If False, split by characters.
    
    Returns:
        List of chunk dictionaries with metadata
    """
    content_size = len(content.encode('utf-8'))
    
    # If content is small enough, return as single chunk
    if content_size <= max_size_bytes:
        return [{
            "content": content,
            "chunk_index": 0,
            "total_chunks": 1,
            "original_size": content_size
        }]
    
    chunks = []
    if chunk_by_lines:
        # Split by lines (preserves log structure)
        lines = content.split('\n')
        current_chunk_lines = []
        current_size = 0
        chunk_index = 0
        
        for line in lines:
            line_size = len((line + '\n').encode('utf-8'))
            
            # If adding this line would exceed limit, save current chunk
            if current_size + line_size > max_size_bytes and current_chunk_lines:
                chunks.append({
                    "content": '\n'.join(current_chunk_lines),
                    "chunk_index": chunk_index,
                    "total_chunks": None,  # Will be set later
                    "original_size": content_size,
                    "chunk_size": current_size
                })
                chunk_index += 1
                current_chunk_lines = [line]  # Start new chunk with this line
                current_size = line_size
            else:
                current_chunk_lines.append(line)
                current_size += line_size
        
        # Add final chunk
        if current_chunk_lines:
            chunks.append({
                "content": '\n'.join(current_chunk_lines),
                "chunk_index": chunk_index,
                "total_chunks": None,  # Will be set later
                "original_size": content_size,
                "chunk_size": current_size
            })
    else:
        # Split by characters (for non-line-based content)
        chunk_index = 0
        for i in range(0, len(content), max_size_bytes):
            chunk_content = content[i:i + max_size_bytes]
            chunks.append({
                "content": chunk_content,
                "chunk_index": chunk_index,
                "total_chunks": None,  # Will be set later
                "original_size": content_size,
                "chunk_size": len(chunk_content.encode('utf-8'))
            })
            chunk_index += 1
    
    # Set total_chunks for all chunks
    total_chunks = len(chunks)
    for chunk in chunks:
        chunk["total_chunks"] = total_chunks
    
    return chunks


def _synthesize_large_log(service: str, component: str, lines: int = 5000, burst_every: int = 200) -> str:
    """Generate deterministic, timestamped multi-thousand-line log content."""
    from datetime import datetime, timedelta
    start = datetime.utcnow().replace(microsecond=0)
    levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    msgs = [
        "Processing request",
        "Connection timeout to upstream",
        "Retrying operation",
        "Cache miss for key",
        "DB query slow",
        "Auth token expired",
        "Rate limit exceeded",
        "Upstream 502 Bad Gateway",
        "Circuit breaker open",
        "Recovered from error"
    ]
    lines_out = []
    current = start
    import random
    rng = random.Random(42)
    for i in range(lines):
        # bursts: every burst_every lines, insert an ERROR burst of 10 lines
        if burst_every and i % burst_every == 0 and i != 0:
            for j in range(10):
                ts = (current + timedelta(milliseconds=j*50)).strftime("%Y-%m-%d %H:%M:%S")
                lines_out.append(f"{ts} ERROR [{service}]({component}) code=E{500+j} message=Upstream failure during burst request_id=req-{i:06d}-{j:02d}")
        lvl = levels[rng.randint(0, len(levels)-1)]
        msg = msgs[rng.randint(0, len(msgs)-1)]
        ts = current.strftime("%Y-%m-%d %H:%M:%S")
        extra = f"request_id=req-{i:08d} latency_ms={rng.randint(1,1200)}"
        lines_out.append(f"{ts} {lvl} [{service}]({component}) {msg} {extra}")
        # advance time with some jitter
        current += timedelta(milliseconds= rng.randint(5, 60))
    return "\n".join(lines_out)


def generate_and_ingest(data_type: str, count: int, verbose: bool = True, output_dir: str = None, upload: bool = True, synth_logs: bool = False, synth_count: int = 5, log_lines: int = 5000, burst_every: int = 200):
    """Generate fake data using LLM, save locally, then optionally ingest via API."""
    print(f"\n{'='*60}")
    print(f"Generating {count} {data_type}(s) using LLM...")
    print(f"{'='*60}")
    
    # Load schema config
    try:
        schema_config = load_schema_config()
        print(f"  ✓ Loaded schema configuration")
    except Exception as e:
        print(f"  ⚠ Warning: Could not load config files: {e}")
        schema_config = {}
    
    # Generate data using LLM
    print(f"\n  🔄 Calling LLM to generate {count} {data_type} entries...")
    print(f"      This may take a moment...")
    items = generate_with_llm(data_type, count, schema_config)
    
    if not items:
        print(f"  ✗ No data generated from LLM")
        print(f"      Check OpenAI API key and network connection")
        return 0, False
    
    if len(items) != count:
        print(f"  ⚠ Generated {len(items)} items (requested {count})")
    else:
        print(f"  ✓ Generated {len(items)} items successfully")
    
    # Show sample of first item
    if items and verbose:
        print(f"\n  📋 Sample generated item:")
        sample = items[0]
        sample_preview = {
            "title": sample.get("title") or sample.get("alert_id") or "N/A",
            "keys": list(sample.keys())[:10]
        }
        print(f"      Title/ID: {sample_preview['title'][:60]}")
        print(f"      Fields: {', '.join(sample_preview['keys'])}")
        if len(sample.keys()) > 10:
            print(f"      ... and {len(sample.keys()) - 10} more fields")
    
    # Optional: synthesize large logs for realism
    if data_type == "log" and synth_logs and items:
        limit = max(1, min(synth_count, len(items)))
        if verbose:
            print(f"\n  🧪 Synthesizing large logs for {limit}/{len(items)} items (~{log_lines} lines each)...")
        for idx in range(limit):
            item = items[idx]
            service = item.get("service") or "api-gateway"
            component = item.get("component") or "api"
            item["content"] = _synthesize_large_log(service, component, lines=log_lines, burst_every=burst_every)

    # Normalize items to ensure required fields are present
    if data_type == "incident":
        for item in items:
            # Ensure 'description' is always present (required by IngestIncident model)
            if not item.get("description"):
                # Use raw_content if available, otherwise create from title
                if item.get("raw_content"):
                    item["description"] = item["raw_content"]
                else:
                    item["description"] = f"Incident: {item.get('title', 'Unknown')}"
    
    # Save to disk first
    if output_dir:
        save_items_to_disk(items, data_type, output_dir)
    
    if not upload:
        print(f"\n  ⏭️ Upload skipped (--save-only mode).")
        return len(items), True
    
    # Ingest each item
    endpoint = f"/ingest/{data_type}"
    print(f"\n  📤 Ingesting {len(items)} items via API (separate POSTs)...")
    print(f"      Endpoint: {INGESTION_SERVICE_URL}{endpoint}")
    success = 0
    failed = 0
    
    for i, item in enumerate(items, 1):
        print(f"\n  📝 Item {i}/{len(items)}:")
        title = item.get("title") or item.get("alert_id") or item.get("incident_id") or f"Item {i}"
        print(f"      Title: {title[:60]}")
        
        try:
            if data_type == "alert":
                result = ingest_via_api("/ingest/alert", item, i, verbose)
            elif data_type == "incident":
                result = ingest_via_api("/ingest/incident", item, i, verbose)
            elif data_type == "runbook":
                result = ingest_via_api("/ingest/runbook", item, i, verbose)
            elif data_type == "log":
                # For logs, check if content is too large and chunk if needed
                content = item.get("content", "")
                if content:
                    content_size = len(content.encode('utf-8'))
                    max_size = 900000  # 900KB to stay under 1MB limit
                    
                    if content_size > max_size:
                        print(f"      ⚠ Large log detected ({content_size/1024:.1f} KB), chunking for upload...")
                        chunks = _chunk_large_content_for_upload(content, max_size_bytes=max_size, chunk_by_lines=True)
                        print(f"      📦 Split into {len(chunks)} chunks for upload")
                        
                        # Send each chunk as a separate log document
                        chunk_success = 0
                        for chunk_idx, chunk_data in enumerate(chunks):
                            # Create log item for this chunk
                            chunk_item = item.copy()
                            chunk_item["content"] = chunk_data["content"]
                            
                            # Add metadata to link chunks together
                            if "metadata" not in chunk_item:
                                chunk_item["metadata"] = {}
                            chunk_item["metadata"]["chunk_index"] = chunk_data["chunk_index"]
                            chunk_item["metadata"]["total_chunks"] = chunk_data["total_chunks"]
                            chunk_item["metadata"]["original_size"] = chunk_data["original_size"]
                            chunk_item["metadata"]["is_chunked"] = True
                            
                            # Update title to indicate chunk
                            if chunk_data["total_chunks"] > 1:
                                chunk_item["title"] = f"{title} (Part {chunk_data['chunk_index'] + 1}/{chunk_data['total_chunks']})"
                            
                            chunk_result = ingest_via_api("/ingest/log", chunk_item, f"{i}.{chunk_idx + 1}", verbose)
                            if chunk_result:
                                chunk_success += 1
                        
                        # Consider item successful if all chunks succeeded
                        result = (chunk_success == len(chunks))
                        if result:
                            print(f"      ✓ All {len(chunks)} chunks ingested successfully")
                        else:
                            print(f"      ✗ Only {chunk_success}/{len(chunks)} chunks succeeded")
                    else:
                        # Normal size, send as-is
                        result = ingest_via_api("/ingest/log", item, i, verbose)
                else:
                    # No content, send as-is
                    result = ingest_via_api("/ingest/log", item, i, verbose)
            else:
                print(f"    ✗ Unknown data type: {data_type}")
                return 0, False
            
            if result:
                success += 1
                print(f"      ✓ Item {i} ingested successfully")
            else:
                failed += 1
                print(f"      ✗ Item {i} failed to ingest")
                # Check if we've hit failure threshold (90% success rate)
                current_success_rate = success / i if i > 0 else 0
                if current_success_rate < 0.1:  # Less than 10% success
                    print(f"\n  ⚠ CRITICAL: Success rate is {current_success_rate*100:.1f}% (below 10%)")
                    print(f"      Stopping ingestion to investigate failures")
                    print(f"      Check ingestion service logs and endpoint availability")
                    return success, False
        
        except Exception as e:
            failed += 1
            print(f"    [{i}] ✗ Unexpected exception: {type(e).__name__}: {e}")
            if verbose:
                import traceback
                print(f"        {traceback.format_exc()[:300]}")
    
    # Calculate final success rate
    success_rate = success / len(items) if len(items) > 0 else 0
    print(f"\n  📊 Summary:")
    print(f"      ✓ Success: {success}/{len(items)} ({success_rate*100:.1f}%)")
    if failed > 0:
        print(f"      ✗ Failed: {failed}/{len(items)}")
    print(f"      Total: {len(items)} {data_type}(s)")
    
    # Check if success rate meets threshold (90%+)
    if success_rate < 0.9:
        print(f"\n  ✗ FAILURE: Success rate {success_rate*100:.1f}% is below 90% threshold")
        print(f"      Please investigate errors before continuing")
        return success, False
    
    print(f"  ✓ SUCCESS: Success rate {success_rate*100:.1f}% meets 90% threshold")
    return success, True


def main():
    global INGESTION_SERVICE_URL
    
    parser = argparse.ArgumentParser(
        description="Generate fake historical data using LLM, save to disk, and optionally ingest via API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all types (20 each)
  python scripts/generate_fake_data.py --all --count 20
  
  # Generate only incidents
  python scripts/generate_fake_data.py --type incident --count 30
  
  # Verbose output
  python scripts/generate_fake_data.py --type runbook --count 15 --verbose

  # Save only (no upload), to a specific directory
  python scripts/generate_fake_data.py --type incident --count 10 --output-dir data/faker_output --save-only
        """
    )
    parser.add_argument("--type", choices=["alert", "incident", "runbook", "log"],
                       help="Type of data to generate")
    parser.add_argument("--all", action="store_true", help="Generate all types")
    parser.add_argument("--count", type=int, default=20, help="Number of items to generate per type (default: 20)")
    parser.add_argument("--url", default=INGESTION_SERVICE_URL, help="Ingestion service URL")
    parser.add_argument("--verbose", "-v", action="store_true", default=True, help="Verbose output (default: True)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (less output)")
    parser.add_argument("--output-dir", type=str, default="data/faker_output", help="Directory to write generated JSONL files")
    parser.add_argument("--save-only", action="store_true", help="Only save to disk; do not upload")
    parser.add_argument("--size", choices=["small", "medium", "large", "xl"], default="medium", help="Scale profile for lengths and complexity")
    parser.add_argument("--synth-logs", action="store_true", help="Synthesize multi-thousand-line logs for realism")
    parser.add_argument("--synth-count", type=int, default=5, help="How many log items to synthesize (default: 5)")
    parser.add_argument("--log-lines", type=int, default=5000, help="Lines per synthesized log (default: 5000)")
    parser.add_argument("--burst-every", type=int, default=200, help="Insert error bursts every N lines (default: 200)")
    
    args = parser.parse_args()
    
    if not args.type and not args.all:
        parser.error("Either --type or --all must be specified")
    
    # Update global URL
    INGESTION_SERVICE_URL = args.url
    
    # Set verbose based on quiet flag
    verbose = not args.quiet
    
    # If we plan to upload, verify service is reachable; else skip checks
    if not args.save_only:
        try:
            response = requests.get(f"{INGESTION_SERVICE_URL}/health", timeout=5)
            if response.status_code != 200:
                print(f"✗ Ingestion service not healthy: {response.status_code}")
                sys.exit(1)
            print(f"✓ Connected to ingestion service at {INGESTION_SERVICE_URL}")
            
            # Verify required endpoints exist
            print(f"  🔍 Verifying required endpoints exist...")
            try:
                docs_response = requests.get(f"{INGESTION_SERVICE_URL}/openapi.json", timeout=5)
                if docs_response.status_code == 200:
                    docs = docs_response.json()
                    paths = list(docs.get("paths", {}).keys())
                    required_endpoints = ["/ingest/alert", "/ingest/incident", "/ingest/runbook", "/ingest/log"]
                    missing = [ep for ep in required_endpoints if ep not in paths]
                    
                    if missing:
                        print(f"  ✗ Missing endpoints: {', '.join(missing)}")
                        print(f"  Available endpoints: {', '.join(paths[:10])}")
                        print(f"\n  💡 SOLUTION: Restart the ingestion service to load new endpoints:")
                        print(f"      1. Kill existing service: pkill -f 'uvicorn.*ingestion'")
                        print(f"      2. Start service: python -m uvicorn ingestion.main:app --port 8000 --reload")
                        print(f"      Or use: ./scripts/utils/restart_ingestion_service.sh")
                        sys.exit(1)
                    else:
                        print(f"  ✓ All required endpoints verified")
                else:
                    print(f"  ⚠ Could not verify endpoints (OpenAPI docs not available)")
            except Exception as e:
                print(f"  ⚠ Could not verify endpoints: {e}")
        except Exception as e:
            print(f"✗ Cannot connect to ingestion service at {INGESTION_SERVICE_URL}: {e}")
            print(f"  Make sure ingestion service is running: python -m uvicorn ingestion.main:app --port 8000")
            sys.exit(1)
    
    # Check OpenAI API key
    if not OPENAI_API_KEY:
        print("✗ OPENAI_API_KEY not set in environment")
        print("  Set it in .env file or export OPENAI_API_KEY=your-key")
        sys.exit(1)
    
    total_success = 0
    
    if args.all:
        types = ["alert", "incident", "runbook", "log"]
        print(f"\n🚀 Generating all data types ({args.count} each)...")
        for data_type in types:
            success, should_continue = generate_and_ingest(
                data_type,
                args.count,
                verbose,
                output_dir=args.output_dir,
                upload=(not args.save_only),
                synth_logs=args.synth_logs,
                synth_count=args.synth_count,
                log_lines=args.log_lines,
                burst_every=args.burst_every
            )
            total_success += success
            
            if not should_continue:
                print(f"\n✗ Stopping: {data_type} ingestion failed below 90% threshold")
                print(f"  Fix the issues and re-run the script")
                sys.exit(1)
            
            print()  # Blank line between types
    else:
        success, should_continue = generate_and_ingest(
            args.type,
            args.count,
            verbose,
            output_dir=args.output_dir,
            upload=(not args.save_only),
            synth_logs=args.synth_logs,
            synth_count=args.synth_count,
            log_lines=args.log_lines,
            burst_every=args.burst_every
        )
        total_success = success
        
        if not should_continue:
            print(f"\n✗ Stopping: {args.type} ingestion failed below 90% threshold")
            print(f"  Fix the issues and re-run the script")
            sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"✅ Total: {total_success} items ingested successfully")
    print(f"{'='*60}")
    
    # Suggest next steps
    print("\n📋 Next steps:")
    print("  1. Test triage: python scripts/simulate_alerts.py --count 5")
    print("  2. View metrics: python scripts/mttr_metrics.py")
    print("  3. Query incidents: curl http://localhost:8001/incidents")
    print("  4. Check ingested data: psql -h localhost -U postgres -d nocdb -c 'SELECT COUNT(*) FROM documents;'")


if __name__ == "__main__":
    main()
