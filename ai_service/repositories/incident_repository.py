"""Repository for incident data access."""
import uuid
import json
from datetime import datetime
from typing import Optional, Dict, List
from db.connection import get_db_connection, get_db_connection_context
from ai_service.core import IncidentNotFoundError, DatabaseError, get_logger

logger = get_logger(__name__)


class IncidentRepository:
    """Repository for incident database operations."""
    
    @staticmethod
    def create(
        alert: dict,
        triage_output: dict,
        triage_evidence: Optional[dict] = None,
        resolution_output: Optional[dict] = None,
        resolution_evidence: Optional[dict] = None,
        policy_band: Optional[str] = None,
        policy_decision: Optional[dict] = None
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
            Incident ID (UUID as string)
        
        Raises:
            DatabaseError: If database operation fails
        """
        logger.debug(f"Creating incident for alert: {alert.get('alert_id', 'unknown')}")
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            
            try:
                incident_id = uuid.uuid4()
                now = datetime.utcnow()
                
                cur.execute(
                    """
                    INSERT INTO incidents (
                        id, alert_id, source, raw_alert, 
                        triage_output, triage_evidence,
                        resolution_output, resolution_evidence,
                        policy_band, policy_decision,
                        alert_received_at, triage_completed_at, resolution_proposed_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s, %s)
                    """,
                    (
                        incident_id,
                        alert.get("alert_id"),
                        alert.get("source"),
                        json.dumps(alert),
                        json.dumps(triage_output) if triage_output else None,
                        json.dumps(triage_evidence) if triage_evidence else None,
                        json.dumps(resolution_output) if resolution_output else None,
                        json.dumps(resolution_evidence) if resolution_evidence else None,
                        policy_band,
                        json.dumps(policy_decision) if policy_decision else None,
                        now,
                        now if triage_output else None,
                        now if resolution_output else None
                    )
                )
                
                conn.commit()
                logger.info(f"Incident created successfully: {incident_id}")
                return str(incident_id)
            
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to create incident: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to create incident: {str(e)}") from e
            finally:
                cur.close()
    
    @staticmethod
    def get_by_id(incident_id: str) -> Dict:
        """
        Get incident by ID.
        
        Args:
            incident_id: Incident ID
        
        Returns:
            Incident dictionary
        
        Raises:
            IncidentNotFoundError: If incident not found
            DatabaseError: If database operation fails
        """
        logger.debug(f"Getting incident: {incident_id}")
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            
            try:
                cur.execute(
                    "SELECT * FROM incidents WHERE id = %s",
                    (incident_id,)
                )
                row = cur.fetchone()
                
                if not row:
                    logger.warning(f"Incident not found: {incident_id}")
                    raise IncidentNotFoundError(f"Incident {incident_id} not found")
                
                logger.debug(f"Incident retrieved: {incident_id}")
                return dict(row)
            except IncidentNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Failed to get incident {incident_id}: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to get incident: {str(e)}") from e
            finally:
                cur.close()
    
    @staticmethod
    def list_all(limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        List incidents.
        
        Args:
            limit: Maximum number of incidents to return
            offset: Number of incidents to skip
        
        Returns:
            List of incident dictionaries
        
        Raises:
            DatabaseError: If database operation fails
        """
        logger.debug(f"Listing incidents: limit={limit}, offset={offset}")
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            
            try:
                cur.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (limit, offset)
                )
                rows = cur.fetchall()
                result = [dict(row) for row in rows]
                logger.debug(f"Listed {len(result)} incidents")
                return result
            except Exception as e:
                logger.error(f"Failed to list incidents: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to list incidents: {str(e)}") from e
            finally:
                cur.close()
    
    @staticmethod
    def update_resolution(
        incident_id: str,
        resolution_output: dict,
        resolution_evidence: Optional[dict] = None,
        policy_band: Optional[str] = None,
        policy_decision: Optional[dict] = None
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
            DatabaseError: If database operation fails
        """
        logger.debug(f"Updating resolution for incident: {incident_id}")
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            
            try:
                # Check if incident exists
                cur.execute("SELECT id FROM incidents WHERE id = %s", (incident_id,))
                if not cur.fetchone():
                    logger.warning(f"Incident not found for resolution update: {incident_id}")
                    raise IncidentNotFoundError(f"Incident {incident_id} not found")
                
                cur.execute(
                    """
                    UPDATE incidents
                    SET resolution_output = %s::jsonb,
                        resolution_evidence = %s::jsonb,
                        policy_band = %s,
                        policy_decision = %s::jsonb,
                        resolution_proposed_at = %s
                    WHERE id = %s
                    """,
                    (
                        json.dumps(resolution_output),
                        json.dumps(resolution_evidence) if resolution_evidence else None,
                        policy_band,
                        json.dumps(policy_decision) if policy_decision else None,
                        datetime.utcnow(),
                        incident_id
                    )
                )
                conn.commit()
                logger.info(f"Resolution updated for incident: {incident_id}")
            except IncidentNotFoundError:
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update resolution for incident {incident_id}: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to update incident resolution: {str(e)}") from e
            finally:
                cur.close()
    
    @staticmethod
    def update_policy(
        incident_id: str,
        policy_band: str,
        policy_decision: Optional[dict] = None
    ) -> None:
        """
        Update incident with policy band and decision.
        
        Args:
            incident_id: Incident ID
            policy_band: Policy band (AUTO, PROPOSE, REVIEW)
            policy_decision: Full policy decision JSON
        
        Raises:
            IncidentNotFoundError: If incident not found
            DatabaseError: If database operation fails
        """
        logger.debug(f"Updating policy for incident: {incident_id}, policy_band={policy_band}")
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            
            try:
                # Check if incident exists
                cur.execute("SELECT id FROM incidents WHERE id = %s", (incident_id,))
                if not cur.fetchone():
                    logger.warning(f"Incident not found for policy update: {incident_id}")
                    raise IncidentNotFoundError(f"Incident {incident_id} not found")
                
                # Get current policy values for logging
                cur.execute("SELECT policy_band, policy_decision FROM incidents WHERE id = %s", (incident_id,))
                current = cur.fetchone()
                old_policy_band = current.get("policy_band") if current else None
                old_policy_decision = current.get("policy_decision") if current else None
                
                cur.execute(
                    """
                    UPDATE incidents
                    SET policy_band = %s,
                        policy_decision = %s::jsonb
                    WHERE id = %s
                    """,
                    (
                        policy_band,
                        json.dumps(policy_decision) if policy_decision else None,
                        incident_id,
                    ),
                )
                conn.commit()
                
                # Log before/after for verification
                logger.info(
                    f"Policy updated for incident: {incident_id}, "
                    f"policy_band: {old_policy_band} -> {policy_band}, "
                    f"policy_decision updated: {old_policy_decision is not None} -> {policy_decision is not None}"
                )
                
                # Verify the update
                cur.execute("SELECT policy_band, policy_decision FROM incidents WHERE id = %s", (incident_id,))
                verify = cur.fetchone()
                if verify:
                    verified_policy_band = verify.get("policy_band")
                    verified_policy_decision = verify.get("policy_decision")
                    if verified_policy_band != policy_band:
                        logger.error(
                            f"Policy update verification failed: expected policy_band={policy_band}, "
                            f"got {verified_policy_band}"
                        )
                    else:
                        logger.debug(f"Policy update verified: policy_band={verified_policy_band}")
            except IncidentNotFoundError:
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update policy for incident {incident_id}: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to update incident policy: {str(e)}") from e
            finally:
                cur.close()
    
    @staticmethod
    def update_triage_output(
        incident_id: str,
        triage_output: dict
    ) -> None:
        """
        Update incident with user-edited triage output.
        
        Args:
            incident_id: Incident ID
            triage_output: Updated triage output dictionary
        
        Raises:
            IncidentNotFoundError: If incident not found
            DatabaseError: If database operation fails
        """
        logger.debug(f"Updating triage_output for incident: {incident_id}")
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            
            try:
                # Check if incident exists
                cur.execute("SELECT id FROM incidents WHERE id = %s", (incident_id,))
                if not cur.fetchone():
                    logger.warning(f"Incident not found for triage update: {incident_id}")
                    raise IncidentNotFoundError(f"Incident {incident_id} not found")
                
                cur.execute(
                    """
                    UPDATE incidents
                    SET triage_output = %s::jsonb
                    WHERE id = %s
                    """,
                    (
                        json.dumps(triage_output),
                        incident_id,
                    ),
                )
                conn.commit()
                logger.info(f"Triage output updated for incident: {incident_id}")
            except IncidentNotFoundError:
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update triage_output for incident {incident_id}: {str(e)}", exc_info=True)
                raise DatabaseError(f"Failed to update incident triage_output: {str(e)}") from e
            finally:
                cur.close()

