"""Repository for feedback data access."""

import uuid
import json
from datetime import datetime
from typing import Optional, Dict, List
from db.connection import get_db_connection_context
from ai_service.core import DatabaseError, get_logger

logger = get_logger(__name__)


class FeedbackRepository:
    """Repository for feedback database operations."""

    @staticmethod
    def create(
        incident_id: str,
        feedback_type: str,
        system_output: dict,
        user_edited: dict,
        notes: Optional[str] = None,
        rating: Optional[str] = None,
    ) -> str:
        """
        Create a new feedback record.

        Args:
            incident_id: Incident ID
            feedback_type: 'triage' or 'resolution'
            system_output: Original system output
            user_edited: User-edited output
            notes: Optional notes from user
            rating: Optional rating ('thumbs_up' or 'thumbs_down')

        Returns:
            Feedback ID

        Raises:
            DatabaseError: If database operation fails
        """
        logger.debug(f"Creating feedback for incident: {incident_id}, type={feedback_type}")
        # Use context manager to ensure connection is returned to pool
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                feedback_id = uuid.uuid4()

                # Compute diff (simple JSON diff)
                diff = {"original": system_output, "edited": user_edited}

                # Validate rating if provided
                if rating and rating not in ["thumbs_up", "thumbs_down"]:
                    raise ValueError(f"Invalid rating: {rating}. Must be 'thumbs_up' or 'thumbs_down'")
                
                cur.execute(
                    """
                    INSERT INTO feedback (id, incident_id, feedback_type, system_output, user_edited, diff, notes, rating)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                    """,
                    (
                        feedback_id,
                        incident_id,
                        feedback_type,
                        json.dumps(system_output),
                        json.dumps(user_edited),
                        json.dumps(diff),
                        notes,
                        rating,
                    ),
                )

                # If feedback is for resolution, mark resolution as accepted
                if feedback_type == "resolution":
                    cur.execute(
                        """
                        UPDATE incidents
                        SET resolution_accepted_at = %s
                        WHERE id = %s
                        """,
                        (datetime.utcnow(), incident_id),
                    )

                conn.commit()
                logger.info(f"Feedback created: {feedback_id} for incident {incident_id}")
                return str(feedback_id)

            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to create feedback: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to create feedback: {str(e)}") from e
            finally:
                cur.close()

    @staticmethod
    def list_between(start_ts: datetime, end_ts: datetime) -> List[Dict]:
        """
        List feedback records between two timestamps.

        Args:
            start_ts: Start timestamp
            end_ts: End timestamp

        Returns:
            List of feedback dictionaries

        Raises:
            DatabaseError: If database operation fails
        """
        logger.debug(f"Listing feedback between {start_ts} and {end_ts}")
        # Use context manager to ensure connection is returned to pool
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                cur.execute(
                    """
                    SELECT id, incident_id, feedback_type, system_output, user_edited, diff, notes, rating, created_at
                    FROM feedback
                    WHERE created_at >= %s AND created_at <= %s
                    ORDER BY created_at ASC
                    """,
                    (start_ts, end_ts),
                )
                rows = cur.fetchall()
                results = []
                for r in rows:
                    # Rows are dictionaries due to dict_row factory
                    results.append(
                        {
                            "id": str(r["id"]),
                            "incident_id": str(r["incident_id"]) if r["incident_id"] else None,
                            "feedback_type": r["feedback_type"],
                            "system_output": r["system_output"],
                            "user_edited": r["user_edited"],
                            "diff": r["diff"],
                            "notes": r["notes"],
                            "rating": r["rating"],
                            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        }
                    )
                logger.debug(f"Listed {len(results)} feedback records")
                return results
            except Exception as e:
                logger.error(f"Failed to list feedback: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to list feedback: {str(e)}") from e
            finally:
                cur.close()

    @staticmethod
    def list_for_incident(incident_id: str) -> List[Dict]:
        """
        List all feedback records for a given incident.

        This is used by the UI to show feedback history (including ratings)
        when an analyst views a historical incident.

        Args:
            incident_id: Incident ID (UUID as string)

        Returns:
            List of feedback dictionaries (most recent first)

        Raises:
            DatabaseError: If database operation fails
        """
        logger.debug(f"Listing feedback for incident_id={incident_id}")
        
        # Validate and convert UUID format in Python for better error messages
        try:
            # Validate UUID format
            validated_uuid = uuid.UUID(incident_id)
            uuid_str = str(validated_uuid)
        except (ValueError, TypeError) as e:
            error_msg = f"Invalid UUID format: {incident_id}"
            logger.error(f"{error_msg}: {str(e)}")
            raise DatabaseError(error_msg) from e
        
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                cur.execute(
                    """
                    SELECT id,
                           incident_id,
                           feedback_type,
                           notes,
                           rating,
                           created_at
                    FROM feedback
                    WHERE incident_id = %s
                    ORDER BY created_at DESC
                    """,
                    (uuid_str,),
                )
                rows = cur.fetchall()
                results: List[Dict] = []
                for r in rows:
                    # Rows are dictionaries due to dict_row factory
                    results.append(
                        {
                            "id": str(r["id"]),
                            "incident_id": str(r["incident_id"]) if r["incident_id"] else None,
                            "feedback_type": r["feedback_type"],
                            "notes": r["notes"],
                            "rating": r["rating"],
                            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                        }
                    )
                logger.debug(
                    "Listed %d feedback records for incident_id=%s",
                    len(results),
                    incident_id,
                )
                return results
            except Exception as e:
                # Extract detailed error information from psycopg exceptions
                error_details = []
                error_details.append(f"Exception type: {type(e).__name__}")
                error_details.append(f"Exception message: {str(e) if str(e) else repr(e)}")
                
                # Check for psycopg-specific error attributes
                if hasattr(e, 'pgcode'):
                    error_details.append(f"PostgreSQL error code: {e.pgcode}")
                if hasattr(e, 'pgerror'):
                    error_details.append(f"PostgreSQL error message: {e.pgerror}")
                if hasattr(e, 'diag'):
                    error_details.append(f"PostgreSQL diagnostic: {e.diag}")
                
                # Get full exception details
                import traceback
                error_traceback = traceback.format_exc()
                
                error_msg = " | ".join(error_details) if error_details else (str(e) if str(e) else repr(e))
                
                logger.error(
                    "Failed to list feedback for incident_id=%s: %s\nTraceback:\n%s",
                    incident_id,
                    error_msg,
                    error_traceback,
                )
                raise DatabaseError(
                    f"Failed to list feedback for incident {incident_id}: {error_msg}"
                ) from e
            finally:
                cur.close()

