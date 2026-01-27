"""Service for incident business logic."""

from typing import Dict, List, Optional, Tuple
from ai_service.repositories.incident_repository import IncidentRepository
from ai_service.core import IncidentNotFoundError, get_logger

logger = get_logger(__name__)


class IncidentService:
    """Service for incident business logic."""

    def __init__(self, repository: Optional[IncidentRepository] = None):
        """
        Initialize incident service.

        Args:
            repository: Optional incident repository (for dependency injection/testing)
        """
        self.repository = repository or IncidentRepository()

    def create_incident(
        self,
        alert: dict,
        triage_output: dict,
        triage_evidence: Optional[dict] = None,
        resolution_output: Optional[dict] = None,
        resolution_evidence: Optional[dict] = None,
        policy_band: Optional[str] = None,
        policy_decision: Optional[dict] = None,
    ) -> str:
        """
        Create a new incident.

        Args:
            alert: Alert dictionary
            triage_output: Triage output dictionary
            triage_evidence: Evidence chunks used by triager agent
            resolution_output: Optional resolution output dictionary
            resolution_evidence: Evidence chunks used by resolution copilot agent
            policy_band: Policy band (AUTO, PROPOSE, REVIEW)
            policy_decision: Full policy decision JSON

        Returns:
            Incident ID
        """
        return self.repository.create(
            alert=alert,
            triage_output=triage_output,
            triage_evidence=triage_evidence,
            resolution_output=resolution_output,
            resolution_evidence=resolution_evidence,
            policy_band=policy_band,
            policy_decision=policy_decision,
        )

    def get_incident(self, incident_id: str) -> Dict:
        """
        Get incident by ID.

        Args:
            incident_id: Incident ID

        Returns:
            Incident dictionary

        Raises:
            IncidentNotFoundError: If incident not found
        """
        return self.repository.get_by_id(incident_id)

    def get_incident_by_alert_id(self, alert_id: str) -> Dict:
        """
        Get incident by alert ID.

        Args:
            alert_id: Alert ID from the original alert

        Returns:
            Incident dictionary

        Raises:
            IncidentNotFoundError: If incident not found
        """
        return self.repository.get_by_alert_id(alert_id)

    def list_incidents(
        self, limit: int = 50, offset: int = 0, search: Optional[str] = None
    ) -> Tuple[List[Dict], int]:
        """
        List incidents with optional search and pagination.

        Args:
            limit: Maximum number of incidents to return
            offset: Number of incidents to skip
            search: Optional search term to filter by incident_id or alert_id

        Returns:
            Tuple of (list of incident dictionaries, total count)
        """
        return self.repository.list_all(
            limit=limit, offset=offset, search=search
        )

    def update_resolution(
        self,
        incident_id: str,
        resolution_output: dict,
        resolution_evidence: Optional[dict] = None,
        policy_band: Optional[str] = None,
        policy_decision: Optional[dict] = None,
    ) -> None:
        """
        Update incident with resolution output.

        Args:
            incident_id: Incident ID
            resolution_output: Resolution output dictionary
            resolution_evidence: Evidence chunks used by resolution copilot agent
            policy_band: Policy band
            policy_decision: Full policy decision JSON

        Raises:
            IncidentNotFoundError: If incident not found
        """

        # If policy_band or policy_decision not provided, preserve existing values
        if policy_band is None or policy_decision is None:
            try:
                current = self.repository.get_by_id(incident_id)
                if policy_band is None:
                    policy_band = current.get("policy_band")
                if policy_decision is None:
                    policy_decision = current.get("policy_decision")
            except IncidentNotFoundError:
                logger.warning(
                    f"Incident {incident_id} not found when trying to preserve policy during resolution update"
                )

        self.repository.update_resolution(
            incident_id=incident_id,
            resolution_output=resolution_output,
            resolution_evidence=resolution_evidence,
            policy_band=policy_band,
            policy_decision=policy_decision,
        )

    def update_policy(
        self,
        incident_id: str,
        policy_band: str,
        policy_decision: Optional[dict] = None,
    ) -> None:
        """
        Update incident with policy band and decision.

        Args:
            incident_id: Incident ID
            policy_band: Policy band (AUTO, PROPOSE, REVIEW)
            policy_decision: Full policy decision JSON

        Raises:
            IncidentNotFoundError: If incident not found
        """
        self.repository.update_policy(
            incident_id=incident_id,
            policy_band=policy_band,
            policy_decision=policy_decision,
        )

    def update_triage_output(
        self, incident_id: str, triage_output: dict
    ) -> None:
        """
        Update incident with user-edited triage output.

        Args:
            incident_id: Incident ID
            triage_output: Updated triage output dictionary

        Raises:
            IncidentNotFoundError: If incident not found
        """
        self.repository.update_triage_output(
            incident_id=incident_id, triage_output=triage_output
        )
