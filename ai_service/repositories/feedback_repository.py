"""Repository for feedback data access."""

import uuid
import json
from datetime import datetime
from typing import Optional, Dict, List
from db.connection import get_db_connection
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
        conn = get_db_connection()
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
            conn.close()

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
        conn = get_db_connection()
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
                results.append(
                    {
                        "id": str(r[0]),
                        "incident_id": str(r[1]) if r[1] else None,
                        "feedback_type": r[2],
                        "system_output": r[3],
                        "user_edited": r[4],
                        "diff": r[5],
                        "notes": r[6],
                        "rating": r[7],
                        "created_at": r[8].isoformat() if r[8] else None,
                    }
                )
            logger.debug(f"Listed {len(results)} feedback records")
            return results
        except Exception as e:
            logger.error(f"Failed to list feedback: {str(e)}", exc_info=True)
            raise DatabaseError(f"Failed to list feedback: {str(e)}") from e
        finally:
            cur.close()
            conn.close()
