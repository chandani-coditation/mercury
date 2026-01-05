"""Pydantic models for AI service."""

from pydantic import BaseModel
from typing import Dict, List, Optional, Union
from datetime import datetime


class Alert(BaseModel):
    """Canonical alert model."""

    alert_id: str
    source: str
    title: str
    description: str
    labels: Dict[str, str] = {}
    affected_services: Optional[List[str]] = None  # Affected services/CI from alert
    ts: Optional[datetime] = None  # Optional: defaults to current time if not provided


class IncidentSignature(BaseModel):
    """Incident signature classification."""

    failure_type: str  # e.g., "SQL_AGENT_JOB_FAILURE"
    error_class: str  # e.g., "SERVICE_ACCOUNT_DISABLED"


class MatchedEvidence(BaseModel):
    """Matched evidence references."""

    incident_signatures: List[str]  # List of incident_signature_id values
    runbook_refs: List[str]  # List of runbook_id values


class TriageOutput(BaseModel):
    """Triage output structure per architecture.

    Per architecture: Triage agent classifies incidents only.
    Does NOT generate resolution steps, rank actions, or invent causes.
    """

    incident_signature: IncidentSignature
    matched_evidence: MatchedEvidence
    severity: str  # critical, high, medium, low (derived from impact/urgency)
    confidence: float  # 0.0 to 1.0
    policy: str  # AUTO, PROPOSE, REVIEW (determined by policy gate, but included in output)
    routing: Optional[str] = (
        None  # Team queue assignment (e.g., "SE DBA SQL") - derived from assignment_group
    )
    impact: Optional[str] = (
        None  # Original impact value from historical evidence (e.g., "2 - Medium", "1 - High")
    )
    urgency: Optional[str] = (
        None  # Original urgency value from historical evidence (e.g., "2 - Medium", "1 - High")
    )
    likely_cause: Optional[str] = (
        None  # Most likely root cause based on alert description and matched incident signatures (max 300 chars)
    )


class RollbackPlan(BaseModel):
    """Structured rollback plan for production safety."""

    steps: List[str]  # Ordered rollback actions (reverse of resolution steps)
    commands_by_step: Optional[Dict[str, List[str]]] = None  # Rollback commands mapped to steps
    preconditions: Optional[List[str]] = (
        None  # What to verify BEFORE rollback (state checks, backups)
    )
    estimated_time_minutes: Optional[int] = None  # Time to complete rollback
    triggers: Optional[List[str]] = None  # Conditions indicating rollback is needed


class ResolutionOutput(BaseModel):
    """Resolution output structure."""

    steps: List[str]  # Renamed from resolution_steps
    commands_by_step: Optional[Dict[str, List[str]]] = None  # Dict mapping step index to commands
    commands: Optional[List[str]] = None  # Legacy flat list (deprecated, use commands_by_step)
    rollback_plan: Optional[Union[List[str], RollbackPlan, Dict]] = (
        None  # Support both legacy (list) and new (structured) formats
    )
    estimated_time_minutes: int
    risk_level: str  # low, medium, high
    requires_approval: bool
    confidence: Optional[float] = None  # System's confidence in these steps (0.0-1.0)
    reasoning: Optional[str] = (
        None  # Short explanation citing evidence chunks (renamed from rationale)
    )
    rationale: Optional[str] = None  # Legacy field (deprecated, use reasoning)
    provenance: Optional[List[Dict[str, str]]] = None  # Array of {doc_id, chunk_id} references


class FeedbackInput(BaseModel):
    """Feedback input from human analyst."""

    feedback_type: str  # "triage" or "resolution"
    user_edited: Dict
    notes: Optional[str] = None
    policy_band: Optional[str] = (
        None  # Optional: Override policy band (AUTO, PROPOSE, REVIEW) for approval
    )
