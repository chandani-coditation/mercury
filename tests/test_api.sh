#!/bin/bash
# Quick API Testing Script

API_BASE="http://localhost:8001/api/v1"

echo " NOC Agent AI - API Testing"
echo "=============================="
echo ""

# Test 1: Health Check
echo "1.  Testing Health Endpoint..."
curl -s "${API_BASE}/health" | jq '.' || echo "   Response received"
echo ""

# Test 2: Readiness Check
echo "2.  Testing Readiness Endpoint..."
curl -s "${API_BASE}/health/ready" | jq '.' || echo "   Response received"
echo ""

# Test 3: Ingest Sample Runbook
echo "3.  Ingesting Sample Runbook..."
RUNBOOK_RESPONSE=$(curl -s -X POST "http://localhost:8002/ingest/runbook" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Restart Procedure",
    "service": "database",
    "component": "postgres",
    "content": "Steps to restart database:\n1. Check active connections\n2. Graceful shutdown\n3. Restart service\n4. Verify health checks",
    "tags": {"category": "operations", "priority": "high"}
  }')
echo "$RUNBOOK_RESPONSE" | jq '.' || echo "$RUNBOOK_RESPONSE"
echo ""

# Test 4: Triage (Synchronous)
echo "4.  Testing Triage (Synchronous)..."
TRIAGE_RESPONSE=$(curl -s -X POST "${API_BASE}/triage" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "High CPU Usage Detected",
    "description": "CPU usage exceeded 90% for 5 minutes on api-gateway service",
    "source": "prometheus",
    "labels": {
      "service": "api-gateway",
      "component": "api",
      "severity": "high"
    }
  }')
echo "$TRIAGE_RESPONSE" | jq '{incident_id, triage: .triage | {severity, category, confidence, summary}, policy_band}' || echo "$TRIAGE_RESPONSE"

INCIDENT_ID=$(echo "$TRIAGE_RESPONSE" | jq -r '.incident_id // empty')
if [ -z "$INCIDENT_ID" ]; then
    echo "     No incident_id returned. Check logs."
    exit 1
fi
echo "    Incident ID: $INCIDENT_ID"
echo ""

# Test 5: Get Incident
echo "5.  Fetching Incident Details..."
curl -s "${API_BASE}/incidents/${INCIDENT_ID}" | jq '{id, policy_band, triage: .triage_output | {severity, category, confidence}}' || echo "   Response received"
echo ""

# Test 6: Resolution (if incident exists)
if [ ! -z "$INCIDENT_ID" ]; then
    echo "6.  Testing Resolution..."
    RESOLUTION_RESPONSE=$(curl -s -X POST "${API_BASE}/resolution?incident_id=${INCIDENT_ID}" \
      -H "Content-Type: application/json")
    echo "$RESOLUTION_RESPONSE" | jq '{incident_id, resolution: .resolution | {risk_level, resolution_steps: (.resolution_steps | length), commands: (.commands | length)}}' || echo "$RESOLUTION_RESPONSE"
    echo ""
fi

# Test 7: Triage (State-Based)
echo "7.  Testing Triage (State-Based HITL)..."
STATE_TRIAGE_RESPONSE=$(curl -s -X POST "${API_BASE}/triage?use_state=true" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Connection Pool Exhausted",
    "description": "Application unable to acquire database connections. Pool size may be too small.",
    "source": "prometheus",
    "labels": {
      "service": "database",
      "component": "postgres"
    }
  }')
echo "$STATE_TRIAGE_RESPONSE" | jq '{incident_id, state: .state | {current_step, policy_band, can_auto_apply, requires_approval}, pending_action: .pending_action}' || echo "$STATE_TRIAGE_RESPONSE"
echo ""

echo " API Testing Complete!"
echo ""
echo " Access Points:"
echo "   API Docs:       http://localhost:8001/docs"
echo ""

