"""InfluxDB client for log retrieval (read-only queries).

This module provides read-only access to InfluxDB for retrieving logs
that can be used as context in triage and resolution.
"""
import os
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from ai_service.core import get_logger

logger = get_logger(__name__)


class InfluxDBClient:
    """Read-only InfluxDB client for log retrieval."""
    
    def __init__(self, url: Optional[str] = None, token: Optional[str] = None, org: Optional[str] = None, bucket: Optional[str] = None):
        """
        Initialize InfluxDB client.
        
        Args:
            url: InfluxDB URL (defaults to INFLUXDB_URL env var)
            token: InfluxDB API token (defaults to INFLUXDB_TOKEN env var)
            org: InfluxDB organization (defaults to INFLUXDB_ORG env var)
            bucket: InfluxDB bucket name (defaults to INFLUXDB_BUCKET env var)
        """
        self.url = url or os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = token or os.getenv("INFLUXDB_TOKEN")
        self.org = org or os.getenv("INFLUXDB_ORG", "my-org")
        self.bucket = bucket or os.getenv("INFLUXDB_BUCKET", "logs")
        
        if not self.token:
            logger.warning("INFLUXDB_TOKEN not set - InfluxDB log retrieval will be disabled")
    
    def is_configured(self) -> bool:
        """Check if InfluxDB is properly configured."""
        return bool(self.token and self.url)
    
    def query_logs(
        self,
        service: Optional[str] = None,
        component: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Query logs from InfluxDB (read-only).
        
        Args:
            service: Filter by service name
            component: Filter by component name
            start_time: Start time for query (defaults to 1 hour ago)
            end_time: End time for query (defaults to now)
            limit: Maximum number of log entries to return
        
        Returns:
            List of log dictionaries with content, timestamp, level, etc.
        """
        if not self.is_configured():
            logger.warning("InfluxDB not configured - returning empty log list")
            return []
        
        # Default time range: last hour
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(hours=1)
        
        # Build Flux query
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
          |> filter(fn: (r) => r["_measurement"] == "logs")
        '''
        
        if service:
            query += f'|> filter(fn: (r) => r["service"] == "{service}")'
        if component:
            query += f'|> filter(fn: (r) => r["component"] == "{component}")'
        
        query += f'|> limit(n: {limit})'
        
        try:
            response = requests.post(
                f"{self.url}/api/v2/query",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/vnd.flux",
                },
                params={"org": self.org},
                data=query,
                timeout=10
            )
            response.raise_for_status()
            
            # Parse Flux CSV response (InfluxDB returns CSV format)
            # Format: #datatype,string,long,dateTime:RFC3339,string,string,string
            #         ,result,table,_time,_measurement,_field,_value
            #         ,0,0,2024-01-01T00:00:00Z,logs,message,Error occurred
            logs = []
            try:
                csv_lines = response.text.strip().split('\n')
                if len(csv_lines) > 2:  # Has header + data
                    # Skip header lines (start with #)
                    data_start = 0
                    for i, line in enumerate(csv_lines):
                        if not line.startswith('#') and line.strip():
                            data_start = i
                            break
                    
                    # Parse data rows
                    for line in csv_lines[data_start:]:
                        if not line.strip() or line.startswith(','):
                            continue
                        parts = line.split(',')
                        if len(parts) >= 6:
                            # Extract: _time, _measurement, _field, _value
                            log_entry = {
                                "timestamp": parts[2] if len(parts) > 2 else None,
                                "measurement": parts[3] if len(parts) > 3 else None,
                                "field": parts[4] if len(parts) > 4 else None,
                                "content": parts[5] if len(parts) > 5 else line,
                                "service": service,
                                "component": component
                            }
                            logs.append(log_entry)
            except Exception as parse_error:
                logger.warning(f"Failed to parse InfluxDB CSV response: {str(parse_error)}")
                # Fallback: return raw response as single log entry
                if response.text:
                    logs.append({
                        "content": response.text[:1000],  # Limit size
                        "service": service,
                        "component": component,
                        "timestamp": None
                    })
            
            logger.debug(f"Retrieved {len(logs)} logs from InfluxDB")
            return logs
            
        except Exception as e:
            logger.error(f"Failed to query InfluxDB: {str(e)}")
            return []
    
    def get_logs_for_context(
        self,
        query_text: str,
        service: Optional[str] = None,
        component: Optional[str] = None,
        limit: int = 10
    ) -> List[str]:
        """
        Get logs relevant to a query for use as context.
        
        Args:
            query_text: Search query text
            service: Filter by service
            component: Filter by component
            limit: Maximum logs to return
        
        Returns:
            List of log content strings
        """
        logs = self.query_logs(service=service, component=component, limit=limit)
        return [log.get("content", "") for log in logs if log.get("content")]


# Global client instance
_influxdb_client: Optional[InfluxDBClient] = None


def get_influxdb_client() -> InfluxDBClient:
    """Get or create InfluxDB client instance."""
    global _influxdb_client
    if _influxdb_client is None:
        _influxdb_client = InfluxDBClient()
    return _influxdb_client

