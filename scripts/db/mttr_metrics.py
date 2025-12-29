"""MTTR metrics utilities."""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path (go up 3 levels: scripts/db -> scripts -> project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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
    """Print MTTR metrics."""
    metrics = get_mttr_metrics(hours)

    print(f"\nMTTR Metrics (Last {hours} hours)")
    print("=" * 60)
    print(f"Total Incidents:        {metrics['total_incidents']}")
    print(f"Triaged:                {metrics['triaged_count']}")
    print(f"Resolutions Proposed:   {metrics['resolved_count']}")
    print(f"Resolutions Accepted:   {metrics['accepted_count']}")
    print()
    print("Timing Metrics:")
    print(f"  Avg Triage Time:      {format_seconds(metrics['avg_triage_secs'])}")
    print(f"  Avg Resolution Time: {format_seconds(metrics['avg_resolution_secs'])}")
    print(f"  Avg MTTR:             {format_seconds(metrics['avg_mttr_secs'])}")
    print(f"  Median MTTR:          {format_seconds(metrics['median_mttr_secs'])}")
    print(f"  P95 MTTR:             {format_seconds(metrics['p95_mttr_secs'])}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="View MTTR metrics")
    parser.add_argument(
        "--hours", type=int, default=24, help="Number of hours to look back (default: 24)"
    )

    args = parser.parse_args()
    print_metrics(args.hours)
