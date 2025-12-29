"""State bus for emitting agent state and managing HITL actions."""

import asyncio
from typing import Dict, Optional, Callable, Any, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from .models import AgentState, PendingAction, AgentStep
from ai_service.core import get_logger
from ai_service.repositories.agent_state_repository import AgentStateRepository

logger = get_logger(__name__)


class StateBus:
    """
    State bus for emitting agent state snapshots and managing HITL actions.

    This class manages:
    - State emission to connected clients (via WebSocket/SSE)
    - Pending action tracking
    - Action response callbacks
    """

    def __init__(self, persist_to_db: bool = True):
        """
        Initialize state bus.

        Args:
            persist_to_db: Whether to persist state to database
        """
        # Map of incident_id -> AgentState
        self._states: Dict[str, AgentState] = {}

        # Map of incident_id -> list of callback functions for state updates
        self._state_subscribers: Dict[str, list] = defaultdict(list)

        # Map of action_name -> callback function for action responses
        self._action_callbacks: Dict[str, Callable] = {}

        # Map of incident_id -> pending action
        self._pending_actions: Dict[str, PendingAction] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Track processed action names (idempotency)
        self._processed_actions: Dict[str, datetime] = {}

        # Background task for monitoring pending actions
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_interval: int = 30

        # State repository for persistence
        self._persist_to_db = persist_to_db
        self._state_repo = AgentStateRepository() if persist_to_db else None

        if self._persist_to_db and self._state_repo:
            self._load_existing_states()

    def _load_existing_states(self) -> None:
        """Load previously persisted agent states (for recovery after restart)."""
        try:
            states = self._state_repo.list_states(include_completed=False)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Failed to load persisted agent states: %s", exc)
            return

        pending_counts: Counter = Counter()
        for state in states:
            if not state.incident_id:
                continue
            self._states[state.incident_id] = state
            if state.pending_action:
                self._pending_actions[state.incident_id] = state.pending_action
                pending_counts[state.pending_action.action_type] += 1
                self._processed_actions.pop(state.pending_action.action_name, None)

        # Log recovered pending actions
        if pending_counts:
            logger.info(
                "Recovered %d agent states (%d pending actions) from persistence",
                len(states),
                sum(pending_counts.values()),
            )

    async def emit_state(self, state: AgentState) -> None:
        """
        Emit state snapshot to all subscribers.

        Args:
            state: AgentState to emit
        """
        async with self._lock:
            # Store state
            if state.incident_id:
                self._states[state.incident_id] = state

            # Update timestamp
            state.updated_at = datetime.utcnow()

            # Persist to database if enabled
            if self._persist_to_db and self._state_repo:
                try:
                    self._state_repo.save_state(state)
                except Exception as e:
                    logger.warning("Failed to persist state to database: %s", e, exc_info=True)

            # Notify subscribers
            subscribers = self._state_subscribers.get(state.incident_id or "global", [])
            for callback in subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(state)
                    else:
                        callback(state)
                except Exception as e:
                    logger.error("Error in state subscriber callback: %s", e, exc_info=True)

            logger.debug(
                "State emitted: incident_id=%s, step=%s, agent_type=%s",
                state.incident_id,
                state.current_step,
                state.agent_type,
            )

    async def start(self, monitor_interval: int = 30) -> None:
        """
        Start background monitoring for pending-action timeouts.

        Args:
            monitor_interval: Interval in seconds between timeout checks.
        """
        self._monitor_interval = monitor_interval
        if self._monitor_task and not self._monitor_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - only if called outside loop
            logger.warning("Cannot start state bus monitor outside an event loop")
            return

        self._monitor_task = loop.create_task(self._pending_action_monitor())
        logger.info("State bus pending-action monitor started (interval=%ss)", monitor_interval)

    async def stop(self) -> None:
        """Stop background monitoring tasks."""
        if not self._monitor_task:
            return
        self._monitor_task.cancel()
        try:
            await self._monitor_task
        except asyncio.CancelledError:
            pass
        finally:
            self._monitor_task = None
            logger.info("State bus pending-action monitor stopped")

    async def _pending_action_monitor(self) -> None:
        """Background coroutine to clean up expired pending actions."""
        try:
            while True:
                await asyncio.sleep(self._monitor_interval)
                await self._check_pending_action_timeouts()
        except asyncio.CancelledError:
            logger.debug("Pending-action monitor cancelled")
            raise

    async def _check_pending_action_timeouts(self) -> None:
        """Check for and handle expired pending actions."""
        async with self._lock:
            pending_snapshot: List[Tuple[str, PendingAction]] = list(self._pending_actions.items())

        now = datetime.utcnow()
        for incident_id, pending_action in pending_snapshot:
            if pending_action.expires_at and pending_action.expires_at <= now:
                await self._handle_action_timeout(incident_id, pending_action)

    async def _handle_action_timeout(self, incident_id: str, pending_action: PendingAction) -> None:
        """Handle timeout for a pending HITL action."""
        async with self._lock:
            state = self._states.get(incident_id)
            if not state:
                self._pending_actions.pop(incident_id, None)
                return
            self._pending_actions.pop(incident_id, None)

            action_type = pending_action.action_type

            state.warning = f"HITL action '{action_type}' timed out; escalating to approver."
            state.updated_at = datetime.utcnow()

            escalated = None
            if action_type != "approve_policy":
                escalated = PendingAction(
                    action_name=f"approve_policy_{incident_id}",
                    action_type="approve_policy",
                    incident_id=incident_id,
                    description=f"Escalated approval after {action_type} timeout",
                    payload={
                        "previous_action": action_type,
                        "previous_payload": pending_action.payload,
                    },
                    created_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(minutes=60),
                )
                state.pending_action = escalated
                self._pending_actions[incident_id] = escalated
                state.current_step = AgentStep.PAUSED_FOR_REVIEW
                state.requires_approval = True
            else:
                state.pending_action = None
                state.current_step = AgentStep.ERROR
                state.error = "Escalated approval timed out; manual intervention required."

            self._states[incident_id] = state

        if self._persist_to_db and self._state_repo:
            try:
                self._state_repo.save_state(state)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to persist timeout for %s: %s", incident_id, exc)

        await self.emit_state(state)

        action_type = pending_action.action_type
        if pending_action.created_at:
            duration = (datetime.utcnow() - pending_action.created_at).total_seconds()

    async def pause_for_action(
        self,
        state: AgentState,
        action_name: str,
        action_type: str,
        description: str,
        payload: Dict[str, Any],
        timeout_minutes: Optional[int] = None,
    ) -> AgentState:
        """
        Pause agent execution and emit HITL action.

        Args:
            state: Current agent state
            action_name: Unique action identifier (e.g., "review_triage_{incident_id}")
            action_type: Action type (review_triage, review_resolution, approve_policy)
            description: Human-readable description
            payload: Action-specific data
            timeout_minutes: Optional timeout in minutes

        Returns:
            Updated state with pending_action set
        """
        async with self._lock:
            expires_at = None
            if timeout_minutes:
                expires_at = datetime.utcnow() + timedelta(minutes=timeout_minutes)

            pending_action = PendingAction(
                action_name=action_name,
                action_type=action_type,
                incident_id=state.incident_id or "",
                description=description,
                payload=payload,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
            )

            state.pending_action = pending_action
            state.current_step = AgentStep.PAUSED_FOR_REVIEW
            state.requires_approval = True
            state.updated_at = datetime.utcnow()

            if state.incident_id:
                self._pending_actions[state.incident_id] = pending_action
                self._states[state.incident_id] = state

            state_to_emit = state

        await self.emit_state(state_to_emit)

        logger.info(
            "Agent paused for action: incident_id=%s, action=%s, type=%s",
            state.incident_id,
            action_name,
            action_type,
        )

        return state

    async def resume_from_action(
        self,
        incident_id: str,
        action_name: str,
        approved: bool,
        user_edited: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        policy_band: Optional[str] = None,
    ) -> Optional[AgentState]:
        """
        Resume agent execution after HITL action response.

        Args:
            incident_id: Incident ID
            action_name: Action name to resume
            approved: Whether action was approved
            user_edited: Optional user-edited data
            notes: Optional notes
            policy_band: Optional policy band override

        Returns:
            Updated state or None if not found
        """
        async with self._lock:
            state = self._states.get(incident_id)
            if not state:
                logger.warning("State not found for incident_id=%s", incident_id)
                return None

            if not state.pending_action:
                if action_name in self._processed_actions:
                    logger.info(
                        "Action %s already processed for incident_id=%s; returning latest state",
                        action_name,
                        incident_id,
                    )
                    return state
                logger.warning(
                    "No pending action to resume for incident_id=%s (action=%s)",
                    incident_id,
                    action_name,
                )
                return None

            if state.pending_action.action_name != action_name:
                logger.warning(
                    "Pending action mismatch: expected %s, got %s",
                    action_name,
                    state.pending_action.action_name,
                )
                return None

            pending_action = state.pending_action

            state.current_step = AgentStep.RESUMED_FROM_REVIEW
            state.pending_action = None
            state.updated_at = datetime.utcnow()

            if user_edited:
                if state.agent_type == "triage":
                    state.triage_output = user_edited
                elif state.agent_type == "resolution":
                    state.resolution_output = user_edited

            if policy_band:
                state.policy_band = policy_band
                if policy_band == "AUTO":
                    state.can_auto_apply = True
                    state.requires_approval = False
                else:
                    state.can_auto_apply = False
                    state.requires_approval = True

            self._pending_actions.pop(incident_id, None)
            self._states[incident_id] = state
            self._processed_actions[action_name] = datetime.utcnow()

        await self.emit_state(state)

        action_type = pending_action.action_type if pending_action else "unknown"
        if pending_action and pending_action.created_at:
            duration = (datetime.utcnow() - pending_action.created_at).total_seconds()

        logger.info(
            "Agent resumed from action: incident_id=%s, action=%s, approved=%s",
            incident_id,
            action_name,
            approved,
        )

        return state

    def subscribe_state(self, incident_id: Optional[str], callback: Callable) -> None:
        """
        Subscribe to state updates for an incident.

        Args:
            incident_id: Incident ID (None for global subscription)
            callback: Callback function(state: AgentState)
        """
        key = incident_id or "global"
        self._state_subscribers[key].append(callback)
        logger.debug("State subscriber added: incident_id=%s", incident_id)

    def unsubscribe_state(self, incident_id: Optional[str], callback: Callable) -> None:
        """
        Unsubscribe from state updates.

        Args:
            incident_id: Incident ID (None for global)
            callback: Callback function to remove
        """
        key = incident_id or "global"
        if callback in self._state_subscribers[key]:
            self._state_subscribers[key].remove(callback)
            logger.debug("State subscriber removed: incident_id=%s", incident_id)

    def get_state(self, incident_id: str) -> Optional[AgentState]:
        """
        Get current state for an incident.

        Args:
            incident_id: Incident ID

        Returns:
            AgentState or None
        """
        return self._states.get(incident_id)

    def get_pending_action(self, incident_id: str) -> Optional[PendingAction]:
        """
        Get pending action for an incident.

        Args:
            incident_id: Incident ID

        Returns:
            PendingAction or None
        """
        return self._pending_actions.get(incident_id)

    def clear_state(self, incident_id: str) -> None:
        """
        Clear state for an incident.

        Args:
            incident_id: Incident ID
        """

        async def _clear():
            async with self._lock:
                if incident_id in self._states:
                    del self._states[incident_id]
                if incident_id in self._pending_actions:
                    del self._pending_actions[incident_id]
                if incident_id in self._state_subscribers:
                    del self._state_subscribers[incident_id]

        asyncio.create_task(_clear())


# Global state bus instance
_state_bus: Optional[StateBus] = None


def get_state_bus() -> StateBus:
    """Get global state bus instance."""
    global _state_bus
    if _state_bus is None:
        _state_bus = StateBus()
    return _state_bus
