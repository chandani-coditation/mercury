"""
Test script for specific BGP Peer alert to validate triage and resolution responses.
"""

import json
import requests
import sys
from typing import Dict

# API Configuration
API_BASE_URL = "http://localhost:8001"
TRIAGE_ENDPOINT = f"{API_BASE_URL}/api/v1/triage"
RESOLUTION_ENDPOINT = f"{API_BASE_URL}/api/v1/resolution"
TIMEOUT = 120  # seconds

# Test alert data
TEST_ALERT = {
    "alert_id": "INC6003207",
    "title": "BGP Peer 173.197.165.33 not established on LV-INET-RT-B",
    "description": "Router: LV-INET-RT-B \nNeighbor IP: 173.197.165.33 \nState: Idle\n\nTrigger Time: Friday, June 6, 2025 12:29 AM\n\nRouter Details: https://orion.int.mgc.com:443/Orion/NetPerfMon/NodeDetails.aspx?NetObject=N:3845 \n\n\nKB: \n\nBR-INET-RT-A\nAT&T: 12.91.173.93\n\nBR-INET-RT-B\nSpectrum: 173.197.80.1\nLumen: 4.38.224.189\n\nLV-INET-RT-A\nAT&T: 12.124.140.25\n\nLV-INET-RT-B\nLumen: 65.56.156.121\nSpectrum: 173.197.165.33",
    "source": "servicenow",
    "category": "network",
    "labels": {
        "service": "Network",
        "component": "Router",
        "cmdb_ci": "Network",
        "environment": "production",
        "severity": "critical",
        "alertname": "BGP Peer Not Established",
    },
    "affected_services": ["Network"],
    "ts": "2025-06-06T00:29:00",
}


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")


def test_triage(alert: Dict) -> Dict:
    """Test triage API endpoint."""
    print_section("TESTING TRIAGE API")
    print(f"Alert ID: {alert['alert_id']}")
    print(f"Title: {alert['title']}")
    print(f"Service: {alert['labels']['service']}")
    print(f"Component: {alert['labels']['component']}")

    try:
        print(f"\n📤 Sending triage request...")
        response = requests.post(TRIAGE_ENDPOINT, json=alert, timeout=TIMEOUT)

        if response.status_code != 200:
            print(f"❌ Triage failed with status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None

        result = response.json()

        # Extract key information
        incident_id = result.get("incident_id")
        triage_data = result.get("triage", {})
        evidence = result.get("evidence", {})

        print(f"\n✅ Triage successful!")
        print(f"   Incident ID: {incident_id}")

        # Triage output validation
        if triage_data:
            print(f"\n📊 Triage Output:")
            print(f"   Severity: {triage_data.get('severity', 'N/A')}")
            print(f"   Impact: {triage_data.get('impact', 'N/A')}")
            print(f"   Urgency: {triage_data.get('urgency', 'N/A')}")
            print(f"   Confidence: {triage_data.get('confidence', 0.0):.2f}")
            print(f"   Policy: {triage_data.get('policy', 'N/A')}")
            print(f"   Routing: {triage_data.get('routing', 'N/A')}")

            # Incident signature
            incident_sig = triage_data.get("incident_signature", {})
            if incident_sig:
                print(f"   Failure Type: {incident_sig.get('failure_type', 'N/A')}")
                print(f"   Error Class: {incident_sig.get('error_class', 'N/A')}")

            # Matched evidence
            matched_evidence = triage_data.get("matched_evidence", {})
            if matched_evidence:
                incident_sigs = matched_evidence.get("incident_signatures", [])
                runbook_refs = matched_evidence.get("runbook_refs", [])
                print(f"   Matched Incident Signatures: {len(incident_sigs)}")
                print(f"   Matched Runbook Refs: {len(runbook_refs)}")
                if runbook_refs:
                    print(f"   Runbook IDs: {runbook_refs[:3]}...")  # Show first 3

        # Evidence validation
        if evidence:
            print(f"\n📚 Evidence Retrieved:")
            chunks_used = evidence.get("chunks_used", 0)
            runbook_metadata = evidence.get("runbook_metadata", [])
            incident_signatures = evidence.get("incident_signatures", [])

            print(f"   Total Chunks Used: {chunks_used}")
            print(f"   Incident Signatures: {len(incident_signatures)}")
            print(f"   Runbook Metadata: {len(runbook_metadata)}")

            if runbook_metadata:
                print(f"\n   Runbook Metadata Details:")
                for i, rb in enumerate(runbook_metadata[:5], 1):  # Show first 5
                    print(f"      {i}. {rb.get('title', 'N/A')}")
                    print(f"         Document ID: {rb.get('document_id', 'N/A')}")
                    print(f"         Service: {rb.get('service', 'N/A')}")
                    print(f"         Component: {rb.get('component', 'N/A')}")

            # Check if we have runbook steps in chunks
            chunks = evidence.get("chunks", [])
            runbook_step_chunks = [
                c
                for c in chunks
                if c.get("provenance", {}).get("source_type") == "runbook_step"
                or c.get("metadata", {}).get("doc_type") == "runbook_step"
            ]
            print(f"   Runbook Step Chunks in Evidence: {len(runbook_step_chunks)}")

        return result

    except requests.exceptions.Timeout:
        print(f"❌ Triage request timed out after {TIMEOUT}s")
        return None
    except Exception as e:
        print(f"❌ Triage error: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


def test_resolution(incident_id: str, triage_result: Dict = None) -> Dict:
    """Test resolution API endpoint."""
    print_section("TESTING RESOLUTION API (COPILOT)")
    print(f"Incident ID: {incident_id}")

    if triage_result:
        evidence = triage_result.get("evidence", {})
        runbook_metadata = evidence.get("runbook_metadata", [])
        if runbook_metadata:
            print(f"Expected Runbooks: {len(runbook_metadata)}")
            for rb in runbook_metadata[:3]:
                print(f"  - {rb.get('title', 'N/A')} (doc_id: {rb.get('document_id', 'N/A')})")

    try:
        print(f"\n📤 Sending resolution request...")
        response = requests.post(
            f"{RESOLUTION_ENDPOINT}?incident_id={incident_id}", timeout=TIMEOUT
        )

        # Handle approval required
        if response.status_code == 403:
            error_data = response.json()
            if error_data.get("detail", {}).get("error") == "approval_required":
                print(f"⚠️  Resolution requires approval (expected for REVIEW policy)")
                return {"approval_required": True, "incident_id": incident_id}

        if response.status_code != 200:
            print(f"❌ Resolution failed with status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None

        result = response.json()
        resolution_data = result.get("resolution", {})
        steps = resolution_data.get("steps", []) or resolution_data.get("resolution_steps", [])
        evidence = result.get("evidence", {})

        print(f"\n✅ Resolution successful!")
        print(f"   Incident ID: {result.get('incident_id')}")
        print(f"   Retrieval Method: {evidence.get('retrieval_method', 'N/A')}")

        # Resolution output validation
        print(f"\n📋 Resolution Output:")
        print(f"   Number of Steps: {len(steps)}")
        print(f"   Confidence: {resolution_data.get('confidence', 0.0):.2f}")
        print(f"   Risk Level: {resolution_data.get('risk_level', 'N/A')}")

        reasoning = resolution_data.get("reasoning", "")
        if reasoning:
            print(f"   Reasoning: {reasoning[:200]}...")

        # Evidence validation
        if evidence:
            runbook_steps = evidence.get("runbook_steps", 0)
            steps_retrieved = evidence.get("steps_retrieved", 0)
            print(f"\n📚 Resolution Evidence:")
            print(f"   Runbook Steps Retrieved: {runbook_steps}")
            print(f"   Steps Retrieved (after filtering): {steps_retrieved}")

        # Validate steps
        if steps:
            print(f"\n📝 Resolution Steps:")
            for i, step in enumerate(steps[:5], 1):  # Show first 5 steps
                if isinstance(step, dict):
                    print(f"   {i}. {step.get('title', 'N/A')}")
                    print(f"      Action: {step.get('action', 'N/A')[:100]}...")
                    if step.get("expected_outcome"):
                        print(
                            f"      Expected Outcome: {step.get('expected_outcome', 'N/A')[:80]}..."
                        )
                else:
                    print(f"   {i}. {str(step)[:100]}...")
        else:
            print(f"\n⚠️  No resolution steps generated!")
            if reasoning:
                print(f"   Reasoning: {reasoning}")

        # Validate response structure
        print(f"\n✅ Resolution response structure validation:")
        required_fields = ["steps", "confidence", "reasoning"]
        missing_fields = [f for f in required_fields if f not in resolution_data]
        if missing_fields:
            print(f"   ⚠️  Missing fields: {missing_fields}")
        else:
            print(f"   ✅ All required fields present")

        # Check if RAG or LLM was used
        retrieval_method = evidence.get("retrieval_method", "")
        if retrieval_method == "copilot_llm_fallback":
            print(
                f"\n✅ LLM Fallback Used: Resolution agent returned empty, copilot agent generated steps"
            )
        elif retrieval_method == "resolution_retrieval":
            print(f"\n✅ RAG Used: Runbook steps retrieved from database")
            if not steps:
                print(f"   ⚠️  All steps were filtered out (likely documentation/context only)")
        else:
            print(f"\n📊 Retrieval Method: {retrieval_method}")

        # Check if approval was required
        if not steps and reasoning and "filtered" in reasoning.lower():
            print(f"\n💡 Note: Steps were retrieved but filtered. This may indicate:")
            print(f"   - Runbook steps contain only documentation/context")
            print(f"   - Filtering logic may be too aggressive")
            print(f"   - Copilot fallback was triggered but requires approval (REVIEW policy)")

        return result

    except requests.exceptions.Timeout:
        print(f"❌ Resolution request timed out after {TIMEOUT}s")
        return None
    except Exception as e:
        print(f"❌ Resolution error: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """Run end-to-end test for the specific alert."""
    print_section("BGP PEER ALERT - END-TO-END TEST")

    # Step 1: Test Triage
    triage_result = test_triage(TEST_ALERT)
    if not triage_result:
        print("\n❌ TEST FAILED: Triage step failed")
        sys.exit(1)

    incident_id = triage_result.get("incident_id")
    if not incident_id:
        print("\n❌ TEST FAILED: No incident_id returned from triage")
        sys.exit(1)

    # Step 2: Test Resolution
    resolution_result = test_resolution(incident_id, triage_result)
    if not resolution_result:
        print("\n❌ TEST FAILED: Resolution step failed")
        sys.exit(1)

    # Final summary
    print_section("TEST SUMMARY")

    if resolution_result.get("approval_required"):
        print("✅ TEST PASSED: Triage successful, resolution requires approval (expected)")
    else:
        resolution_data = resolution_result.get("resolution", {})
        steps = resolution_data.get("steps", []) or resolution_data.get("resolution_steps", [])

        if steps:
            print(f"✅ TEST PASSED: Both triage and resolution completed successfully")
            print(f"   Generated {len(steps)} resolution steps")
        else:
            print(f"⚠️  TEST COMPLETED: Triage successful, but no resolution steps generated")
            print(f"   This may indicate no matching runbook steps were found")

    print(f"\nIncident ID: {incident_id}")
    print(f"Test completed successfully!")


if __name__ == "__main__":
    main()
