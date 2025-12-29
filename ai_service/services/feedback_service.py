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
    ) -> str:
        """
        Create a new feedback record.

        Args:
            incident_id: Incident ID
            feedback_type: 'triage' or 'resolution'
            system_output: Original system output
            user_edited: User-edited output
            notes: Optional notes from user

        Returns:
            Feedback ID
        """
        logger.debug(
            f"Creating feedback via service for incident: {incident_id}, type={feedback_type}"
        )
        return self.repository.create(
            incident_id=incident_id,
            feedback_type=feedback_type,
            system_output=system_output,
            user_edited=user_edited,
            notes=notes,
        )

    def list_feedback_between(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        List feedback records between two dates.

        Args:
            start_date: Start date (defaults to 7 days ago)
            end_date: End date (defaults to now)

        Returns:
            List of feedback dictionaries
        """
        logger.debug(f"Listing feedback via service between {start_date} and {end_date}")
        if start_date is None:
            from datetime import timedelta

            start_date = datetime.utcnow() - timedelta(days=7)

        if end_date is None:
            end_date = datetime.utcnow()

        return self.repository.list_between(start_ts=start_date, end_ts=end_date)
