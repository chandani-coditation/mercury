#!/bin/bash
# Test Triage Endpoint with Real ServiceNow Ticket Data

echo "=========================================="
echo "Testing Triage Endpoint"
echo "=========================================="
echo ""

# Example 1: SSIS Package Failure (based on INC6050935)
echo "Example 1: SSIS Package Execution Failure"
echo "-------------------------------------------"
TRIAGE_RESPONSE=$(curl -s -X POST "http://localhost:8001/api/v1/triage" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "test-ssis-failure-001",
    "title": "SentryOne Monitoring/Alert - SSIS Package Execution Failed",
    "description": "Job '\''BeyondInsight - Process Daily'\'' Failed on Step 1 [Execute SSIS Package]. Executed as user: INT\\ClustAgtSrvc. Started: 12:00:00 AM Finished: 12:05:44 AM Elapsed: 343.75 seconds. The package execution failed. Connection: BRPRWSQL312.INT.MGC.COM. Object Name: BeyondInsight - Process Daily.",
    "source": "monitoring",
    "labels": {
      "service": "database",
      "component": "sql-server",
      "cmdb_ci": "Database-SQL",
      "category": "Monitoring/Alert"
    }
  }')

echo "$TRIAGE_RESPONSE" | jq '.'

# Extract incident_id for resolution test
INCIDENT_ID=$(echo "$TRIAGE_RESPONSE" | jq -r '.incident_id // empty')

if [ -n "$INCIDENT_ID" ] && [ "$INCIDENT_ID" != "null" ]; then
    echo ""
    echo " Triage successful! Incident ID: $INCIDENT_ID"
    echo ""
    echo "To test resolution, run:"
    echo "  ./tests/test_resolution.sh $INCIDENT_ID"
    echo ""
    # Save incident_id for resolution test
    echo "$INCIDENT_ID" > /tmp/noc_ai_incident_id.txt
else
    echo ""
    echo " Triage failed or no incident_id returned"
fi

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="

