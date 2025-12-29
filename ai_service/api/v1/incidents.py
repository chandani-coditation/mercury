"""Incident endpoints."""

from fastapi import APIRouter, HTTPException
from ai_service.services import IncidentService
from ai_service.core import get_logger, IncidentNotFoundError, DatabaseError

logger = get_logger(__name__)
router = APIRouter()


@router.get("/incidents")
def get_incidents(limit: int = 50, offset: int = 0):
    """List incidents."""
    try:
        service = IncidentService()
        incidents = service.list_incidents(limit=limit, offset=offset)
        return {"incidents": incidents, "count": len(incidents)}
    except DatabaseError as e:
        logger.error(f"Database error listing incidents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error listing incidents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/incidents/{incident_id}")
def get_incident_endpoint(incident_id: str):
    """Get incident details by incident ID or alert ID."""
    try:
        service = IncidentService()

        # Try to get by incident_id first (UUID format)
        try:
            incident = service.get_incident(incident_id)
            logger.info(f"Found incident by ID: {incident_id}")
            return incident
        except (IncidentNotFoundError, DatabaseError) as e:
            # If not found or invalid UUID format, try by alert_id
            error_msg = str(e)
            if "invalid input syntax for type uuid" in error_msg.lower() or isinstance(
                e, IncidentNotFoundError
            ):
                logger.debug(
                    f"Not found by incident_id (or invalid UUID), trying alert_id: {incident_id}"
                )
                try:
                    incident = service.get_incident_by_alert_id(incident_id)
                    logger.info(f"Found incident by alert_id: {incident_id}")
                    return incident
                except IncidentNotFoundError:
                    # Not found by either ID
                    logger.warning(f"Incident not found by ID or alert_id: {incident_id}")
                    raise HTTPException(
                        status_code=404,
                        detail=f"Incident not found with ID or Alert ID: {incident_id}",
                    )
            else:
                # Different database error, re-raise
                raise

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except DatabaseError as e:
        logger.error(f"Database error getting incident: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting incident: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
