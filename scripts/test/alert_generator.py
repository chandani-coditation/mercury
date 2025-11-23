"""Mock alert generator for testing without K8s/Prometheus."""
import random
import uuid
from datetime import datetime, timezone
from typing import Dict


ALERT_TEMPLATES = [
    {
        "title": "High CPU Usage",
        "description": "CPU usage is above 90% for the last 5 minutes",
        "labels": {"service": "api-gateway", "component": "compute", "severity": "high"},
        "category": "infrastructure"
    },
    {
        "title": "Database Connection Pool Exhausted",
        "description": "All database connections are in use, new requests are being queued",
        "labels": {"service": "user-service", "component": "database", "severity": "critical"},
        "category": "database"
    },
    {
        "title": "High Latency",
        "description": "P95 latency has exceeded 500ms for the last 10 minutes",
        "labels": {"service": "payment-service", "component": "api", "severity": "high"},
        "category": "application"
    },
    {
        "title": "Disk Space Low",
        "description": "Disk usage is above 85% on /var/log partition",
        "labels": {"service": "logging-service", "component": "storage", "severity": "medium"},
        "category": "infrastructure"
    },
    {
        "title": "Memory Leak Detected",
        "description": "Memory usage has been steadily increasing over the last hour",
        "labels": {"service": "analytics-service", "component": "compute", "severity": "high"},
        "category": "application"
    },
    {
        "title": "Network Packet Loss",
        "description": "Packet loss detected on network interface eth0",
        "labels": {"service": "network", "component": "infrastructure", "severity": "critical"},
        "category": "network"
    },
    {
        "title": "Failed Health Check",
        "description": "Service health check endpoint is returning 500 errors",
        "labels": {"service": "auth-service", "component": "api", "severity": "critical"},
        "category": "application"
    },
    {
        "title": "Cache Hit Rate Low",
        "description": "Redis cache hit rate has dropped below 60%",
        "labels": {"service": "cache-service", "component": "cache", "severity": "medium"},
        "category": "application"
    },
    {
        "title": "SSL Certificate Expiring",
        "description": "SSL certificate will expire in 7 days",
        "labels": {"service": "web-service", "component": "security", "severity": "medium"},
        "category": "security"
    },
    {
        "title": "Queue Backlog Growing",
        "description": "Message queue backlog has grown to 10,000 messages",
        "labels": {"service": "message-queue", "component": "queue", "severity": "high"},
        "category": "application"
    }
]


def generate_alert(template: Dict = None) -> Dict:
    """
    Generate a mock alert.
    
    Args:
        template: Optional alert template, otherwise random
    
    Returns:
        Alert dictionary in canonical format
    """
    if template is None:
        template = random.choice(ALERT_TEMPLATES)
    
    alert_id = str(uuid.uuid4())
    
    return {
        "alert_id": alert_id,
        "source": "mock-prometheus",
        "title": template["title"],
        "description": template["description"],
        "labels": template["labels"].copy(),
        "ts": datetime.now(timezone.utc).isoformat()
    }


def generate_random_alert() -> Dict:
    """Generate a random alert from templates."""
    return generate_alert()


def simulate_robusta_alert(ai_service_url: str = "http://localhost:8001") -> Dict:
    """
    Simulate Robusta calling the AI service.
    
    Args:
        ai_service_url: Base URL of AI service
    
    Returns:
        Response from AI service
    """
    import requests
    
    alert = generate_random_alert()
    
    try:
        response = requests.post(
            f"{ai_service_url}/api/v1/triage",
            json=alert,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e), "alert": alert}



