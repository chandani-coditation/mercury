#!/bin/bash
# Ensure Homebrew binaries are on PATH for macOS (Apple Silicon default)
export PATH="/opt/homebrew/bin:$PATH"

# Setup script for Robusta with fake Prometheus alerts
# This sets up a local K8s cluster (kind) and installs Robusta

set -e

echo "🚀 Setting up Robusta with Fake Prometheus Alerts"
echo "=================================================="
echo ""

# Check if kind is installed
if ! command -v kind &> /dev/null; then
    echo " kind is not installed"
    echo ""
    echo "Install kind with:"
    echo "  brew install kind  # macOS"
    echo "  or visit: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo " kubectl is not installed"
    echo ""
    echo "Install kubectl with:"
    echo "  brew install kubectl  # macOS"
    exit 1
fi

# Check if helm is installed
if ! command -v helm &> /dev/null; then
    echo " helm is not installed"
    echo ""
    echo "Install helm with:"
    echo "  brew install helm  # macOS"
    exit 1
fi

echo " Prerequisites check passed"
echo ""

# Check if cluster already exists
if kind get clusters | grep -q "noc-cluster"; then
    echo "  Cluster 'noc-cluster' already exists"
    read -p "Delete and recreate? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "  Deleting existing cluster..."
        kind delete cluster --name noc-cluster
    else
        echo "Using existing cluster"
        kubectl cluster-info --context kind-noc-cluster
        exit 0
    fi
fi

# Create kind cluster
echo " Creating kind cluster..."
# Check if ports 80/443 are in use
if lsof -i :80 >/dev/null 2>&1 || lsof -i :443 >/dev/null 2>&1; then
    echo "  Ports 80/443 are in use, using alternative ports (8080/8443)"
    cat <<EOF | kind create cluster --name noc-cluster --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 8080
    protocol: TCP
  - containerPort: 443
    hostPort: 8443
    protocol: TCP
EOF
else
    cat <<EOF | kind create cluster --name noc-cluster --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
EOF
fi

echo " Cluster created"
echo ""

# Wait for cluster to be ready
echo "⏳ Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready node --all --timeout=90s

# Install Prometheus (for fake alerts)
echo "📊 Installing Prometheus..."
kubectl create namespace monitoring 2>/dev/null || true

# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack (includes Prometheus)
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --set prometheus.prometheusSpec.service.type=NodePort \
  --set prometheus.prometheusSpec.service.nodePort=30900 \
  --wait

echo " Prometheus installed"
echo ""

# Install Robusta
echo " Installing Robusta..."
kubectl create namespace robusta 2>/dev/null || true

# Add Robusta Helm repo
helm repo add robusta https://robusta-charts.storage.googleapis.com
helm repo update

# Install Robusta with a sink (required)
# Create a values file for Robusta
cat > /tmp/robusta-values.yaml <<EOF
clusterName: "noc-cluster"
globalConfig:
  account_id: "dev"
  signing_key: "dev-key"

runner:
  enablePrometheusAlerts: true

# Use stdout sink for testing (simplest option)
sinksConfig:
  - name: "default"
    stdout:
      enabled: true
EOF

helm install robusta robusta/robusta \
  -n robusta \
  -f /tmp/robusta-values.yaml \
  --wait

echo " Robusta installed"
echo ""

# Get Robusta webhook URL
echo " Getting Robusta webhook URL..."
sleep 10  # Wait for Robusta to be fully ready

ROBUSTA_WEBHOOK=$(kubectl get svc -n robusta robusta-runner -o jsonpath='{.spec.clusterIP}')
ROBUSTA_PORT=$(kubectl get svc -n robusta robusta-runner -o jsonpath='{.spec.ports[0].port}')

echo " Robusta webhook: http://${ROBUSTA_WEBHOOK}:${ROBUSTA_PORT}/webhook"
echo ""

# Create a service to expose AI service to Robusta
echo "🔗 Setting up AI service connection..."
echo ""
echo "Note: You'll need to deploy your AI service to the cluster or"
echo "      expose it via port-forward/ingress for Robusta to reach it."
echo ""

echo " Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Deploy your AI service to the cluster (or use port-forward)"
echo "  2. Create Robusta playbook (see scripts/create_robusta_playbook.sh)"
echo "  3. Send fake Prometheus alerts (see scripts/send_fake_prometheus_alerts.sh)"
echo ""
echo "To access Prometheus UI:"
echo "  kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090"
echo ""
echo "To check Robusta logs:"
echo "  kubectl logs -n robusta -l app=robusta-runner -f"


