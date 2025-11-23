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
    """Get incident details."""
    try:
        service = IncidentService()
        incident = service.get_incident(incident_id)
        return incident
    except IncidentNotFoundError as e:
        logger.warning(f"Incident not found: {incident_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        logger.error(f"Database error getting incident: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting incident: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")



