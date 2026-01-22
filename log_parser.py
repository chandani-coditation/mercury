#!/usr/bin/env python3
"""
Log Parser Script
Parses logs from CSV files or server logs to extract errors, exceptions, and important details.
Creates output files with naming: TicketID-YYYYMMDD_HHMM-host-severity.txt
"""

import csv
import re
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import subprocess


class LogParser:
    """Parse logs and extract errors, exceptions, and important details."""
    
    # Error/Exception patterns to search for
    ERROR_PATTERNS = [
        r'\berror\b',
        r'\bexception\b',
        r'\bfail(?:ed|ure)?\b',
        r'\bcritical\b',
        r'\balert\b',
        r'\bfatal\b',
        r'\btimeout\b',
        r'\bdenied\b',
        r'\brefused\b',
        r'\bunable\b',
        r'\bcannot\b',
        r'\bunavailable\b',
        r'\bdown\b',
        r'\boffline\b',
        r'\bcrash(?:ed)?\b',
        r'\bpanic\b',
        r'\bstack\s+trace\b',
        r'\btraceback\b',
        r'\bout\s+of\s+memory\b',
        r'\bdisk\s+full\b',
        r'\bconnection\s+reset\b',
        r'\bconnection\s+refused\b',
        r'\b503\b',  # Service unavailable
        r'\b500\b',  # Internal server error
        r'\b502\b',  # Bad gateway
        r'\b504\b',  # Gateway timeout
    ]
    
    # Severity levels to prioritize
    SEVERITY_LEVELS = {
        'critical': 1,
        'alert': 2,
        'error': 3,
        'err': 3,
        'warning': 4,
        'warn': 4,
        'notice': 5,
        'info': 6,
        'debug': 7,
    }
    
    def __init__(self, case_sensitive: bool = False):
        """Initialize the log parser.
        
        Args:
            case_sensitive: Whether pattern matching should be case sensitive
        """
        self.case_sensitive = case_sensitive
        self.flags = 0 if case_sensitive else re.IGNORECASE
        self.compiled_patterns = [
            re.compile(pattern, self.flags) for pattern in self.ERROR_PATTERNS
        ]
    
    def is_important_log(self, log_message: str, severity: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Check if a log entry is important (error/exception/warning).
        
        Args:
            log_message: The log message to check
            severity: Severity level of the log
            
        Returns:
            Tuple of (is_important, matched_pattern)
        """
        if not log_message:
            return False, None
        
        # Check severity level first
        if severity:
            severity_lower = severity.lower()
            if severity_lower in ['critical', 'alert', 'error', 'err']:
                return True, f"severity:{severity_lower}"
            if severity_lower in ['warning', 'warn']:
                return True, f"severity:{severity_lower}"
        
        # Check for error patterns in message
        for pattern in self.compiled_patterns:
            if pattern.search(log_message):
                return True, pattern.pattern
        
        return False, None
    
    def should_include_log(self, log_message: str, severity: Optional[str] = None) -> bool:
        """Determine if a log should be included in output.
        This is more lenient than is_important_log - includes warnings and notices
        that might contain useful information.
        
        Args:
            log_message: The log message to check
            severity: Severity level of the log
            
        Returns:
            True if log should be included
        """
        # Always include errors, exceptions, warnings
        is_important, _ = self.is_important_log(log_message, severity)
        if is_important:
            return True
        
        # Include notices and info if they contain important keywords
        if severity and severity.lower() in ['notice', 'info']:
            # Check for important keywords even in notices
            important_keywords = [
                'failed', 'failure', 'timeout', 'denied', 'refused',
                'unable', 'cannot', 'unavailable', 'down', 'offline',
                'restart', 'reload', 'config', 'change', 'update'
            ]
            log_lower = log_message.lower()
            for keyword in important_keywords:
                if keyword in log_lower:
                    return True
        
        return False
    
    def extract_ticket_id(self, file_path: str) -> Optional[str]:
        """Extract ticket ID from file path.
        
        Args:
            file_path: Path to the log file
            
        Returns:
            Ticket ID if found, None otherwise
        """
        # Try to extract from filename (e.g., influx-INC6052856)
        filename = os.path.basename(file_path)
        match = re.search(r'INC\d+', filename, re.IGNORECASE)
        if match:
            return match.group(0)
        
        # Try to extract from path
        match = re.search(r'INC\d+', file_path, re.IGNORECASE)
        if match:
            return match.group(0)
        
        return None
    
    def parse_csv_logs(self, csv_path: str) -> List[Dict]:
        """Parse logs from CSV file (InfluxDB format).
        
        Args:
            csv_path: Path to CSV file
            
        Returns:
            List of parsed log entries with metadata
        """
        logs = []
        ticket_id = self.extract_ticket_id(csv_path)
        
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Skip empty rows
                    if not any(row.values()):
                        continue
                    
                    # Only process message field entries
                    field = row.get('_field', '').strip()
                    if field != 'message':
                        continue
                    
                    # Extract log data
                    log_entry = {
                        'ticket_id': ticket_id,
                        'timestamp': row.get('_time', '').strip(),
                        'value': row.get('_value', '').strip(),
                        'severity': row.get('severity', '').strip(),
                        'hostname': row.get('hostname', '').strip(),
                        'host': row.get('host', '').strip(),
                        'appname': row.get('appname', '').strip(),
                        'facility': row.get('facility', '').strip(),
                        'measurement': row.get('_measurement', '').strip(),
                        'start_time': row.get('_start', '').strip(),
                        'stop_time': row.get('_stop', '').strip(),
                    }
                    
                    # Extract actual log message from _value
                    log_message = log_entry['value']
                    
                    # Always check for error patterns first (even with --include-all)
                    is_important, matched_pattern = self.is_important_log(
                        log_message, log_entry['severity']
                    )
                    
                    # Also check if we should include it (more lenient check)
                    should_include = self.should_include_log(
                        log_message, log_entry['severity']
                    )
                    
                    # Include all logs if --include-all flag is set
                    include_all = getattr(self, 'include_all', False)
                    
                    if is_important or should_include or include_all:
                        log_entry['is_important'] = True
                        
                        # Determine matched pattern - prioritize actual error patterns
                        if matched_pattern:
                            # Found an actual error pattern
                            log_entry['matched_pattern'] = matched_pattern
                        elif should_include and not is_important:
                            # Matched keywords but not error patterns
                            log_entry['matched_pattern'] = 'keyword_match'
                        elif include_all:
                            # Included because of --include-all, but check severity
                            severity = log_entry.get('severity', '').lower()
                            if severity in ['critical', 'alert', 'error', 'err', 'warning', 'warn']:
                                log_entry['matched_pattern'] = f'severity:{severity}'
                            else:
                                log_entry['matched_pattern'] = 'normal_log'
                        else:
                            log_entry['matched_pattern'] = 'keyword_match'
                        
                        logs.append(log_entry)
        
        except Exception as e:
            print(f"Error parsing CSV file {csv_path}: {str(e)}", file=sys.stderr)
            return []
        
        return logs
    
    def parse_server_logs(self, log_path: str, ticket_id: Optional[str] = None) -> List[Dict]:
        """Parse logs from server log file (plain text or syslog format).
        
        Args:
            log_path: Path to log file on server
            ticket_id: Optional ticket ID
            
        Returns:
            List of parsed log entries
        """
        logs = []
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Try to parse syslog format
                    # Format: <priority>timestamp hostname service: message
                    syslog_match = re.match(
                        r'<(\d+)>(\w+\s+\d+\s+\d+:\d+:\d+)\s+(\S+)\s+(\S+):\s*(.*)',
                        line
                    )
                    
                    if syslog_match:
                        priority = int(syslog_match.group(1))
                        timestamp = syslog_match.group(2)
                        hostname = syslog_match.group(3)
                        service = syslog_match.group(4)
                        message = syslog_match.group(5)
                        
                        # Extract severity from priority (RFC 3164)
                        severity_code = priority & 0x07
                        severity_map = {
                            0: 'emergency',
                            1: 'alert',
                            2: 'critical',
                            3: 'error',
                            4: 'warning',
                            5: 'notice',
                            6: 'info',
                            7: 'debug'
                        }
                        severity = severity_map.get(severity_code, 'unknown')
                    else:
                        # Plain text log - try to extract timestamp and message
                        timestamp_match = re.search(
                            r'(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})', line
                        )
                        timestamp = timestamp_match.group(1) if timestamp_match else ''
                        message = line
                        hostname = ''
                        service = ''
                        severity = None
                    
                    # Always check for error patterns first (even with --include-all)
                    is_important, matched_pattern = self.is_important_log(message, severity)
                    should_include = self.should_include_log(message, severity)
                    include_all = getattr(self, 'include_all', False)
                    
                    if is_important or should_include or include_all:
                        # Determine matched pattern - prioritize actual error patterns
                        if matched_pattern:
                            pattern_display = matched_pattern
                        elif should_include and not is_important:
                            pattern_display = 'keyword_match'
                        elif include_all:
                            severity_lower = (severity or 'unknown').lower()
                            if severity_lower in ['critical', 'alert', 'error', 'err', 'warning', 'warn']:
                                pattern_display = f'severity:{severity_lower}'
                            else:
                                pattern_display = 'normal_log'
                        else:
                            pattern_display = 'keyword_match'
                        
                        log_entry = {
                            'ticket_id': ticket_id,
                            'timestamp': timestamp,
                            'value': message,
                            'severity': severity or 'unknown',
                            'hostname': hostname,
                            'host': hostname,
                            'appname': service,
                            'facility': '',
                            'measurement': 'syslog',
                            'is_important': True,
                            'matched_pattern': pattern_display,
                            'line_number': line_num,
                        }
                        logs.append(log_entry)
        
        except Exception as e:
            print(f"Error parsing server log file {log_path}: {str(e)}", file=sys.stderr)
            return []
        
        return logs

    def parse_server_log_lines(
        self, lines: List[str], ticket_id: Optional[str] = None, source: Optional[str] = None
    ) -> List[Dict]:
        """Parse logs from already-collected server log lines (journald output, piped logs, etc.)."""
        logs: List[Dict] = []
        include_all = getattr(self, "include_all", False)

        for line_num, line in enumerate(lines, 1):
            line = (line or "").strip()
            if not line:
                continue

            # Try to parse syslog format
            # Format: <priority>timestamp hostname service: message
            syslog_match = re.match(
                r"<(\d+)>(\w+\s+\d+\s+\d+:\d+:\d+)\s+(\S+)\s+(\S+):\s*(.*)", line
            )

            if syslog_match:
                priority = int(syslog_match.group(1))
                timestamp = syslog_match.group(2)
                hostname = syslog_match.group(3)
                service = syslog_match.group(4)
                message = syslog_match.group(5)

                # Extract severity from priority (RFC 3164)
                severity_code = priority & 0x07
                severity_map = {
                    0: "emergency",
                    1: "alert",
                    2: "critical",
                    3: "error",
                    4: "warning",
                    5: "notice",
                    6: "info",
                    7: "debug",
                }
                severity = severity_map.get(severity_code, "unknown")
            else:
                # journald lines often look like:
                # "Jan 22 14:00:01 hostname service[pid]: message"
                # or raw app logs. We keep message as-is and try to extract timestamp-ish token.
                timestamp_match = re.search(
                    r"(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})", line
                )
                timestamp = timestamp_match.group(1) if timestamp_match else ""
                message = line
                hostname = ""
                service = source or ""
                severity = None

            is_important, matched_pattern = self.is_important_log(message, severity)
            should_include = self.should_include_log(message, severity)

            if is_important or should_include or include_all:
                log_entry = {
                    "ticket_id": ticket_id,
                    "timestamp": timestamp,
                    "value": message,
                    "severity": (severity or "unknown"),
                    "hostname": hostname,
                    "host": hostname,
                    "appname": service,
                    "facility": "",
                    "measurement": "syslog",
                    "is_important": True,
                    "matched_pattern": matched_pattern
                    or ("all_logs" if include_all else "keyword_match"),
                    "line_number": line_num,
                    "source": source,
                }
                logs.append(log_entry)

        return logs

    def discover_server_log_sources(self) -> List[str]:
        """Best-effort discovery of common Linux log files."""
        candidates = [
            "/var/log/syslog",
            "/var/log/messages",
            "/var/log/kern.log",
            "/var/log/auth.log",
            "/var/log/daemon.log",
            "/var/log/nginx/error.log",
            "/var/log/apache2/error.log",
        ]
        return [p for p in candidates if os.path.exists(p) and os.path.isfile(p)]

    def collect_journalctl_lines(self, since: str = "1 hour ago", max_lines: int = 5000) -> List[str]:
        """Collect logs from journald using journalctl (if available)."""
        try:
            proc = subprocess.run(
                [
                    "journalctl",
                    "--no-pager",
                    "--since",
                    since,
                    "-n",
                    str(max_lines),
                    "-o",
                    "short",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if proc.returncode != 0:
                return []
            return proc.stdout.splitlines()
        except FileNotFoundError:
            return []
        except Exception:
            return []
    
    def group_logs_by_severity(self, logs: List[Dict]) -> Dict[str, List[Dict]]:
        """Group logs by severity level.
        
        Args:
            logs: List of log entries
            
        Returns:
            Dictionary grouped by severity
        """
        grouped = defaultdict(list)
        
        for log in logs:
            severity = log.get('severity', 'unknown').lower()
            grouped[severity].append(log)
        
        return dict(grouped)
    
    def create_output_file(
        self,
        logs: List[Dict],
        output_dir: str,
        ticket_id: Optional[str] = None,
        hostname: Optional[str] = None
    ) -> str:
        """Create output file with extracted important logs.
        
        Args:
            logs: List of important log entries
            output_dir: Directory to save output file
            ticket_id: Ticket ID
            hostname: Hostname
            
        Returns:
            Path to created output file
        """
        if not logs:
            print("No important logs found to write.", file=sys.stderr)
            return ""
        
        def _safe_token(value: str, max_len: int = 30) -> str:
            value = (value or "").strip().lower()
            # keep letters/numbers/dot/dash/underscore only, convert others to dash
            value = re.sub(r"[^a-z0-9._-]+", "-", value)
            value = re.sub(r"-{2,}", "-", value).strip("-")
            return value[:max_len] if value else ""

        def _level_from_severity(sev: str) -> str:
            sev_l = (sev or "").lower()
            if sev_l in ["critical", "alert", "emergency", "error", "err", "warning", "warn"]:
                return "high"
            return "normal"

        # --- Build a short, meaningful filename: TICKET-YYYYMMDD_HHMM-host-level.txt
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        tid = (ticket_id or "UNKNOWN").upper()

        # prefer a hostname from data; fall back to provided hostname arg
        hostnames = [log.get("hostname", "").strip() for log in logs if log.get("hostname", "").strip()]
        host_raw = hostnames[0] if hostnames else (hostname or "")
        host_short = _safe_token(host_raw.split(".")[0] if host_raw else "", max_len=25) or "host"

        # level = most critical (HIGH beats NORMAL) present in this output
        severity_counts = defaultdict(int)
        for log in logs:
            severity_counts[(log.get("severity") or "unknown").lower()] += 1

        def _sev_rank(sev: str) -> int:
            return self.SEVERITY_LEVELS.get(sev.lower(), 999)

        top_sev = min(severity_counts.keys(), key=_sev_rank) if severity_counts else "unknown"
        top_level = _level_from_severity(top_sev)

        filename = f"{tid}-{ts}-{host_short}-{top_level}.txt"
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)
        
        # Write logs to file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write("=" * 80 + "\n")
                f.write(f"LOG PARSER OUTPUT\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Ticket ID: {ticket_id or 'UNKNOWN'}\n")
                f.write(f"Total Important Logs Found: {len(logs)}\n")
                f.write("=" * 80 + "\n\n")
                
                # Group by severity
                grouped_logs = self.group_logs_by_severity(logs)
                
                # Write logs grouped by severity (most critical first)
                severity_order = ['critical', 'alert', 'error', 'err', 'warning', 'warn', 'notice', 'info', 'debug', 'unknown']
                
                for severity in severity_order:
                    if severity in grouped_logs:
                        f.write(f"\n{'=' * 80}\n")
                        f.write(f"SEVERITY: {severity.upper()} ({len(grouped_logs[severity])} entries)\n")
                        f.write(f"{'=' * 80}\n\n")
                        
                        for log in grouped_logs[severity]:
                            # Format matched pattern for better readability
                            pattern = log.get('matched_pattern', 'N/A')
                            if pattern and pattern != 'N/A':
                                # Clean up pattern display
                                if pattern.startswith('severity:'):
                                    pattern_display = f"Severity-based ({pattern.replace('severity:', '')})"
                                elif pattern.startswith('\\b') or pattern.startswith('r\''):
                                    # Extract readable pattern name
                                    pattern_clean = pattern.replace('\\b', '').replace('r\'', '').replace('\'', '')
                                    pattern_display = f"Error pattern: {pattern_clean}"
                                elif pattern == 'keyword_match':
                                    pattern_display = "Important keyword detected"
                                elif pattern == 'normal_log':
                                    pattern_display = "Normal log (included with --include-all)"
                                else:
                                    pattern_display = pattern
                            else:
                                pattern_display = 'N/A'
                            
                            f.write(f"Timestamp: {log.get('timestamp', 'N/A')}\n")
                            f.write(f"Hostname: {log.get('hostname', 'N/A')}\n")
                            f.write(f"Host: {log.get('host', 'N/A')}\n")
                            f.write(f"App/Service: {log.get('appname', 'N/A')}\n")
                            # Show a simple, easy-to-read level instead of syslog severity
                            raw_sev = (log.get("severity") or "unknown")
                            level = "HIGH" if _level_from_severity(raw_sev) == "high" else "NORMAL"
                            f.write(f"Level: {level}\n")
                            f.write(f"Reason Included: {pattern_display}\n")
                            f.write(f"Log Message:\n{log.get('value', 'N/A')}\n")
                            f.write("-" * 80 + "\n\n")
                
                # Write summary
                f.write("\n" + "=" * 80 + "\n")
                f.write("SUMMARY\n")
                f.write("=" * 80 + "\n")
                for severity, count in sorted(severity_counts.items()):
                    f.write(f"{severity.upper()}: {count}\n")
        
        except Exception as e:
            print(f"Error writing output file: {str(e)}", file=sys.stderr)
            return ""
        
        return output_path


def main():
    """Main function to run the log parser."""
    parser = argparse.ArgumentParser(
        description='Parse logs and extract errors, exceptions, and important details',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Parse CSV file
  python log_parser.py --csv Logs/influx-INC6052856.csv --output parsed_logs/
  
  # Parse server log file
  python log_parser.py --server /var/log/syslog --output parsed_logs/
  
  # Parse multiple CSV files
  python log_parser.py --csv-dir Logs/ --output parsed_logs/
  
  # Parse with custom ticket ID
  python log_parser.py --csv file.csv --ticket-id INC123456 --output parsed_logs/
        """
    )
    
    parser.add_argument(
        '--csv',
        type=str,
        help='Path to CSV log file (InfluxDB format)'
    )
    
    parser.add_argument(
        '--csv-dir',
        type=str,
        help='Directory containing CSV log files'
    )
    
    parser.add_argument(
        '--server',
        type=str,
        help='Path to server log file (syslog or plain text format)'
    )

    parser.add_argument(
        '--server-auto',
        action='store_true',
        help='Auto-discover common server log locations (/var/log/*) and parse them'
    )

    parser.add_argument(
        '--journal',
        action='store_true',
        help='Also read journald logs using journalctl (if available)'
    )

    parser.add_argument(
        '--since',
        type=str,
        default='1 hour ago',
        help='When using --journal, time range passed to journalctl --since (default: \"1 hour ago\")'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='parsed_logs',
        help='Output directory for parsed logs (default: parsed_logs)'
    )
    
    parser.add_argument(
        '--ticket-id',
        type=str,
        help='Ticket ID (if not found in filename)'
    )
    
    parser.add_argument(
        '--case-sensitive',
        action='store_true',
        help='Use case-sensitive pattern matching'
    )
    
    parser.add_argument(
        '--include-all',
        action='store_true',
        help='Include all logs regardless of severity (useful for testing)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not any([args.csv, args.csv_dir, args.server, args.server_auto, args.journal]):
        parser.error("Must specify one of: --csv, --csv-dir, --server, --server-auto, or --journal")
    
    # Initialize parser
    log_parser = LogParser(case_sensitive=args.case_sensitive)
    log_parser.include_all = args.include_all
    
    all_logs = []
    processed_files = []
    
    # Process CSV file
    if args.csv:
        if not os.path.exists(args.csv):
            print(f"Error: CSV file not found: {args.csv}", file=sys.stderr)
            sys.exit(1)
        
        print(f"Parsing CSV file: {args.csv}")
        logs = log_parser.parse_csv_logs(args.csv)
        all_logs.extend(logs)
        processed_files.append(args.csv)
        if args.verbose:
            print(f"  Processed log entries, found {len(logs)} important ones")
        else:
            print(f"Found {len(logs)} important log entries")
    
    # Process CSV directory
    if args.csv_dir:
        if not os.path.isdir(args.csv_dir):
            print(f"Error: Directory not found: {args.csv_dir}", file=sys.stderr)
            sys.exit(1)
        
        csv_files = list(Path(args.csv_dir).glob("*.csv"))
        print(f"Found {len(csv_files)} CSV files in {args.csv_dir}")
        
        for csv_file in csv_files:
            print(f"Parsing: {csv_file}")
            logs = log_parser.parse_csv_logs(str(csv_file))
            all_logs.extend(logs)
            processed_files.append(str(csv_file))
            print(f"  Found {len(logs)} important log entries")
    
    # Process server log file
    if args.server:
        if not os.path.exists(args.server):
            print(f"Error: Server log file not found: {args.server}", file=sys.stderr)
            sys.exit(1)
        
        print(f"Parsing server log file: {args.server}")
        logs = log_parser.parse_server_logs(args.server, ticket_id=args.ticket_id)
        all_logs.extend(logs)
        processed_files.append(args.server)
        print(f"Found {len(logs)} important log entries")

    # Auto-discover server log files
    if args.server_auto:
        sources = log_parser.discover_server_log_sources()
        if not sources:
            print("No common server log files found for auto-discovery.", file=sys.stderr)
        else:
            print(f"Auto-discovered {len(sources)} log file(s)")
            for p in sources:
                print(f"Parsing: {p}")
                logs = log_parser.parse_server_logs(p, ticket_id=args.ticket_id)
                all_logs.extend(logs)
                processed_files.append(p)

    # Read journald (journalctl)
    if args.journal:
        print(f"Collecting journald logs via journalctl (since: {args.since})")
        lines = log_parser.collect_journalctl_lines(since=args.since, max_lines=5000)
        if not lines:
            print("No journald logs collected (journalctl unavailable or permission denied).", file=sys.stderr)
        else:
            logs = log_parser.parse_server_log_lines(lines, ticket_id=args.ticket_id, source="journald")
            all_logs.extend(logs)
            processed_files.append("journald")
            print(f"Found {len(logs)} important log entries from journald")
    
    # Create output file
    if all_logs:
        # Determine ticket ID
        ticket_id = args.ticket_id
        if not ticket_id and processed_files:
            ticket_id = log_parser.extract_ticket_id(processed_files[0])
        
        # Get hostname from logs
        hostnames = set(log.get('hostname', '') for log in all_logs if log.get('hostname'))
        hostname = sorted(hostnames)[0] if hostnames else None
        
        print(f"\nCreating output file...")
        output_path = log_parser.create_output_file(
            all_logs,
            args.output,
            ticket_id=ticket_id,
            hostname=hostname
        )
        
        if output_path:
            print(f"Output file created: {output_path}")
            print(f"Total important logs: {len(all_logs)}")
            
            # Print summary
            severity_counts = defaultdict(int)
            for log in all_logs:
                severity_counts[log.get('severity', 'unknown')] += 1
            
            print("\nSummary by severity:")
            for severity, count in sorted(severity_counts.items()):
                print(f"  {severity.upper()}: {count}")
        else:
            print("Failed to create output file", file=sys.stderr)
            sys.exit(1)
    else:
        print("No important logs found in the provided files.")
        sys.exit(0)


if __name__ == '__main__':
    main()
