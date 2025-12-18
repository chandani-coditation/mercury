#!/bin/bash
# Test Resolution Endpoint

echo "=========================================="
echo "Testing Resolution Endpoint"
echo "=========================================="
echo ""

# Get incident_id from argument or saved file
if [ -n "$1" ]; then
    INCIDENT_ID="$1"
elif [ -f /tmp/noc_ai_incident_id.txt ]; then
    INCIDENT_ID=$(cat /tmp/noc_ai_incident_id.txt)
else
    echo " Error: No incident_id provided"
    echo ""
    echo "Usage:"
    echo "  ./tests/test_resolution.sh <incident_id>"
    echo ""
    echo "Or run test_triage.sh first to get an incident_id"
    exit 1
fi

echo "Using Incident ID: $INCIDENT_ID"
echo ""

# Call resolution endpoint
echo "Requesting resolution..."
RESOLUTION_RESPONSE=$(curl -s -X POST "http://localhost:8001/api/v1/resolution?incident_id=$INCIDENT_ID" \
  -H "Content-Type: application/json")

echo "$RESOLUTION_RESPONSE" | jq '.'

# Check if resolution was successful
RESOLUTION_STATUS=$(echo "$RESOLUTION_RESPONSE" | jq -r '.resolution // empty')

if [ -n "$RESOLUTION_STATUS" ] && [ "$RESOLUTION_STATUS" != "null" ]; then
    echo ""
    echo " Resolution generated successfully!"
    echo ""
    echo "Resolution Summary:"
    echo "$RESOLUTION_RESPONSE" | jq -r '.resolution.steps[]? | "  - \(.action)"' 2>/dev/null || echo "  (See full response above)"
else
    echo ""
    echo " Resolution failed or no resolution returned"
    echo ""
    echo "Response:"
    echo "$RESOLUTION_RESPONSE" | jq '.'
fi

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="

