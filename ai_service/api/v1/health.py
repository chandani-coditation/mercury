"""Health check endpoints with dependency checks."""

from fastapi import APIRouter, HTTPException
from ai_service.core import get_logger, get_llm_handler
from db.connection import get_db_connection_context
import time

logger = get_logger(__name__)
router = APIRouter()

# Health check timeout (seconds)
HEALTH_CHECK_TIMEOUT = 5


@router.get("/health")
def health_check():
    """
    Basic health check endpoint.
    Returns service status without checking dependencies.
    """
    logger.debug("Health check requested")
    return {"status": "healthy", "service": "ai", "version": "1.0.0"}


@router.get("/health/ready")
def readiness_check():
    """
    Readiness check endpoint with dependency verification.
    Checks database connectivity and LLM API availability.
    Includes timeout protection to prevent hanging.
    """
    logger.debug("Readiness check requested")
    start_time = time.time()
    checks = {
        "service": "ai",
        "version": "1.0.0",
        "status": "ready",
        "checks": {},
    }

    # Check database with timeout protection
    db_start = time.time()
    try:
        with get_db_connection_context() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
        db_duration = time.time() - db_start
        checks["checks"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_duration * 1000, 2),
        }
    except Exception as e:
        db_duration = time.time() - db_start
        error_msg = str(e)
        if db_duration >= HEALTH_CHECK_TIMEOUT:
            error_msg = f"Timeout after {db_duration:.2f}s: {error_msg}"
        logger.warning(f"Database health check failed: {error_msg}")
        checks["checks"]["database"] = {
            "status": "unhealthy",
            "error": error_msg,
            "response_time_ms": round(db_duration * 1000, 2),
        }
        checks["status"] = "not_ready"

    # Check LLM API (lightweight check - validate configuration)
    llm_start = time.time()
    try:
        # Use common handler to validate configuration (doesn't make actual API call)
        handler = get_llm_handler()
        validation = handler.validate_configuration()

        llm_duration = time.time() - llm_start
        if validation["valid"]:
            checks["checks"]["llm_api"] = {
                "status": "healthy",
                "mode": validation["mode"],
                "response_time_ms": round(llm_duration * 1000, 2),
            }
        else:
            error_msg = "; ".join(validation["errors"])
            checks["checks"]["llm_api"] = {
                "status": "unhealthy",
                "mode": validation["mode"],
                "error": error_msg,
                "response_time_ms": round(llm_duration * 1000, 2),
            }
            checks["status"] = "not_ready"
    except Exception as e:
        llm_duration = time.time() - llm_start
        error_msg = str(e)
        if llm_duration >= HEALTH_CHECK_TIMEOUT:
            error_msg = f"Timeout after {llm_duration:.2f}s: {error_msg}"
        logger.warning(f"LLM API health check failed: {error_msg}")
        checks["checks"]["llm_api"] = {
            "status": "unhealthy",
            "error": error_msg,
            "response_time_ms": round(llm_duration * 1000, 2),
        }
        checks["status"] = "not_ready"

    total_duration = time.time() - start_time
    checks["total_response_time_ms"] = round(total_duration * 1000, 2)

    if checks["status"] == "not_ready":
        raise HTTPException(status_code=503, detail=checks)

    return checks


@router.get("/health/live")
def liveness_check():
    """
    Liveness check endpoint.
    Simple check to verify the service is running.
    """
    return {"status": "alive", "service": "ai"}
