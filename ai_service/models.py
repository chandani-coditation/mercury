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
    ts: datetime


class TriageOutput(BaseModel):
    """Triage output structure."""
    severity: str  # critical, high, medium, low
    category: str  # e.g., "database", "network", "application"
    summary: str
    likely_cause: str
    affected_services: List[str]
    recommended_actions: List[str]
    confidence: float  # 0.0 to 1.0


class ResolutionOutput(BaseModel):
    """Resolution output structure."""
    resolution_steps: List[str]
    commands: Optional[List[str]] = None
    rollback_plan: Optional[List[str]] = None
    estimated_time_minutes: int
    risk_level: str  # low, medium, high
    requires_approval: bool


class FeedbackInput(BaseModel):
    """Feedback input from human analyst."""
    feedback_type: str  # "triage" or "resolution"
    user_edited: Dict
    notes: Optional[str] = None
    policy_band: Optional[str] = None  # Optional: Override policy band (AUTO, PROPOSE, REVIEW) for approval



