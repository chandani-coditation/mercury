#!/usr/bin/env bash
set -euo pipefail

# ---------- ENV VALIDATION ----------
: "${INFLUX_URL:?missing}"
: "${ORG:?missing}"
: "${BUCKET:?missing}"
: "${INFLUX_TOKEN:?missing}"

TICKET_JSON="$1"
WINDOW_MINUTES="${2:-15}"

OUTPUT_DIR="outputs"
mkdir -p "$OUTPUT_DIR"

disk_usage_mb() {
  df -Pm . | awk 'NR==2 {print $3}'
}

cleanup() {
  [[ -f "$OUTFILE" ]] && rm -f "$OUTFILE"
}
trap cleanup EXIT

# ---------- PARSE INPUT ----------
TICKET_ID=$(jq -r '.ticket_id' <<< "$TICKET_JSON")
CREATED_AT=$(jq -r '.ticket_created_date' <<< "$TICKET_JSON")

START=$(date -u -d "$CREATED_AT - ${WINDOW_MINUTES} minutes" +"%Y-%m-%dT%H:%M:%SZ")
END=$(date -u -d "$CREATED_AT" +"%Y-%m-%dT%H:%M:%SZ")

OUTFILE="$OUTPUT_DIR/influx-${TICKET_ID}.csv"

echo "Ticket: $TICKET_ID"
echo "Time window: $START -> $END"

step_1=$(disk_usage_mb)
echo "Disk before fetch: ${step_1}MB"

# ---------- FLUX QUERY ----------
FLUX_QUERY=$(cat <<EOM
from(bucket: "$BUCKET")
  |> range(start: time(v: "$START"), stop: time(v: "$END"))
EOM
)

# ---------- FETCH ----------
# curl -sS \
#   -X POST "$INFLUX_URL/api/v2/query?org=$ORG" \
#   -H "Authorization: Token $INFLUX_TOKEN" \
#   -H "Content-Type: application/vnd.flux" \
#   -H "Accept: application/csv" \
#   --data-binary "$FLUX_QUERY" \
#   -o "$OUTFILE"

curl -s https://jsonplaceholder.typicode.com/posts -o outputs/sample.json

step_2=$(disk_usage_mb)
echo "Disk after fetch: ${step_2}MB"
echo "Created: $OUTFILE"

if [[ ! -s "$OUTFILE" ]]; then
  echo "WARNING: No logs fetched for $TICKET_ID"
fi

echo "Artifact path: outputs/$(basename "$OUTFILE")"

rm -f "$OUTFILE"

step_3=$(disk_usage_mb)
echo "Disk after cleanup: ${step_3}MB"

if (( step_3 >= step_2 )); then
  echo "ERROR: Disk cleanup failed"
  exit 1
fi

echo "Ticket $TICKET_ID completed successfully"
