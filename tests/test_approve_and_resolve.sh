#!/bin/bash
# Test complete flow: Triage -> Approve -> Resolution

INCIDENT_ID="${1:-a809753d-f377-443e-8a88-cc9d88eb2b37}"

echo "=========================================="
echo "Complete Test Flow: Approve & Resolve"
echo "=========================================="
echo ""

echo "Step 1: Getting incident details..."
INCIDENT=$(curl -s -X GET "http://localhost:8001/api/v1/incidents/$INCIDENT_ID")
echo "$INCIDENT" | jq '.triage_output | {severity, category, routing, confidence}'
echo ""

echo "Step 2: Approving incident (setting policy_band to AUTO)..."
# Build JSON payload using jq to properly escape the triage_output
APPROVE_PAYLOAD=$(echo "$INCIDENT" | jq -c '{
  feedback_type: "triage",
  user_edited: .triage_output,
  notes: "Approved for testing - allowing resolution to proceed",
  policy_band: "AUTO"
}')

APPROVE_RESPONSE=$(curl -s -X PUT "http://localhost:8001/api/v1/incidents/$INCIDENT_ID/feedback" \
  -H "Content-Type: application/json" \
  -d "$APPROVE_PAYLOAD")

echo "$APPROVE_RESPONSE" | jq '.'
echo ""

echo "Step 3: Requesting resolution..."
RESOLUTION_RESPONSE=$(curl -s -X POST "http://localhost:8001/api/v1/resolution?incident_id=$INCIDENT_ID" \
  -H "Content-Type: application/json")

echo "$RESOLUTION_RESPONSE" | jq '.'

if echo "$RESOLUTION_RESPONSE" | jq -e '.resolution' > /dev/null 2>&1; then
    echo ""
    echo " Resolution generated successfully!"
    echo ""
    echo "Resolution Summary:"
    STEPS=$(echo "$RESOLUTION_RESPONSE" | jq -r '.resolution.steps[]? // empty' 2>/dev/null)
    if [ -n "$STEPS" ]; then
        echo "$STEPS" | sed 's/^/  - /'
    else
        echo "$RESOLUTION_RESPONSE" | jq '.resolution'
    fi
else
    echo ""
    echo " Resolution failed"
    echo "$RESOLUTION_RESPONSE" | jq '.'
fi

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="

