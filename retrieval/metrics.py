"""Retrieval quality metrics tracking.

TASK #7: Metrics/Monitoring for Retrieval Quality
Tracks retrieval success rate, empty results, average scores, and service/component match rates.
"""

import time
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime

# Try to import logger
try:
    from ai_service.core import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# In-memory metrics store (can be replaced with database or external metrics system)
_metrics_store = {
    "retrieval_count": 0,
    "empty_results_count": 0,
    "total_results": 0,
    "avg_rrf_score": 0.0,
    "avg_vector_score": 0.0,
    "avg_fulltext_score": 0.0,
    "service_match_count": 0,
    "component_match_count": 0,
    "service_mismatch_count": 0,
    "component_mismatch_count": 0,
    "retrieval_times": [],
    "by_retrieval_type": defaultdict(
        lambda: {"count": 0, "empty_count": 0, "avg_scores": {}}
    ),
    "last_updated": None,
}

# Thread-safe lock (simple implementation - for production, use proper locking)
_metrics_lock = None
try:
    import threading

    _metrics_lock = threading.Lock()
except ImportError:
    pass


def record_retrieval(
    results: List[Dict],
    retrieval_type: str = "hybrid_search",
    service: Optional[str] = None,
    component: Optional[str] = None,
    query_service: Optional[str] = None,
    query_component: Optional[str] = None,
    retrieval_time_ms: Optional[float] = None,
) -> None:
    """
    Record retrieval metrics.

    Args:
        results: List of retrieved chunks with scores
        retrieval_type: Type of retrieval ("hybrid_search", "triage_retrieval", "mmr_search", etc.)
        service: Service value from query (if available)
        component: Component value from query (if available)
        query_service: Service value from query context
        query_component: Component value from query context
        retrieval_time_ms: Retrieval time in milliseconds (optional)
    """
    if _metrics_lock:
        _metrics_lock.acquire()

    try:
        _metrics_store["retrieval_count"] += 1
        _metrics_store["last_updated"] = datetime.utcnow().isoformat()

        # Track by retrieval type
        type_metrics = _metrics_store["by_retrieval_type"][retrieval_type]
        type_metrics["count"] += 1

        # Check for empty results
        if not results or len(results) == 0:
            _metrics_store["empty_results_count"] += 1
            type_metrics["empty_count"] += 1
            logger.debug(
                f"Retrieval metrics: Empty results for {retrieval_type}"
            )
            return

        # Calculate average scores
        total_rrf = 0.0
        total_vector = 0.0
        total_fulltext = 0.0
        valid_scores = 0

        service_matches = 0
        component_matches = 0
        service_mismatches = 0
        component_mismatches = 0

        for result in results:
            # Aggregate scores
            if "rrf_score" in result and result["rrf_score"] is not None:
                total_rrf += float(result["rrf_score"])
                valid_scores += 1
            if "vector_score" in result and result["vector_score"] is not None:
                total_vector += float(result["vector_score"])
            if (
                "fulltext_score" in result
                and result["fulltext_score"] is not None
            ):
                total_fulltext += float(result["fulltext_score"])

            # Check service/component matches
            result_service = (
                result.get("metadata", {}).get("service")
                if isinstance(result.get("metadata"), dict)
                else None
            )
            result_component = (
                result.get("metadata", {}).get("component")
                if isinstance(result.get("metadata"), dict)
                else None
            )

            query_svc = query_service or service
            query_comp = query_component or component

            if query_svc and result_service:
                if str(query_svc).lower() == str(result_service).lower():
                    service_matches += 1
                else:
                    service_mismatches += 1

            if query_comp and result_component:
                if str(query_comp).lower() == str(result_component).lower():
                    component_matches += 1
                else:
                    component_mismatches += 1

        # Update totals
        _metrics_store["total_results"] += len(results)

        # Update average scores (exponential moving average for efficiency)
        if valid_scores > 0:
            avg_rrf = total_rrf / len(results)
            alpha = 0.1  # Smoothing factor
            _metrics_store["avg_rrf_score"] = (1 - alpha) * _metrics_store[
                "avg_rrf_score"
            ] + alpha * avg_rrf

            if total_vector > 0:
                avg_vector = total_vector / len(results)
                _metrics_store["avg_vector_score"] = (
                    1 - alpha
                ) * _metrics_store["avg_vector_score"] + alpha * avg_vector

            if total_fulltext > 0:
                avg_fulltext = total_fulltext / len(results)
                _metrics_store["avg_fulltext_score"] = (
                    1 - alpha
                ) * _metrics_store["avg_fulltext_score"] + alpha * avg_fulltext

        # Update service/component match counts
        if service_matches > 0:
            _metrics_store["service_match_count"] += service_matches
        if component_matches > 0:
            _metrics_store["component_match_count"] += component_matches
        if service_mismatches > 0:
            _metrics_store["service_mismatch_count"] += service_mismatches
        if component_mismatches > 0:
            _metrics_store["component_mismatch_count"] += component_mismatches

        # Track retrieval time
        if retrieval_time_ms is not None:
            _metrics_store["retrieval_times"].append(retrieval_time_ms)
            # Keep only last 1000 retrieval times
            if len(_metrics_store["retrieval_times"]) > 1000:
                _metrics_store["retrieval_times"] = _metrics_store[
                    "retrieval_times"
                ][-1000:]

        # Log periodic summary (every 100 retrievals)
        if _metrics_store["retrieval_count"] % 100 == 0:
            logger.info(
                f"Retrieval metrics summary: "
                f"total={_metrics_store['retrieval_count']}, "
                f"empty={_metrics_store['empty_results_count']} "
                f"({_metrics_store['empty_results_count'] / _metrics_store['retrieval_count'] * 100:.1f}%), "
                f"avg_rrf={_metrics_store['avg_rrf_score']:.3f}, "
                f"service_match_rate={_metrics_store['service_match_count'] / max(1, _metrics_store['service_match_count'] + _metrics_store['service_mismatch_count']) * 100:.1f}%"
            )

    finally:
        if _metrics_lock:
            _metrics_lock.release()


def get_metrics() -> Dict:
    """
    Get current retrieval metrics.

    Returns:
        Dictionary with current metrics
    """
    if _metrics_lock:
        _metrics_lock.acquire()

    try:
        # Calculate additional derived metrics
        metrics = _metrics_store.copy()

        # Calculate success rate
        if metrics["retrieval_count"] > 0:
            metrics["success_rate"] = (
                (metrics["retrieval_count"] - metrics["empty_results_count"])
                / metrics["retrieval_count"]
                * 100
            )
        else:
            metrics["success_rate"] = 0.0

        # Calculate average results per retrieval
        if metrics["retrieval_count"] > 0:
            metrics["avg_results_per_retrieval"] = (
                metrics["total_results"] / metrics["retrieval_count"]
            )
        else:
            metrics["avg_results_per_retrieval"] = 0.0

        # Calculate service/component match rates
        total_service_checks = (
            metrics["service_match_count"] + metrics["service_mismatch_count"]
        )
        if total_service_checks > 0:
            metrics["service_match_rate"] = (
                metrics["service_match_count"] / total_service_checks * 100
            )
        else:
            metrics["service_match_rate"] = 0.0

        total_component_checks = (
            metrics["component_match_count"]
            + metrics["component_mismatch_count"]
        )
        if total_component_checks > 0:
            metrics["component_match_rate"] = (
                metrics["component_match_count"] / total_component_checks * 100
            )
        else:
            metrics["component_match_rate"] = 0.0

        # Calculate average retrieval time
        if metrics["retrieval_times"]:
            metrics["avg_retrieval_time_ms"] = sum(
                metrics["retrieval_times"]
            ) / len(metrics["retrieval_times"])
            metrics["p95_retrieval_time_ms"] = sorted(
                metrics["retrieval_times"]
            )[int(len(metrics["retrieval_times"]) * 0.95)]
        else:
            metrics["avg_retrieval_time_ms"] = 0.0
            metrics["p95_retrieval_time_ms"] = 0.0

        # Convert defaultdict to regular dict for JSON serialization
        metrics["by_retrieval_type"] = dict(metrics["by_retrieval_type"])

        return metrics

    finally:
        if _metrics_lock:
            _metrics_lock.release()


def reset_metrics() -> None:
    """Reset all metrics (useful for testing)."""
    if _metrics_lock:
        _metrics_lock.acquire()

    try:
        _metrics_store.clear()
        _metrics_store.update(
            {
                "retrieval_count": 0,
                "empty_results_count": 0,
                "total_results": 0,
                "avg_rrf_score": 0.0,
                "avg_vector_score": 0.0,
                "avg_fulltext_score": 0.0,
                "service_match_count": 0,
                "component_match_count": 0,
                "service_mismatch_count": 0,
                "component_mismatch_count": 0,
                "retrieval_times": [],
                "by_retrieval_type": defaultdict(
                    lambda: {"count": 0, "empty_count": 0, "avg_scores": {}}
                ),
                "last_updated": None,
            }
        )
    finally:
        if _metrics_lock:
            _metrics_lock.release()
