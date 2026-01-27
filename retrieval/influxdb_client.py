"""InfluxDB client for log retrieval (read-only queries).

This module provides read-only access to InfluxDB for retrieving logs
that can be used as context in triage and resolution.
"""

import os
import csv
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from ai_service.core import get_logger

logger = get_logger(__name__)


class InfluxDBClient:
    """Read-only InfluxDB client for log retrieval."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None,
    ):
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

    @staticmethod
    def _parse_influxdb_csv(csv_data: str) -> Tuple[List[str], List[List[str]]]:
        """
        Parse InfluxDB CSV format (with comment lines starting with #).
        
        InfluxDB CSV format:
        - First 3 lines start with # (group, datatype, default)
        - 4th line is the header (starts with comma: ,result,table,...)
        - Remaining lines are data rows
        
        Args:
            csv_data: Raw CSV string from InfluxDB
            
        Returns:
            Tuple of (headers, data_rows) where:
            - headers: List of column names
            - data_rows: List of lists containing parsed row values
        """
        csv_lines = csv_data.strip().split("\n")
        
        # Find header line (first non-comment line)
        header_line = None
        data_start = 0
        
        for i, line in enumerate(csv_lines):
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            # First non-comment line is the header
            header_line = line
            data_start = i + 1
            break
        
        if header_line is None:
            return [], []
        
        # Parse header
        header_reader = csv.reader([header_line])
        headers = next(header_reader)
        
        # Parse data rows
        data_rows = []
        for line in csv_lines[data_start:]:
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            
            try:
                row_reader = csv.reader([line])
                row_values = next(row_reader)
                
                # Pad with empty strings if needed
                if len(row_values) < len(headers):
                    row_values.extend([''] * (len(headers) - len(row_values)))
                
                data_rows.append(row_values[:len(headers)])
            except StopIteration:
                continue
        
        return headers, data_rows

    def fetch_logs_for_ticket(
        self,
        ticket_id: str,
        ticket_creation_date: datetime,
        window_minutes: Optional[int] = None,
    ) -> str:
        """
        Fetch raw logs from InfluxDB for a specific ticket within a time window.
        
        This method fetches logs from ticket_creation_date - window_minutes to ticket_creation_date.
        The logs are returned as CSV string (InfluxDB format) for parsing by log_parser.
        
        Args:
            ticket_id: Ticket/incident ID
            ticket_creation_date: Ticket creation datetime (UTC)
            window_minutes: Time window in minutes before ticket creation (defaults to env var or 15)
            
        Returns:
            CSV string containing raw logs from InfluxDB
            
        Raises:
            ValueError: If InfluxDB is not configured
            requests.RequestException: If InfluxDB query fails
        """
        if not self.is_configured():
            raise ValueError("InfluxDB not configured - cannot fetch logs")
        
        # Get window_minutes from env var or default to 15
        if window_minutes is None:
            window_minutes = int(os.getenv("INFLUX_LOG_WINDOW_MINUTES", "15"))
        
        # Calculate time window
        start_time = ticket_creation_date - timedelta(minutes=window_minutes)
        end_time = ticket_creation_date
        
        # Format times for Flux query (RFC3339 format)
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build Flux query (similar to shell script)
        flux_query = f'''from(bucket: "{self.bucket}")
  |> range(start: time(v: "{start_str}"), stop: time(v: "{end_str}"))'''
        
        logger.info(
            f"Fetching logs for ticket {ticket_id} from {start_str} to {end_str} "
            f"(window: {window_minutes} minutes)"
        )
        
        try:
            response = requests.post(
                f"{self.url}/api/v2/query?org={self.org}",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/vnd.flux",
                    "Accept": "application/csv",
                },
                data=flux_query,
                timeout=300,  # 5 minute timeout for large log files
            )
            response.raise_for_status()
            
            csv_data = response.text
            logger.info(f"Fetched {len(csv_data)} bytes of log data for ticket {ticket_id}")
            
            return csv_data
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch logs from InfluxDB for ticket {ticket_id}: {str(e)}")
            raise

    def fetch_and_parse_logs_for_ticket(
        self,
        ticket_id: str,
        ticket_creation_date: datetime,
        window_minutes: Optional[int] = None,
        include_warnings: bool = False,
    ) -> List[Dict]:
        """
        Fetch logs from InfluxDB and parse them to extract only error/important logs.
        
        Uses the same LogParser that's used for ingestion to ensure consistent filtering.
        
        This method:
        1. Fetches raw logs from InfluxDB for the ticket time window
        2. Parses the CSV response using InfluxDB CSV parser
        3. Filters to keep only error/important logs using log_parser (same as ingestion)
        4. Returns parsed and filtered log entries
        
        Args:
            ticket_id: Ticket/incident ID
            ticket_creation_date: Ticket creation datetime (UTC)
            window_minutes: Time window in minutes before ticket creation (defaults to env var or 15)
            include_warnings: Whether to include warning-level logs (default: False)
            
        Returns:
            List of parsed log dictionaries with error/important logs only
        """
        # Import log_parser - same one used for ingestion
        import sys
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        from log_parser import LogParser
        
        # Fetch raw CSV logs from InfluxDB
        csv_data = self.fetch_logs_for_ticket(ticket_id, ticket_creation_date, window_minutes)
        
        if not csv_data or not csv_data.strip():
            logger.warning(f"No logs fetched for ticket {ticket_id}")
            return []
        
        # Get actual window_minutes used (for logging)
        actual_window = window_minutes or int(os.getenv("INFLUX_LOG_WINDOW_MINUTES", "15"))
        
        # Initialize log parser (same as used in ingestion)
        parser = LogParser(case_sensitive=False)
        parser.include_all = False
        parser.include_warnings = include_warnings
        
        # Parse InfluxDB CSV format
        logs = []
        try:
            headers, data_rows = self._parse_influxdb_csv(csv_data)
            
            if not headers:
                logger.warning(f"No header found in CSV response for ticket {ticket_id}")
                return []
            
            logger.debug(f"Parsed {len(data_rows)} rows from InfluxDB CSV")
            
            # Process each data row
            for row_values in data_rows:
                # Create dictionary from headers and values
                row = dict(zip(headers, row_values))
                
                # Skip empty rows
                if not any(row.values()):
                    continue
                
                # Only process message field entries (matching bash script behavior)
                field = (row.get('_field') or '').strip()
                if field != 'message':
                    continue
                
                # Extract log data (same structure as log_parser.parse_csv_logs)
                log_entry = {
                    'ticket_id': ticket_id,
                    'timestamp': (row.get('_time') or '').strip(),
                    'value': (row.get('_value') or '').strip(),
                    'severity': (row.get('severity') or '').strip(),
                    'level': (row.get('level') or '').strip(),
                    'hostname': (row.get('hostname') or '').strip(),
                    'host': (row.get('host') or '').strip(),
                    'appname': (row.get('appname') or '').strip(),
                    'facility': (row.get('facility') or '').strip(),
                    'measurement': (row.get('_measurement') or '').strip(),
                    'start_time': (row.get('_start') or '').strip(),
                    'stop_time': (row.get('_stop') or '').strip(),
                }
                
                # Filter using log_parser.is_important_log (same logic as ingestion)
                log_message = log_entry['value']
                is_important, matched_pattern = parser.is_important_log(
                    log_message,
                    log_entry['severity'],
                    level=log_entry['level'],
                    include_warnings=include_warnings
                )
                
                if is_important:
                    log_entry['is_important'] = True
                    log_entry['matched_pattern'] = matched_pattern or 'error_pattern'
                    logs.append(log_entry)
        
        except Exception as e:
            logger.error(f"Failed to parse logs for ticket {ticket_id}: {str(e)}", exc_info=True)
            return []
        
        # Remove duplicates (same as ingestion)
        logs = parser._remove_duplicates(logs)
        
        logger.info(
            f"Parsed {len(logs)} important log entries from {ticket_id} "
            f"(window: {actual_window} minutes)"
        )
        
        return logs


# Global client instance
_influxdb_client: Optional[InfluxDBClient] = None


def get_influxdb_client() -> InfluxDBClient:
    """Get or create InfluxDB client instance."""
    global _influxdb_client
    if _influxdb_client is None:
        _influxdb_client = InfluxDBClient()
    return _influxdb_client
