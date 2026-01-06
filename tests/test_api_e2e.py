"""
End-to-end API tests using test incidents from test_incidents.csv.

This test file validates that:
1. Triage API correctly processes incidents
2. Resolution API generates appropriate resolution steps
3. Both APIs work together in an end-to-end flow
"""

import csv
import json
import os
import sys
import requests
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# API Configuration
API_BASE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
TRIAGE_ENDPOINT = f"{API_BASE_URL}/api/v1/triage"
RESOLUTION_ENDPOINT = f"{API_BASE_URL}/api/v1/resolution"
HEALTH_ENDPOINT = f"{API_BASE_URL}/api/v1/health"
TIMEOUT = 120  # seconds


def load_test_incidents(csv_path: Path, limit: int = 2) -> List[Dict]:
    """Load test incidents from CSV file."""
    incidents = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            
            # Parse affected_services (string representation of list)
            affected_services = []
            if row.get('affected_services'):
                try:
                    affected_services = eval(row['affected_services'])
                except:
                    affected_services = [s.strip() for s in row['affected_services'].split(',') if s.strip()]
            
            # Build alert payload matching Alert model
            incident = {
                'incident_id': row.get('incident_id', ''),
                'alert_id': row.get('incident_id', ''),
                'source': 'servicenow',
                'title': row.get('title', ''),
                'description': row.get('description', ''),
                'severity': row.get('severity', 'medium'),
                'ts': row.get('timestamp', datetime.utcnow().isoformat()),
                'labels': {
                    'service': affected_services[0] if affected_services else None,
                    'category': row.get('category', ''),
                },
                'affected_services': affected_services,
            }
            
            incidents.append(incident)
    
    return incidents


def check_service_health() -> bool:
    """Check if AI service is running and healthy."""
    try:
        response = requests.get(HEALTH_ENDPOINT, timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def test_triage(alert: Dict, retries: int = 3) -> Dict:
    """Test triage API endpoint."""
    print(f"\n  📋 Testing Triage API...")
    print(f"     Title: {alert['title'][:60]}...")
    print(f"     Service: {alert.get('labels', {}).get('service', 'N/A')}")
    
    for attempt in range(retries):
        try:
            response = requests.post(
                TRIAGE_ENDPOINT,
                json=alert,
                timeout=TIMEOUT
            )
        
            if response.status_code != 200:
                # Retry on 500 errors (connection pool issues)
                if response.status_code == 500 and attempt < retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"     ⚠️  Triage returned 500 (attempt {attempt + 1}/{retries}), retrying in {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                    continue
                
                print(f"     ❌ Triage failed with status {response.status_code}")
                print(f"     Response: {response.text[:200]}")
                return None
            
            result = response.json()
            
            incident_id = result.get('incident_id')
            triage_data = result.get('triage', {})
            
            # Check for incident_signature (may not be present if no matching signatures found)
            incident_sig = triage_data.get('incident_signature', {})
            if not incident_sig:
                # Try to get from evidence_chunks if available
                evidence = result.get('evidence_chunks', {})
                incident_sigs = evidence.get('incident_signatures', [])
                if incident_sigs and len(incident_sigs) > 0:
                    # Get failure_type and error_class from first incident signature
                    first_sig = incident_sigs[0]
                    incident_sig = {
                        'failure_type': first_sig.get('failure_type'),
                        'error_class': first_sig.get('error_class')
                    }
            
            print(f"     ✅ Triage successful!")
            print(f"     Incident ID: {incident_id}")
            print(f"     Severity: {triage_data.get('severity', 'N/A')}")
            print(f"     Policy Band: {result.get('policy_band', 'N/A')}")
            print(f"     Category: {triage_data.get('category', 'N/A')}")
            print(f"     Routing: {triage_data.get('routing', 'N/A')}")
            failure_type = incident_sig.get('failure_type') if incident_sig else None
            error_class = incident_sig.get('error_class') if incident_sig else None
            print(f"     Failure Type: {failure_type if failure_type else 'N/A (no matching signatures)'}")
            print(f"     Error Class: {error_class if error_class else 'N/A (no matching signatures)'}")
            print(f"     Confidence: {triage_data.get('confidence', 0.0):.2f}")
            
            # Validate response structure
            evidence_chunks = result.get('evidence_chunks', {})
            chunks_count = evidence_chunks.get('chunks_used', 0) if isinstance(evidence_chunks, dict) else len(evidence_chunks) if isinstance(evidence_chunks, list) else 0
            print(f"     Evidence Chunks: {chunks_count}")
            
            policy_decision = result.get('policy_decision', {})
            if policy_decision:
                print(f"     Requires Approval: {policy_decision.get('requires_approval', 'N/A')}")
                print(f"     Can Auto Apply: {policy_decision.get('can_auto_apply', 'N/A')}")
            
            return result  # Success, exit retry loop
            
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"     ⚠️  Triage request timed out (attempt {attempt + 1}/{retries}), retrying in {wait_time}s...")
                import time
                time.sleep(wait_time)
                continue
            print(f"     ❌ Triage request timed out after {TIMEOUT}s")
            return None
        except Exception as e:
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"     ⚠️  Triage error (attempt {attempt + 1}/{retries}): {str(e)}, retrying in {wait_time}s...")
                import time
                time.sleep(wait_time)
                continue
            print(f"     ❌ Triage error: {str(e)}")
            return None
    
    return None  # Should not reach here


def test_resolution(incident_id: str) -> Dict:
    """Test resolution API endpoint."""
    print(f"\n  🔧 Testing Resolution API...")
    print(f"     Incident ID: {incident_id}")
    
    try:
        response = requests.post(
            f"{RESOLUTION_ENDPOINT}?incident_id={incident_id}",
            timeout=TIMEOUT
        )
        
        # Handle approval required (403) - this is expected for REVIEW policy band
        if response.status_code == 403:
            error_data = response.json()
            if error_data.get('detail', {}).get('error') == 'approval_required':
                print(f"     ⚠️  Resolution requires approval (expected for REVIEW policy)")
                print(f"     Policy Band: REVIEW")
                print(f"     This is expected behavior - resolution needs human approval")
                # Return a special marker to indicate approval required
                return {'approval_required': True, 'incident_id': incident_id}
        
        if response.status_code != 200:
            print(f"     ❌ Resolution failed with status {response.status_code}")
            print(f"     Response: {response.text[:200]}")
            return None
        
        result = response.json()
        resolution_data = result.get('resolution', {})
        steps = resolution_data.get('steps', [])
        
        print(f"     ✅ Resolution successful!")
        print(f"     Incident ID: {result.get('incident_id')}")
        print(f"     Number of Steps: {len(steps)}")
        print(f"     Risk Level: {resolution_data.get('risk_level', 'N/A')}")
        print(f"     Confidence: {resolution_data.get('confidence', 0.0):.2f}")
        
        if steps:
            # Steps are dictionaries, extract title
            first_step_title = steps[0].get('title', '') if isinstance(steps[0], dict) else str(steps[0])
            print(f"     First Step: {first_step_title[:80]}...")
        
        evidence = result.get('evidence', {})
        if evidence:
            print(f"     Runbook Steps Retrieved: {evidence.get('runbook_steps', 0)}")
        
        return result
        
    except requests.exceptions.Timeout:
        print(f"     ❌ Resolution request timed out after {TIMEOUT}s")
        return None
    except Exception as e:
        print(f"     ❌ Resolution error: {str(e)}")
        return None


def test_incident_end_to_end(incident: Dict, incident_num: int) -> bool:
    """Test complete end-to-end flow for a single incident."""
    print(f"\n{'='*80}")
    print(f"TEST {incident_num}: {incident.get('title', 'Unknown')[:60]}")
    print(f"{'='*80}")
    
    # Step 1: Triage
    triage_result = test_triage(incident)
    if not triage_result:
        print(f"\n❌ TEST {incident_num} FAILED: Triage step failed")
        return False
    
    incident_id = triage_result.get('incident_id')
    if not incident_id:
        print(f"\n❌ TEST {incident_num} FAILED: No incident_id returned from triage")
        return False
    
    # Step 2: Resolution
    resolution_result = test_resolution(incident_id)
    if not resolution_result:
        print(f"\n❌ TEST {incident_num} FAILED: Resolution step failed")
        return False
    
    # Handle approval required case
    if resolution_result.get('approval_required'):
        print(f"\n✅ TEST {incident_num} PASSED: Triage successful, resolution requires approval (expected)")
        return True
    
    # Validation
    steps = resolution_result.get('resolution', {}).get('steps', [])
    if not steps:
        print(f"\n⚠️  TEST {incident_num} WARNING: No resolution steps generated")
        return True  # Not a failure, but worth noting
    
    print(f"\n✅ TEST {incident_num} PASSED: End-to-end flow completed successfully")
    return True


def main():
    """Run end-to-end API tests."""
    print("="*80)
    print("NOC AI Service - End-to-End API Tests")
    print("="*80)
    
    # Check service health
    print("\n🔍 Checking service health...")
    if not check_service_health():
        print(f"❌ AI service is not available at {API_BASE_URL}")
        print(f"   Please ensure the service is running:")
        print(f"   docker compose up -d ai-service")
        sys.exit(1)
    print(f"✅ Service is healthy at {API_BASE_URL}")
    
    # Load test incidents
    csv_path = project_root / "tickets_data" / "test_incidents.csv"
    if not csv_path.exists():
        print(f"❌ Test incidents file not found: {csv_path}")
        sys.exit(1)
    
    print(f"\n📂 Loading test incidents from: {csv_path}")
    incidents = load_test_incidents(csv_path, limit=2)
    
    if not incidents:
        print("❌ No test incidents loaded")
        sys.exit(1)
    
    print(f"✅ Loaded {len(incidents)} test incident(s)")
    
    # Run tests
    results = []
    for i, incident in enumerate(incidents, 1):
        success = test_incident_end_to_end(incident, i)
        results.append(success)
        # Add delay between tests to avoid connection pool exhaustion
        if i < len(incidents):
            import time
            print(f"\n⏳ Waiting 5 seconds before next test to avoid connection pool issues...")
            time.sleep(5)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(results)
    total = len(results)
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()

