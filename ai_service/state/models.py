"""State models for state-based HITL workflow."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal, Any
from datetime import datetime
from enum import Enum


class AgentStep(str, Enum):
    """Agent execution steps."""

    INITIALIZED = "initialized"
    RETRIEVING_CONTEXT = "retrieving_context"
    CONTEXT_RETRIEVED = "context_retrieved"
    CALLING_LLM = "calling_llm"
    LLM_COMPLETED = "llm_completed"
    VALIDATING = "validating"
    VALIDATION_COMPLETE = "validation_complete"
    POLICY_EVALUATING = "policy_evaluating"
    POLICY_EVALUATED = "policy_evaluated"
    PAUSED_FOR_REVIEW = "paused_for_review"
    RESUMED_FROM_REVIEW = "resumed_from_review"
    STORING = "storing"
    COMPLETED = "completed"
    ERROR = "error"


class PendingAction(BaseModel):
    """Pending HITL action awaiting human response."""

    action_name: str  # e.g., "review_triage", "review_resolution"
    action_type: Literal["review_triage", "review_resolution", "approve_policy"]
    incident_id: str
    description: str
    payload: Dict[str, Any]  # Action-specific data
    created_at: datetime
    expires_at: Optional[datetime] = None


class AgentState(BaseModel):
    """Canonical agent state for HITL workflow."""

    # Incident metadata
    incident_id: Optional[str] = None
    alert_id: Optional[str] = None
    alert: Optional[Dict[str, Any]] = None

    # Current step
    current_step: AgentStep = AgentStep.INITIALIZED
    agent_type: Literal["triage", "resolution"] = "triage"

    # Progress tracking
    context_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    context_chunks_count: int = 0

    # Triage state
    triage_output: Optional[Dict[str, Any]] = None
    triage_evidence: Optional[Dict[str, Any]] = None

    # Resolution state
    resolution_output: Optional[Dict[str, Any]] = None
    resolution_evidence: Optional[Dict[str, Any]] = None

    # Policy state
    policy_band: Optional[str] = None  # AUTO, PROPOSE, REVIEW, PENDING
    policy_decision: Optional[Dict[str, Any]] = None
    requires_approval: bool = False
    can_auto_apply: bool = False

    # Pending actions
    pending_action: Optional[PendingAction] = None

    # Logs and messages
    logs: List[Dict[str, str]] = Field(default_factory=list)  # {timestamp, level, message}
    messages: List[str] = Field(default_factory=list)

    # Metadata
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error state
    error: Optional[str] = None
    warning: Optional[str] = None

    class Config:
        use_enum_values = True


class ActionResponse(BaseModel):
    """Human response to a pending action."""

    action_name: str
    incident_id: str
    approved: bool = True
    user_edited: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    policy_band: Optional[str] = None  # For policy approval
    responded_at: datetime = Field(default_factory=datetime.utcnow)
