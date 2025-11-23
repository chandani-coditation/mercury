#!/bin/bash
# Example script to test triage with "High CPU usage on API Gateway"

echo "🚀 Testing Triage: High CPU usage on API Gateway"
echo "================================================"

# Example 1: Basic triage (synchronous, no HITL)
echo -e "\n📋 Example 1: Basic Triage (Synchronous)"
echo "-------------------------------------------"
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
  }' | python3 -m json.tool

echo -e "\n\n⏳ Waiting 3 seconds before next example..."
sleep 3

# Example 2: State-based HITL triage (with human review)
echo -e "\n📋 Example 2: State-Based HITL Triage (with Human Review)"
echo "-----------------------------------------------------------"
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
  }' | python3 -m json.tool

echo -e "\n\n✅ Test complete!"
echo ""
echo "📝 Next Steps:"
echo "1. Check the UI at http://localhost:3000 to see the incidents"
echo "2. For Example 2, you should see a pending action requiring human review"
echo "3. Use the WebSocket connection to see real-time state updates"
echo "4. Review and approve/reject the triage output in the UI"

