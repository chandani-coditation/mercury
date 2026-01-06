"""Metrics endpoint for retrieval quality monitoring.

TASK #7: Metrics/Monitoring for Retrieval Quality
Provides API endpoint to view retrieval quality metrics.
"""

from fastapi import APIRouter, HTTPException
from ai_service.core import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/metrics")
def get_retrieval_metrics():
    """
    Get retrieval quality metrics.
    
    Returns:
        Dictionary with retrieval metrics including:
        - retrieval_count: Total number of retrievals
        - empty_results_count: Number of retrievals with no results
        - success_rate: Percentage of successful retrievals
        - avg_rrf_score: Average RRF score
        - avg_vector_score: Average vector similarity score
        - avg_fulltext_score: Average full-text search score
        - service_match_rate: Percentage of service matches
        - component_match_rate: Percentage of component matches
        - avg_retrieval_time_ms: Average retrieval time in milliseconds
        - by_retrieval_type: Metrics broken down by retrieval type
    """
    try:
        from retrieval.metrics import get_metrics
        
        metrics = get_metrics()
        return {
            "status": "success",
            "metrics": metrics,
        }
    except ImportError:
        logger.warning("Retrieval metrics module not available")
        raise HTTPException(
            status_code=503,
            detail="Metrics collection is not available. Ensure retrieval.metrics module is accessible."
        )
    except Exception as e:
        logger.error(f"Error retrieving metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics: {str(e)}"
        )


@router.post("/metrics/reset")
def reset_retrieval_metrics():
    """
    Reset all retrieval metrics (useful for testing).
    
    Returns:
        Confirmation message
    """
    try:
        from retrieval.metrics import reset_metrics
        
        reset_metrics()
        return {
            "status": "success",
            "message": "Metrics reset successfully"
        }
    except ImportError:
        logger.warning("Retrieval metrics module not available")
        raise HTTPException(
            status_code=503,
            detail="Metrics collection is not available. Ensure retrieval.metrics module is accessible."
        )
    except Exception as e:
        logger.error(f"Error resetting metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset metrics: {str(e)}"
        )

