"""Repository for agent state persistence."""

from typing import Optional, Dict, Any, List
from datetime import datetime
from db.connection import get_db_connection_context
from ai_service.core import get_logger, DatabaseError
from ai_service.state import AgentState, PendingAction
import json

logger = get_logger(__name__)


class AgentStateRepository:
    """Repository for agent state operations."""

    def save_state(self, state: AgentState) -> str:
        """
        Save agent state to database.

        Args:
            state: AgentState to save

        Returns:
            State ID
        """
        # Use context manager to ensure connection is returned to pool
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                # Convert state to JSON
                state_data = state.model_dump(mode="json")
                pending_action_data = None
                if state.pending_action:
                    pending_action_data = state.pending_action.model_dump(mode="json")

                # Insert or update state
                if state.incident_id:
                    # Check if state exists
                    cur.execute(
                        "SELECT id FROM agent_state WHERE incident_id = %s AND agent_type = %s",
                        (state.incident_id, state.agent_type),
                    )
                    existing = cur.fetchone()

                    if existing:
                        # Update existing state
                        state_id = existing["id"] if isinstance(existing, dict) else existing[0]
                        cur.execute(
                            """
                            UPDATE agent_state
                            SET current_step = %s,
                                state_data = %s,
                                pending_action = %s,
                                updated_at = now()
                            WHERE id = %s
                            """,
                            (
                                (
                                    state.current_step.value
                                    if hasattr(state.current_step, "value")
                                    else str(state.current_step)
                                ),
                                json.dumps(state_data),
                                json.dumps(pending_action_data) if pending_action_data else None,
                                state_id,
                            ),
                        )
                    else:
                        # Insert new state
                        cur.execute(
                            """
                            INSERT INTO agent_state (incident_id, agent_type, current_step, state_data, pending_action)
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING id
                            """,
                            (
                                state.incident_id,
                                state.agent_type,
                                (
                                    state.current_step.value
                                    if hasattr(state.current_step, "value")
                                    else str(state.current_step)
                                ),
                                json.dumps(state_data),
                                json.dumps(pending_action_data) if pending_action_data else None,
                            ),
                        )
                        result = cur.fetchone()
                        state_id = result["id"] if isinstance(result, dict) else result[0]
                else:
                    # Insert new state without incident_id
                    cur.execute(
                        """
                        INSERT INTO agent_state (agent_type, current_step, state_data, pending_action)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            state.agent_type,
                            (
                                state.current_step.value
                                if hasattr(state.current_step, "value")
                                else str(state.current_step)
                            ),
                            json.dumps(state_data),
                            json.dumps(pending_action_data) if pending_action_data else None,
                        ),
                    )
                    result = cur.fetchone()
                    state_id = result["id"] if isinstance(result, dict) else result[0]

                conn.commit()
                logger.debug(
                    f"Agent state saved: state_id={state_id}, incident_id={state.incident_id}"
                )
                return str(state_id)

            except Exception as e:
                conn.rollback()
                logger.error(f"Error saving agent state: {e}", exc_info=True)
                raise DatabaseError(f"Failed to save agent state: {str(e)}")
            finally:
                cur.close()

    def get_state(self, incident_id: str, agent_type: str) -> Optional[AgentState]:
        """
        Get latest agent state for an incident.

        Args:
            incident_id: Incident ID
            agent_type: Agent type (triage or resolution)

        Returns:
            AgentState or None
        """
        # Use context manager to ensure connection is returned to pool
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                cur.execute(
                    """
                    SELECT state_data, pending_action, updated_at
                    FROM agent_state
                    WHERE incident_id = %s AND agent_type = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (incident_id, agent_type),
                )
                result = cur.fetchone()

                if not result:
                    return None

                state_data = result["state_data"] if isinstance(result, dict) else result[0]
                pending_action_data = (
                    result["pending_action"] if isinstance(result, dict) else result[1]
                )

                # Reconstruct AgentState
                state_dict = state_data if isinstance(state_data, dict) else json.loads(state_data)
                if pending_action_data:
                    if isinstance(pending_action_data, dict):
                        state_dict["pending_action"] = pending_action_data
                    else:
                        state_dict["pending_action"] = json.loads(pending_action_data)

                return AgentState(**state_dict)

            except Exception as e:
                logger.error(f"Error getting agent state: {e}", exc_info=True)
                raise DatabaseError(f"Failed to get agent state: {str(e)}")
            finally:
                cur.close()

    def get_pending_actions(self, agent_type: Optional[str] = None) -> list:
        """
        Get all pending actions.

        Args:
            agent_type: Optional filter by agent type

        Returns:
            List of (incident_id, pending_action) tuples
        """
        # Use context manager to ensure connection is returned to pool
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                if agent_type:
                    cur.execute(
                        """
                        SELECT incident_id, pending_action, updated_at
                        FROM agent_state
                        WHERE pending_action IS NOT NULL AND agent_type = %s
                        ORDER BY updated_at DESC
                        """,
                        (agent_type,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT incident_id, pending_action, updated_at
                        FROM agent_state
                        WHERE pending_action IS NOT NULL
                        ORDER BY updated_at DESC
                        """
                    )

                results = cur.fetchall()
                pending = []
                for row in results:
                    incident_id = row["incident_id"] if isinstance(row, dict) else row[0]
                    pending_action_data = row["pending_action"] if isinstance(row, dict) else row[1]
                    if pending_action_data:
                        action_dict = (
                            pending_action_data
                            if isinstance(pending_action_data, dict)
                            else json.loads(pending_action_data)
                        )
                        pending.append((incident_id, PendingAction(**action_dict)))

                return pending

            except Exception as e:
                logger.error(f"Error getting pending actions: {e}", exc_info=True)
                raise DatabaseError(f"Failed to get pending actions: {str(e)}")
            finally:
                cur.close()

    def list_states(self, include_completed: bool = False) -> List[AgentState]:
        """
        List persisted agent states.

        Args:
            include_completed: If False, only return non-completed states.

        Returns:
            List of AgentState instances.
        """
        # Use context manager to ensure connection is returned to pool
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                if include_completed:
                    cur.execute(
                        """
                        SELECT state_data
                        FROM agent_state
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT state_data
                        FROM agent_state
                        WHERE current_step IS NULL OR current_step != 'completed'
                        """
                    )

                results = cur.fetchall()
                states: List[AgentState] = []
                for row in results:
                    state_data = row["state_data"] if isinstance(row, dict) else row[0]
                    state_dict = (
                        state_data if isinstance(state_data, dict) else json.loads(state_data)
                    )
                    try:
                        states.append(AgentState(**state_dict))
                    except Exception as exc:
                        logger.warning("Failed to deserialize agent state: %s", exc)
                        continue

                return states

            except Exception as e:
                logger.error(f"Error listing agent states: {e}", exc_info=True)
                raise DatabaseError(f"Failed to list agent states: {str(e)}")
            finally:
                cur.close()
