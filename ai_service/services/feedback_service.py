"""Service for feedback business logic."""

from datetime import datetime
from typing import Dict, List, Optional
from ai_service.repositories.feedback_repository import FeedbackRepository
from ai_service.core import get_logger

logger = get_logger(__name__)


class FeedbackService:
    """Service for feedback business logic."""

    def __init__(self, repository: Optional[FeedbackRepository] = None):
        """
        Initialize feedback service.

        Args:
            repository: Optional feedback repository (for dependency injection/testing)
        """
        self.repository = repository or FeedbackRepository()

    def create_feedback(
        self,
        incident_id: str,
        feedback_type: str,
        system_output: dict,
        user_edited: dict,
        notes: Optional[str] = None,
        rating: Optional[str] = None,
    ) -> str:
        """
        Create a new feedback record, or update existing one if it's a rating for the same field/step.

        Args:
            incident_id: Incident ID
            feedback_type: 'triage' or 'resolution'
            system_output: Original system output
            user_edited: User-edited output
            notes: Optional notes from user
            rating: Optional rating ('thumbs_up' or 'thumbs_down')

        Returns:
            Feedback ID (new or updated)
        """

        # If this is a rating feedback (thumbs up/down), check if we should update existing feedback
        if rating and notes:
            existing_feedback = self.repository.find_existing_rating_feedback(
                incident_id=incident_id,
                feedback_type=feedback_type,
                notes=notes,
            )

            if existing_feedback:
                updated = self.repository.update_rating(
                    feedback_id=existing_feedback["id"],
                    rating=rating,
                    notes=notes,
                )
                if updated:
                    return existing_feedback["id"]
                else:
                    logger.warning(
                        "Failed to update existing feedback, will create new one"
                    )

        # Create new feedback record
        return self.repository.create(
            incident_id=incident_id,
            feedback_type=feedback_type,
            system_output=system_output,
            user_edited=user_edited,
            notes=notes,
            rating=rating,
        )

    def list_feedback_between(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        List feedback records between two dates.

        Args:
            start_date: Start date (defaults to 7 days ago)
            end_date: End date (defaults to now)

        Returns:
            List of feedback dictionaries
        """
        if start_date is None:
            from datetime import timedelta

            start_date = datetime.utcnow() - timedelta(days=7)

        if end_date is None:
            end_date = datetime.utcnow()

        return self.repository.list_between(start_ts=start_date, end_ts=end_date)

    def list_for_incident(self, incident_id: str) -> List[Dict]:
        """
        List all feedback records for a specific incident.

        This powers the UI feedback history view so analysts can see
        previous thumbs up/down ratings and notes.

        Args:
            incident_id: Incident ID

        Returns:
            List of feedback dictionaries (most recent first)
        """
        return self.repository.list_for_incident(incident_id)
