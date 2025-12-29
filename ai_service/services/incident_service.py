"""Service for incident business logic."""

from typing import Dict, List, Optional
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
        logger.debug(f"Creating incident via service for alert: {alert.get('alert_id', 'unknown')}")
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
        logger.debug(f"Getting incident via service: {incident_id}")
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
        logger.debug(f"Getting incident by alert_id via service: {alert_id}")
        return self.repository.get_by_alert_id(alert_id)

    def list_incidents(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        List incidents.

        Args:
            limit: Maximum number of incidents to return
            offset: Number of incidents to skip

        Returns:
            List of incident dictionaries
        """
        logger.debug(f"Listing incidents via service: limit={limit}, offset={offset}")
        return self.repository.list_all(limit=limit, offset=offset)

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
        logger.debug(f"Updating resolution via service for incident: {incident_id}")
        self.repository.update_resolution(
            incident_id=incident_id,
            resolution_output=resolution_output,
            resolution_evidence=resolution_evidence,
            policy_band=policy_band,
            policy_decision=policy_decision,
        )

    def update_policy(
        self, incident_id: str, policy_band: str, policy_decision: Optional[dict] = None
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
        logger.debug(
            f"Updating policy via service for incident: {incident_id}, policy_band={policy_band}"
        )
        self.repository.update_policy(
            incident_id=incident_id, policy_band=policy_band, policy_decision=policy_decision
        )

    def update_triage_output(self, incident_id: str, triage_output: dict) -> None:
        """
        Update incident with user-edited triage output.

        Args:
            incident_id: Incident ID
            triage_output: Updated triage output dictionary

        Raises:
            IncidentNotFoundError: If incident not found
        """
        logger.debug(f"Updating triage_output via service for incident: {incident_id}")
        self.repository.update_triage_output(incident_id=incident_id, triage_output=triage_output)
