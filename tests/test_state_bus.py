"""Tests for the state bus recovery and timeout logic."""
from datetime import datetime, timedelta

import pytest

from ai_service.state import AgentState, PendingAction, AgentStep, StateBus
from ai_service.core import hitl_actions_pending


class StubAgentStateRepository:
    """Simple stub that mimics the AgentStateRepository interface."""

    def __init__(self, states=None):
        self._states = states or []
        self.saved_states = []

    def list_states(self, include_completed=False):
        return list(self._states)

    def save_state(self, state: AgentState):
        self.saved_states.append(state)
        return "stub-state-id"


def _reset_hitl_gauge():
    """Ensure gauges start from zero for deterministic tests."""
    for action_type in ["review_triage", "review_resolution", "approve_policy"]:
        hitl_actions_pending.labels(action_type=action_type).set(0)


@pytest.mark.asyncio
async def test_state_bus_recovers_persisted_state(monkeypatch):
    """StateBus should load persisted states (and pending actions) on init."""
    _reset_hitl_gauge()

    pending = PendingAction(
        action_name="review_triage_inc-1",
        action_type="review_triage",
        incident_id="inc-1",
        description="Review triage",
        payload={"triage_output": {}},
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    recovered_state = AgentState(
        incident_id="inc-1",
        alert_id="alert-1",
        agent_type="triage",
        current_step=AgentStep.PAUSED_FOR_REVIEW,
        pending_action=pending,
        started_at=datetime.utcnow(),
    )

    stub_repo = StubAgentStateRepository(states=[recovered_state])
    monkeypatch.setattr(
        "ai_service.state.bus.AgentStateRepository",
        lambda: stub_repo,
    )

    bus = StateBus(persist_to_db=True)

    state = bus.get_state("inc-1")
    assert state is not None
    assert state.pending_action is not None
    assert bus.get_pending_action("inc-1").action_name == "review_triage_inc-1"


@pytest.mark.asyncio
async def test_state_bus_handles_expired_pending_action(monkeypatch):
    """Expired pending actions are cleared and marked as errors."""
    _reset_hitl_gauge()
    stub_repo = StubAgentStateRepository()
    monkeypatch.setattr(
        "ai_service.state.bus.AgentStateRepository",
        lambda: stub_repo,
    )

    bus = StateBus(persist_to_db=True)

    expired_action = PendingAction(
        action_name="review_resolution_inc-2",
        action_type="review_resolution",
        incident_id="inc-2",
        description="Review resolution",
        payload={},
        created_at=datetime.utcnow() - timedelta(minutes=35),
        expires_at=datetime.utcnow() - timedelta(minutes=5),
    )
    state = AgentState(
        incident_id="inc-2",
        agent_type="resolution",
        current_step=AgentStep.PAUSED_FOR_REVIEW,
        pending_action=expired_action,
        started_at=datetime.utcnow(),
    )

    bus._states["inc-2"] = state
    bus._pending_actions["inc-2"] = expired_action
    hitl_actions_pending.labels(action_type="review_resolution").set(1)

    await bus._handle_action_timeout("inc-2", expired_action)

    assert bus.get_pending_action("inc-2") is None
    recovered_state = bus.get_state("inc-2")
    assert recovered_state.current_step == AgentStep.ERROR
    assert "timed out" in (recovered_state.error or "")
    assert len(stub_repo.saved_states) == 1


@pytest.mark.asyncio
async def test_state_bus_resume_clears_pending_action():
    """resume_from_action should drop pending action and move to RESUMED step."""
    _reset_hitl_gauge()
    bus = StateBus(persist_to_db=False)

    pending = PendingAction(
        action_name="review_resolution_inc-3",
        action_type="review_resolution",
        incident_id="inc-3",
        description="Review resolution",
        payload={},
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    state = AgentState(
        incident_id="inc-3",
        agent_type="resolution",
        current_step=AgentStep.PAUSED_FOR_REVIEW,
        pending_action=pending,
        started_at=datetime.utcnow(),
    )

    bus._states["inc-3"] = state
    bus._pending_actions["inc-3"] = pending
    hitl_actions_pending.labels(action_type="review_resolution").set(1)

    result_state = await bus.resume_from_action(
        incident_id="inc-3",
        action_name="review_resolution_inc-3",
        approved=True,
        user_edited={"resolution_steps": ["step"]},
    )

    assert result_state is not None
    assert result_state.pending_action is None
    assert result_state.current_step == AgentStep.RESUMED_FROM_REVIEW
    assert bus.get_pending_action("inc-3") is None

