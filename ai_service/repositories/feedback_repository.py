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
        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                feedback_id = uuid.uuid4()

                # Compute diff (simple JSON diff)
                diff = {"original": system_output, "edited": user_edited}

                # Validate rating if provided
                if rating and rating not in ["thumbs_up", "thumbs_down"]:
                    raise ValueError(
                        f"Invalid rating: {rating}. Must be 'thumbs_up' or 'thumbs_down'"
                    )

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
                return results
            except Exception as e:
                logger.error(f"Failed to list feedback: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to list feedback: {str(e)}") from e
            finally:
                cur.close()

    @staticmethod
    def find_existing_rating_feedback(
        incident_id: str,
        feedback_type: str,
        notes: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Find existing feedback record for a rating (thumbs up/down) based on notes pattern.

        The notes field typically contains patterns like:
        - "Rating for severity: thumbs_up"
        - "Rating for resolution step <step_title>: thumbs_down"

        Args:
            incident_id: Incident ID
            feedback_type: 'triage' or 'resolution'
            notes: Notes string that contains the field/step identifier

        Returns:
            Existing feedback record if found, None otherwise
        """
        if not notes:
            return None


        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                # Validate UUID format
                validated_uuid = uuid.UUID(incident_id)
                uuid_str = str(validated_uuid)
            except (ValueError, TypeError):
                logger.warning(f"Invalid UUID format for incident_id: {incident_id}")
                return None

            try:
                # Find feedback with matching incident_id, feedback_type, and notes pattern
                # Extract the field/step identifier from notes (e.g., "severity", "step 1")
                # We look for feedback with notes that start with "Rating for" and contain the same identifier
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
                      AND feedback_type = %s
                      AND notes IS NOT NULL
                      AND notes LIKE %s
                      AND rating IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (uuid_str, feedback_type, f"Rating for%"),
                )
                row = cur.fetchone()

                if row:
                    # Extract field identifier from both notes to compare
                    existing_notes = row["notes"] or ""
                    # Simple pattern matching: if notes contain the same field/step identifier
                    # For triage: "Rating for severity", "Rating for impact", "Rating for urgency"
                    # For resolution: "Rating for resolution step 1", "Rating for resolution step 2", etc.
                    if notes and existing_notes:
                        # Extract the identifier part (everything after "Rating for " and before ":")
                        def extract_identifier(note_str: str) -> Optional[str]:
                            if "Rating for" in note_str:
                                parts = note_str.split("Rating for")
                                if len(parts) > 1:
                                    identifier_part = parts[1].split(":")[0].strip()
                                    return identifier_part
                            return None

                        existing_id = extract_identifier(existing_notes)
                        new_id = extract_identifier(notes)

                        # If identifiers match, this is the same field/step
                        if existing_id and new_id and existing_id == new_id:
                            return {
                                "id": str(row["id"]),
                                "incident_id": (
                                    str(row["incident_id"]) if row["incident_id"] else None
                                ),
                                "feedback_type": row["feedback_type"],
                                "notes": row["notes"],
                                "rating": row["rating"],
                                "created_at": (
                                    row["created_at"].isoformat() if row["created_at"] else None
                                ),
                            }

                return None
            except Exception as e:
                logger.error(
                    f"Failed to find existing feedback: {str(e)}",
                    exc_info=True,
                )
                return None
            finally:
                cur.close()

    @staticmethod
    def update_rating(
        feedback_id: str,
        rating: str,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Update an existing feedback record's rating and notes.

        Args:
            feedback_id: Feedback record ID
            rating: New rating ('thumbs_up' or 'thumbs_down')
            notes: Optional new notes

        Returns:
            True if update successful, False otherwise
        """

        with get_db_connection_context() as conn:
            cur = conn.cursor()

            try:
                validated_uuid = uuid.UUID(feedback_id)
                uuid_str = str(validated_uuid)
            except (ValueError, TypeError):
                logger.warning(f"Invalid UUID format for feedback_id: {feedback_id}")
                return False

            try:
                # Validate rating
                if rating not in ["thumbs_up", "thumbs_down"]:
                    raise ValueError(f"Invalid rating: {rating}")

                update_fields = ["rating = %s"]
                params = [rating]

                if notes:
                    update_fields.append("notes = %s")
                    params.append(notes)

                params.append(uuid_str)

                cur.execute(
                    f"""
                    UPDATE feedback
                    SET {', '.join(update_fields)}, created_at = now()
                    WHERE id = %s
                    """,
                    tuple(params),
                )

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update feedback rating: {str(e)}", exc_info=True)
                return False
            finally:
                cur.close()

    @staticmethod
    def list_for_incident(incident_id: str) -> List[Dict]:
        """
        List all feedback records for a given incident.

        For rating feedback (thumbs up/down), only returns the latest feedback
        per field/step combination to avoid duplicates.

        This is used by the UI to show feedback history (including ratings)
        when an analyst views a historical incident.

        Args:
            incident_id: Incident ID (UUID as string)

        Returns:
            List of feedback dictionaries (most recent first, deduplicated by field/step)

        Raises:
            DatabaseError: If database operation fails
        """

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

                # Helper function to extract field/step identifier from notes
                def extract_identifier(note_str: Optional[str]) -> Optional[str]:
                    if not note_str or "Rating for" not in note_str:
                        return None
                    parts = note_str.split("Rating for")
                    if len(parts) > 1:
                        identifier_part = parts[1].split(":")[0].strip()
                        return identifier_part
                    return None

                # Deduplicate: keep only latest feedback per field/step combination
                seen_identifiers: Dict[str, bool] = {}
                results: List[Dict] = []

                for r in rows:
                    # Rows are dictionaries due to dict_row factory
                    feedback_record = {
                        "id": str(r["id"]),
                        "incident_id": str(r["incident_id"]) if r["incident_id"] else None,
                        "feedback_type": r["feedback_type"],
                        "notes": r["notes"],
                        "rating": r["rating"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    }

                    # For rating feedback, deduplicate by field/step identifier
                    if r["rating"] and r["notes"]:
                        identifier = extract_identifier(r["notes"])
                        if identifier:
                            # Create unique key: feedback_type + identifier
                            key = f"{r['feedback_type']}:{identifier}"
                            if key in seen_identifiers:
                                # Skip this duplicate - we already have the latest one
                                continue
                            seen_identifiers[key] = True

                    results.append(feedback_record)

                    len(results),
                    incident_id,
                    len(rows),
                
                return results
            except Exception as e:
                # Extract detailed error information from psycopg exceptions
                error_details = []
                error_details.append(f"Exception type: {type(e).__name__}")
                error_details.append(f"Exception message: {str(e) if str(e) else repr(e)}")

                # Check for psycopg-specific error attributes
                if hasattr(e, "pgcode"):
                    error_details.append(f"PostgreSQL error code: {e.pgcode}")
                if hasattr(e, "pgerror"):
                    error_details.append(f"PostgreSQL error message: {e.pgerror}")
                if hasattr(e, "diag"):
                    error_details.append(f"PostgreSQL diagnostic: {e.diag}")

                # Get full exception details
                import traceback

                error_traceback = traceback.format_exc()

                error_msg = (
                    " | ".join(error_details) if error_details else (str(e) if str(e) else repr(e))
                )

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
