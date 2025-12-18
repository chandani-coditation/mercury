"""Mock alert generator for testing without K8s/Prometheus.

Now biased toward real incident data from tickets_data/*.csv so generated alerts
look closer to production payloads. Falls back to curated templates if the CSVs
aren't present.
"""
import csv
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


ALLOWED_CATEGORIES = {"database", "network", "application", "infrastructure", "security", "other"}

ALERT_TEMPLATES = [
    {
        "title": "High CPU Usage",
        "description": "CPU usage is above 90% for the last 5 minutes",
        "labels": {"service": "api-gateway", "component": "compute", "severity": "high"},
        "category": "infrastructure",
    },
    {
        "title": "Database Connection Pool Exhausted",
        "description": "All database connections are in use, new requests are being queued",
        "labels": {"service": "user-service", "component": "database", "severity": "critical"},
        "category": "database",
    },
    {
        "title": "High Latency",
        "description": "P95 latency has exceeded 500ms for the last 10 minutes",
        "labels": {"service": "payment-service", "component": "api", "severity": "high"},
        "category": "application",
    },
    {
        "title": "Disk Space Low",
        "description": "Disk usage is above 85% on /var/log partition",
        "labels": {"service": "logging-service", "component": "storage", "severity": "medium"},
        "category": "infrastructure",
    },
    {
        "title": "Memory Leak Detected",
        "description": "Memory usage has been steadily increasing over the last hour",
        "labels": {"service": "analytics-service", "component": "compute", "severity": "high"},
        "category": "application",
    },
    {
        "title": "Network Packet Loss",
        "description": "Packet loss detected on network interface eth0",
        "labels": {"service": "network", "component": "infrastructure", "severity": "critical"},
        "category": "network",
    },
    {
        "title": "Failed Health Check",
        "description": "Service health check endpoint is returning 500 errors",
        "labels": {"service": "auth-service", "component": "api", "severity": "critical"},
        "category": "application",
    },
    {
        "title": "Cache Hit Rate Low",
        "description": "Redis cache hit rate has dropped below 60%",
        "labels": {"service": "cache-service", "component": "cache", "severity": "medium"},
        "category": "application",
    },
    {
        "title": "SSL Certificate Expiring",
        "description": "SSL certificate will expire in 7 days",
        "labels": {"service": "web-service", "component": "security", "severity": "medium"},
        "category": "security",
    },
    {
        "title": "Queue Backlog Growing",
        "description": "Message queue backlog has grown to 10,000 messages",
        "labels": {"service": "message-queue", "component": "queue", "severity": "high"},
        "category": "application",
    },
]

_CSV_SAMPLES: List[Dict] = []


def _slug(text: str, default: str) -> str:
    text = (text or "").strip()
    if not text:
        return default
    return (
        text.replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
        .replace("_", "-")
        .replace(".", "-")
        .lower()
    )


def _normalize_category(raw: str) -> str:
    raw_lower = (raw or "").lower()
    for key in ALLOWED_CATEGORIES:
        if key in raw_lower:
            return key
    # heuristics for common variants from the CSV
    if "monitor" in raw_lower or "alert" in raw_lower:
        return "infrastructure"
    if "db" in raw_lower or "sql" in raw_lower:
        return "database"
    return "other"


def _load_csv_samples(limit: int = 800) -> None:
    if _CSV_SAMPLES:
        return
    repo_root = Path(__file__).resolve().parents[1]
    csv_path = repo_root / "tickets_data" / "Database Alerts Filtered - Sheet1.csv"
    if not csv_path.exists():
        return
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                title = (row.get("short_description") or row.get("description") or "").strip()
                description = (row.get("description") or row.get("short_description") or "").strip()
                cmdb_ci = row.get("cmdb_ci") or ""
                category = _normalize_category(row.get("category"))
                impact = (row.get("impact") or "").strip()
                urgency = (row.get("urgency") or "").strip()
                if not title:
                    continue
                _CSV_SAMPLES.append(
                    {
                        "title": title,
                        "description": description or title,
                        "labels": {
                            "service": _slug(cmdb_ci, "database"),
                            "component": _slug(row.get("category"), "component"),
                            "impact": impact or "3-low",
                            "urgency": urgency or "3-low",
                        },
                        "category": category,
                    }
                )
                if idx >= limit:
                    break
    except Exception:
        # fall back silently; templates will be used
        _CSV_SAMPLES.clear()


def _pick_template() -> Dict:
    _load_csv_samples()
    if _CSV_SAMPLES and random.random() < 0.75:
        return random.choice(_CSV_SAMPLES)
    return random.choice(ALERT_TEMPLATES)


def generate_alert(template: Dict = None) -> Dict:
    """
    Generate a mock alert, favoring CSV-derived samples for realism.

    Args:
        template: Optional alert template, otherwise random

    Returns:
        Alert dictionary in canonical format
    """
    if template is None:
        template = _pick_template()

    alert_id = str(uuid.uuid4())

    return {
        "alert_id": alert_id,
        "source": "mock-prometheus",
        "title": template["title"],
        "description": template["description"],
        "labels": template["labels"].copy(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def generate_random_alert() -> Dict:
    """Generate a random alert from templates or CSV samples."""
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
        response = requests.post(f"{ai_service_url}/api/v1/triage", json=alert, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e), "alert": alert}
