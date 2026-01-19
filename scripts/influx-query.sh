#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="outputs"
OUTFILE=""
STEP_1_DISKSIZE=0
STEP_2_DISKSIZE=0
STEP_3_DISKSIZE=0

cleanup_on_exit() {
  local exit_code=$?
  
  if [[ $exit_code -ne 0 ]]; then
    echo "Exit trap triggered with error (exit code: $exit_code)"
  fi
  
  if [[ -f "$OUTFILE" ]]; then
    echo "Deleting log file: $OUTFILE"
    rm -f "$OUTFILE"
    
    STEP_3_DISKSIZE=$(disk_usage_mb)
    echo "step_3_disksize: ${STEP_3_DISKSIZE}MB"
    
    if [[ $STEP_2_DISKSIZE -gt 0 ]]; then
      disk_freed=$((STEP_2_DISKSIZE - STEP_3_DISKSIZE))
      echo "Disk freed: ${disk_freed}MB"
      
      if [[ $STEP_3_DISKSIZE -gt $STEP_2_DISKSIZE ]]; then
        echo "WARNING: Disk usage increased after cleanup"
      fi
    fi
  fi
  
  exit $exit_code
}

trap cleanup_on_exit EXIT INT TERM

: "${INFLUX_URL:?missing}"
: "${ORG:?missing}"
: "${BUCKET:?missing}"
: "${INFLUX_TOKEN:?missing}"

TICKET_ID="$1"
CREATED_AT="$2"
WINDOW_MINUTES="${3:-15}"

if [[ -z "$TICKET_ID" ]]; then
  echo "ERROR: Ticket ID is required"
  exit 1
fi

if [[ -z "$CREATED_AT" ]]; then
  echo "ERROR: Ticket creation date is required"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

disk_usage_mb() {
  df -Pm . | awk 'NR==2 {print $3}'
}

START=$(date -u -d "$CREATED_AT - ${WINDOW_MINUTES} minutes" +"%Y-%m-%dT%H:%M:%SZ")
END=$(date -u -d "$CREATED_AT" +"%Y-%m-%dT%H:%M:%SZ")

OUTFILE="$OUTPUT_DIR/influx-${TICKET_ID}.csv"

echo "Ticket: $TICKET_ID"
echo "Time window: $START -> $END"

STEP_1_DISKSIZE=$(disk_usage_mb)
echo "step_1_disksize: ${STEP_1_DISKSIZE}MB"

FLUX_QUERY=$(cat <<EOM
from(bucket: "$BUCKET")
  |> range(start: time(v: "$START"), stop: time(v: "$END"))
EOM
)

echo "Fetching logs from InfluxDB..."
curl -sS \
  -X POST "$INFLUX_URL/api/v2/query?org=$ORG" \
  -H "Authorization: Token $INFLUX_TOKEN" \
  -H "Content-Type: application/vnd.flux" \
  -H "Accept: application/csv" \
  --data-binary "$FLUX_QUERY" \
  -o "$OUTFILE"

STEP_2_DISKSIZE=$(disk_usage_mb)
echo "step_2_disksize: ${STEP_2_DISKSIZE}MB"
disk_increase=$((STEP_2_DISKSIZE - STEP_1_DISKSIZE))
echo "Disk increase: ${disk_increase}MB"

if [[ -f "$OUTFILE" ]]; then
  file_size=$(du -h "$OUTFILE" | cut -f1)
  echo "Created: $OUTFILE (size: $file_size)"
else
  echo "ERROR: Failed to create output file"
  exit 1
fi

if [[ ! -s "$OUTFILE" ]]; then
  echo "WARNING: No logs fetched for $TICKET_ID (empty file)"
fi

echo "Ticket $TICKET_ID processing completed"
