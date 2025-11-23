# Triage Testing Example: "High CPU usage on API Gateway"

This document provides a complete example for testing the triage functionality in the UI.

## Example Alert Data

### JSON Payload Structure

```json
{
  "alert_id": "cpu-high-api-gateway-001",
  "source": "prometheus",
  "title": "High CPU usage on API Gateway",
  "description": "CPU usage on api-gateway-01 has exceeded 90% for the past 15 minutes. Average CPU utilization is at 94.2%. This is affecting response times for incoming API requests. Error rate has increased from 0.1% to 2.3% during this period.",
  "labels": {
    "service": "api-gateway",
    "component": "gateway",
    "environment": "production",
    "instance": "api-gateway-01",
    "alertname": "HighCPUUsage",
    "severity": "critical"
  },
  "ts": "2024-01-15T10:30:00Z"
}
```

## Testing Methods

### Method 1: Using the Test Script

Run the provided test script:

```bash
./test_triage_example.sh
```

This will:
- Test basic synchronous triage
- Test state-based HITL triage with human review
- Show JSON responses

### Method 2: Using cURL Directly

#### Basic Triage (Synchronous)

```bash
curl -X POST "http://localhost:8001/api/v1/triage" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "cpu-high-api-gateway-001",
    "source": "prometheus",
    "title": "High CPU usage on API Gateway",
    "description": "CPU usage on api-gateway-01 has exceeded 90% for the past 15 minutes. Average CPU utilization is at 94.2%. This is affecting response times for incoming API requests. Error rate has increased from 0.1% to 2.3% during this period.",
    "labels": {
      "service": "api-gateway",
      "component": "gateway",
      "environment": "production",
      "instance": "api-gateway-01",
      "alertname": "HighCPUUsage",
      "severity": "critical"
    },
    "ts": "2024-01-15T10:30:00Z"
  }'
```

#### State-Based HITL Triage (with Human Review)

```bash
curl -X POST "http://localhost:8001/api/v1/triage?use_state=true" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "cpu-high-api-gateway-002",
    "source": "prometheus",
    "title": "High CPU usage on API Gateway",
    "description": "CPU usage on api-gateway-02 has exceeded 95% for the past 20 minutes. Average CPU utilization is at 96.8%. Response times have degraded from 50ms to 450ms. Multiple downstream services are experiencing timeouts. Memory usage is also elevated at 85%.",
    "labels": {
      "service": "api-gateway",
      "component": "gateway",
      "environment": "production",
      "instance": "api-gateway-02",
      "alertname": "HighCPUUsage",
      "severity": "critical",
      "team": "platform",
      "region": "us-east-1"
    },
    "ts": "2024-01-15T10:35:00Z"
  }'
```

### Method 3: Using the API Documentation (Swagger UI)

1. Open http://localhost:8001/docs in your browser
2. Navigate to the `/api/v1/triage` endpoint
3. Click "Try it out"
4. Paste the JSON payload above
5. Set `use_state` to `true` for HITL workflow
6. Click "Execute"

### Method 4: Testing via UI (Future Enhancement)

Currently, the UI displays incidents after they're created via API. To test:

1. **Submit triage via API** (using any method above)
2. **Open the UI** at http://localhost:3000
3. **View the incident** in the incident list
4. **For HITL triage** (`use_state=true`):
   - You should see a pending action card
   - Review the triage output
   - Approve or edit the triage assessment
   - The agent will resume after your response

## Expected Response

### Basic Triage Response

```json
{
  "incident_id": "uuid-here",
  "triage": {
    "severity": "high",
    "category": "performance",
    "summary": "High CPU usage detected on API Gateway instance...",
    "likely_cause": "Possible causes include: high request volume, inefficient query processing, or resource constraints...",
    "affected_services": ["api-gateway", "downstream-services"],
    "recommended_actions": [
      "Scale up API Gateway instances",
      "Check for slow queries or inefficient code paths",
      "Review recent deployments"
    ],
    "confidence": 0.85
  },
  "evidence_chunks": [...],
  "policy_band": "AUTO",
  "policy_decision": {...}
}
```

### State-Based HITL Response

The response will include:
- `incident_id`: UUID of the created incident
- `state`: Current agent state
- `pending_action`: Action requiring human review (if policy requires it)
- `websocket_url`: WebSocket endpoint for real-time updates

## What to Check in the UI

After submitting a triage:

1. **Incident List** (http://localhost:3000):
   - New incident should appear
   - Check severity badge
   - Check policy band (AUTO/PROPOSE/REVIEW)

2. **Incident Detail** (click on incident):
   - View triage output
   - See evidence chunks used
   - Check policy decision
   - For HITL: See pending action card

3. **HITL Workflow** (if `use_state=true`):
   - Progress stepper showing current step
   - Pending action card with review form
   - Real-time state updates via WebSocket
   - Ability to approve/edit/reject

4. **WebSocket Connection**:
   - Open browser DevTools → Network → WS
   - Connect to `ws://localhost:8001/api/v1/agents/{incident_id}/state/stream`
   - See real-time state emissions

## Additional Test Variations

### Variation 1: Medium Severity

```json
{
  "alert_id": "cpu-medium-api-gateway-003",
  "source": "prometheus",
  "title": "Elevated CPU usage on API Gateway",
  "description": "CPU usage on api-gateway-03 is at 75% for the past 10 minutes. No significant impact on response times yet.",
  "labels": {
    "service": "api-gateway",
    "component": "gateway",
    "environment": "staging",
    "severity": "medium"
  },
  "ts": "2024-01-15T10:40:00Z"
}
```

### Variation 2: With More Context

```json
{
  "alert_id": "cpu-high-api-gateway-004",
  "source": "prometheus",
  "title": "High CPU usage on API Gateway",
  "description": "CPU usage spike detected. Recent deployment of v2.3.1 occurred 30 minutes ago. Multiple users reporting slow API responses. Database connection pool is at 90% capacity. Consider rolling back deployment or scaling horizontally.",
  "labels": {
    "service": "api-gateway",
    "component": "gateway",
    "environment": "production",
    "deployment": "v2.3.1",
    "severity": "critical",
    "team": "platform",
    "region": "us-east-1",
    "datacenter": "dc1"
  },
  "ts": "2024-01-15T10:45:00Z"
}
```

## Troubleshooting

### Issue: No incidents appear in UI
- **Solution**: Check if the API call succeeded. Verify the incident was created in the database.

### Issue: Pending action not showing
- **Solution**: Ensure `use_state=true` was used and the policy band is PROPOSE or REVIEW (not AUTO).

### Issue: WebSocket not connecting
- **Solution**: Check browser console for errors. Verify the WebSocket URL format is correct.

### Issue: Triage returns error
- **Solution**: Check API logs: `docker-compose logs -f ai-service`. Verify OPENAI_API_KEY is set correctly.

## Next Steps After Triage

1. **Review Triage Output**: Check if severity, category, and recommendations are accurate
2. **Provide Feedback**: Use the feedback endpoint to improve future triages
3. **Trigger Resolution**: After triage is approved, trigger the resolution copilot agent
4. **Monitor**: Watch the incident timeline for state transitions

