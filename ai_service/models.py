"""Pydantic models for AI service."""
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime


class Alert(BaseModel):
    """Canonical alert model."""
    alert_id: str
    source: str
    title: str
    description: str
    labels: Dict[str, str] = {}
    ts: Optional[datetime] = None  # Optional: defaults to current time if not provided


class TriageOutput(BaseModel):
    """Triage output structure."""
    severity: str  # critical, high, medium, low
    category: str  # e.g., "database", "network", "application"
    summary: str
    likely_cause: str
    routing: str  # Team queue assignment (e.g., "SE DBA SQL", "NOC", "SE Windows")
    affected_services: List[str]
    recommended_actions: List[str]
    confidence: float  # 0.0 to 1.0


class ResolutionOutput(BaseModel):
    """Resolution output structure."""
    steps: List[str]  # Renamed from resolution_steps
    commands_by_step: Optional[Dict[str, List[str]]] = None  # Dict mapping step index to commands
    commands: Optional[List[str]] = None  # Legacy flat list (deprecated, use commands_by_step)
    rollback_plan: Optional[List[str]] = None
    estimated_time_minutes: int
    risk_level: str  # low, medium, high
    requires_approval: bool
    confidence: Optional[float] = None  # System's confidence in these steps (0.0-1.0)
    reasoning: Optional[str] = None  # Short explanation citing evidence chunks (renamed from rationale)
    rationale: Optional[str] = None  # Legacy field (deprecated, use reasoning)
    provenance: Optional[List[Dict[str, str]]] = None  # Array of {doc_id, chunk_id} references


class FeedbackInput(BaseModel):
    """Feedback input from human analyst."""
    feedback_type: str  # "triage" or "resolution"
    user_edited: Dict
    notes: Optional[str] = None
    policy_band: Optional[str] = None  # Optional: Override policy band (AUTO, PROPOSE, REVIEW) for approval



