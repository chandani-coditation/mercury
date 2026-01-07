"""API v1 package exports."""

from . import feedback  # noqa: F401
from . import incidents  # noqa: F401
from . import triage  # noqa: F401
from . import resolution  # noqa: F401

"""API v1 routes."""

from fastapi import APIRouter
from ai_service.api.v1 import (
    triage,
    resolution,
    incidents,
    feedback,
    calibration,
    health,
    simulate,
    agents,
    metrics,
)

router = APIRouter(prefix="/api/v1", tags=["v1"])

# Include all route modules
router.include_router(health.router)
router.include_router(triage.router)
router.include_router(resolution.router)
router.include_router(incidents.router)
router.include_router(feedback.router)
router.include_router(calibration.router)
router.include_router(simulate.router)
router.include_router(agents.router)
router.include_router(metrics.router)

__all__ = ["router"]
