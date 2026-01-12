"""MTTR metrics utilities."""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from ai_service.core import get_logger, setup_logging
except ImportError:
    import logging

    def setup_logging(log_level="INFO", service_name="mttr_metrics_script"):
        logging.basicConfig(level=getattr(logging, log_level))

    def get_logger(name):
        return logging.getLogger(name)


# Setup logging
setup_logging(log_level="INFO", service_name="mttr_metrics_script")
logger = get_logger(__name__)

from db.connection import get_db_connection


def get_mttr_metrics(hours: int = 24):
    """
    Get MTTR metrics for the last N hours.

    Args:
        hours: Number of hours to look back

    Returns:
        Dictionary with metrics
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Query the incident_metrics view
        cur.execute(
            """
            SELECT 
                COUNT(*) as total_incidents,
                COUNT(CASE WHEN triage_completed_at IS NOT NULL THEN 1 END) as triaged_count,
                COUNT(CASE WHEN resolution_proposed_at IS NOT NULL THEN 1 END) as resolved_count,
                COUNT(CASE WHEN resolution_accepted_at IS NOT NULL THEN 1 END) as accepted_count,
                AVG(triage_secs) as avg_triage_secs,
                AVG(resolution_proposed_secs) as avg_resolution_secs,
                AVG(mttr_secs) as avg_mttr_secs,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mttr_secs) as median_mttr_secs,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY mttr_secs) as p95_mttr_secs
            FROM incident_metrics
            WHERE alert_received_at >= NOW() - INTERVAL '%s hours'
            """,
            (hours,),
        )

        row = cur.fetchone()

        if not row:
            return {
                "total_incidents": 0,
                "triaged_count": 0,
                "resolved_count": 0,
                "accepted_count": 0,
                "avg_triage_secs": 0,
                "avg_resolution_secs": 0,
                "avg_mttr_secs": 0,
                "median_mttr_secs": 0,
                "p95_mttr_secs": 0,
            }

        return {
            "total_incidents": row["total_incidents"] or 0,
            "triaged_count": row["triaged_count"] or 0,
            "resolved_count": row["resolved_count"] or 0,
            "accepted_count": row["accepted_count"] or 0,
            "avg_triage_secs": float(row["avg_triage_secs"] or 0),
            "avg_resolution_secs": float(row["avg_resolution_secs"] or 0),
            "avg_mttr_secs": float(row["avg_mttr_secs"] or 0),
            "median_mttr_secs": float(row["median_mttr_secs"] or 0),
            "p95_mttr_secs": float(row["p95_mttr_secs"] or 0),
        }

    finally:
        cur.close()
        conn.close()


def format_seconds(seconds: float) -> str:
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def print_metrics(hours: int = 24):
    """Log MTTR metrics."""
    metrics = get_mttr_metrics(hours)

    logger.info(f"\nMTTR Metrics (Last {hours} hours)")
    logger.info("=" * 60)
    logger.info(f"Total Incidents:        {metrics['total_incidents']}")
    logger.info(f"Triaged:                {metrics['triaged_count']}")
    logger.info(f"Resolutions Proposed:   {metrics['resolved_count']}")
    logger.info(f"Resolutions Accepted:   {metrics['accepted_count']}")
    logger.info("")
    logger.info("Timing Metrics:")
    logger.info(f"  Avg Triage Time:      {format_seconds(metrics['avg_triage_secs'])}")
    logger.info(f"  Avg Resolution Time: {format_seconds(metrics['avg_resolution_secs'])}")
    logger.info(f"  Avg MTTR:             {format_seconds(metrics['avg_mttr_secs'])}")
    logger.info(f"  Median MTTR:          {format_seconds(metrics['median_mttr_secs'])}")
    logger.info(f"  P95 MTTR:             {format_seconds(metrics['p95_mttr_secs'])}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="View MTTR metrics")
    parser.add_argument(
        "--hours", type=int, default=24, help="Number of hours to look back (default: 24)"
    )

    args = parser.parse_args()
    print_metrics(args.hours)
