#!/bin/bash
# Ensure Homebrew binaries are on PATH for macOS (Apple Silicon default)
export PATH="/opt/homebrew/bin:$PATH"

# Send fake Prometheus alerts to Robusta
# This simulates Prometheus alertmanager webhook calls

set -e

ROBUSTA_NAMESPACE=${ROBUSTA_NAMESPACE:-robusta}
ALERT_COUNT=${1:-5}

echo "📨 Sending fake Prometheus alerts to Robusta"
echo "============================================"
echo ""

# Get Robusta service
ROBUSTA_SVC=$(kubectl get svc -n $ROBUSTA_NAMESPACE -l app=robusta-runner -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "$ROBUSTA_SVC" ]; then
    echo "❌ Robusta service not found. Is Robusta installed?"
    echo ""
    echo "Run: ./scripts/setup_robusta.sh"
    exit 1
fi

# Port forward to Robusta
echo "🔗 Setting up port-forward to Robusta..."
kubectl port-forward -n $ROBUSTA_NAMESPACE svc/$ROBUSTA_SVC 5000:5000 > /dev/null 2>&1 &
PF_PID=$!
sleep 2

# Cleanup function
cleanup() {
    kill $PF_PID 2>/dev/null || true
}
trap cleanup EXIT

echo "✓ Connected to Robusta"
echo ""

# Alert templates
ALERTS=(
    '{"labels":{"alertname":"HighCPUUsage","severity":"high","service":"api-gateway"},"annotations":{"summary":"CPU usage above 90%","description":"CPU usage is above 90% for the last 5 minutes"},"startsAt":"2024-01-15T10:00:00Z","endsAt":"2024-01-15T10:05:00Z"}'
    '{"labels":{"alertname":"DatabaseConnectionPoolExhausted","severity":"critical","service":"user-service"},"annotations":{"summary":"Database connection pool exhausted","description":"All database connections are in use"},"startsAt":"2024-01-15T10:00:00Z","endsAt":"2024-01-15T10:05:00Z"}'
    '{"labels":{"alertname":"HighLatency","severity":"high","service":"payment-service"},"annotations":{"summary":"P95 latency exceeded 500ms","description":"P95 latency has exceeded 500ms for the last 10 minutes"},"startsAt":"2024-01-15T10:00:00Z","endsAt":"2024-01-15T10:05:00Z"}'
    '{"labels":{"alertname":"DiskSpaceLow","severity":"medium","service":"logging-service"},"annotations":{"summary":"Disk usage above 85%","description":"Disk usage is above 85% on /var/log partition"},"startsAt":"2024-01-15T10:00:00Z","endsAt":"2024-01-15T10:05:00Z"}'
    '{"labels":{"alertname":"MemoryLeakDetected","severity":"high","service":"analytics-service"},"annotations":{"summary":"Memory leak detected","description":"Memory usage has been steadily increasing"},"startsAt":"2024-01-15T10:00:00Z","endsAt":"2024-01-15T10:05:00Z"}'
)

# Send alerts
for i in $(seq 1 $ALERT_COUNT); do
    ALERT_INDEX=$((($i - 1) % ${#ALERTS[@]}))
    ALERT="${ALERTS[$ALERT_INDEX]}"
    
    # Create Prometheus alertmanager webhook payload
    PAYLOAD=$(cat <<EOF
{
  "version": "4",
  "groupKey": "test-group",
  "status": "firing",
  "receiver": "robusta",
  "groupLabels": {},
  "commonLabels": {},
  "commonAnnotations": {},
  "externalURL": "http://localhost:9093",
  "alerts": [$ALERT]
}
EOF
)
    
    echo "[$i/$ALERT_COUNT] Sending alert: $(echo $ALERT | jq -r '.labels.alertname')"
    
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        http://localhost:5000/webhook 2>/dev/null)
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)
    
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "202" ]; then
        echo "  ✓ Alert sent successfully"
    else
        echo "  ⚠️  Alert sent (HTTP $HTTP_CODE)"
    fi
    
    sleep 1
done

echo ""
echo "✅ Sent $ALERT_COUNT fake alerts to Robusta"
echo ""
echo "Check Robusta logs:"
echo "  kubectl logs -n $ROBUSTA_NAMESPACE -l app=robusta-runner -f"


