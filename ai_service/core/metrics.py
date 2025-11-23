"""Prometheus metrics for NOC Agent AI."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from typing import Optional
import time


# Request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Agent metrics
triage_requests_total = Counter(
    "triage_requests_total",
    "Total triage requests",
    ["status"]  # success, validation_error, llm_error, etc.
)

triage_duration_seconds = Histogram(
    "triage_duration_seconds",
    "Triage processing duration in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

resolution_requests_total = Counter(
    "resolution_requests_total",
    "Total resolution requests",
    ["status", "policy_band"]  # success, validation_error, skipped, etc.
)

resolution_duration_seconds = Histogram(
    "resolution_duration_seconds",
    "Resolution processing duration in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# LLM metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["agent_type", "model", "status"]  # triage/resolution, model name, success/error
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["agent_type", "type"]  # triage/resolution, prompt/completion
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM API request duration in seconds",
    ["agent_type", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Database metrics
db_queries_total = Counter(
    "db_queries_total",
    "Total database queries",
    ["operation", "status"]  # select, insert, update, success/error
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Retrieval metrics
retrieval_requests_total = Counter(
    "retrieval_requests_total",
    "Total retrieval requests",
    ["agent_type", "status"]  # triage/resolution, success/error
)

retrieval_chunks_returned = Histogram(
    "retrieval_chunks_returned",
    "Number of chunks returned per retrieval",
    ["agent_type"],
    buckets=[1, 3, 5, 10, 15, 20, 30]
)

retrieval_duration_seconds = Histogram(
    "retrieval_duration_seconds",
    "Retrieval duration in seconds",
    ["agent_type"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

# System metrics
active_incidents = Gauge(
    "active_incidents",
    "Number of active incidents",
    ["status"]  # pending, triaged, resolved
)

policy_decisions_total = Counter(
    "policy_decisions_total",
    "Total policy decisions",
    ["policy_band"]  # AUTO, PROPOSE, REVIEW
)

# State-based HITL metrics
agent_state_emitted_total = Counter(
    "agent_state_emitted_total",
    "Total agent state emissions",
    ["agent_type", "step"]  # triage/resolution, step name
)

hitl_actions_pending = Gauge(
    "hitl_actions_pending",
    "Number of pending HITL actions",
    ["action_type"]  # review_triage, review_resolution, approve_policy
)

hitl_actions_total = Counter(
    "hitl_actions_total",
    "Total HITL actions",
    ["action_type", "status"]  # action type, created/resumed/timeout
)

hitl_action_duration_seconds = Histogram(
    "hitl_action_duration_seconds",
    "HITL action duration (from creation to response) in seconds",
    ["action_type"],
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600]
)


def get_metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


class MetricsTimer:
    """Context manager for timing operations."""
    
    def __init__(self, histogram: Histogram, labels: Optional[dict] = None):
        """
        Initialize timer.
        
        Args:
            histogram: Prometheus Histogram metric
            labels: Optional labels dict
        """
        self.histogram = histogram
        self.labels = labels or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.labels:
            self.histogram.labels(**self.labels).observe(duration)
        else:
            self.histogram.observe(duration)

