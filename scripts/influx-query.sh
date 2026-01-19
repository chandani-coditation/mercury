#!/usr/bin/env bash
set -euo pipefail

#################################
# CONFIG
#################################
OUTPUT_DIR="outputs"
ARTIFACT_DIR="artifacts"
TEST_DOWNLOAD_URL="https://raw.githubusercontent.com/torvalds/linux/master/README"


TICKETS_JSON='[
  {"ticket_id":"INC6052856"},
  {"ticket_id":"INC6052852"}
]'

#################################
# FUNCTIONS
#################################

get_disk_mb() {
  df -Pm . | awk 'NR==2 {print $4}'
}

cleanup() {
  echo "🔹 Running final cleanup (EXIT trap)"

  if [[ -n "${OUTFILE:-}" && -f "$OUTFILE" ]]; then
    rm -f "$OUTFILE"
    echo "Deleted leftover file: $OUTFILE"
  fi
}

trap cleanup EXIT

#################################
# PREP
#################################

mkdir -p "$OUTPUT_DIR" "$ARTIFACT_DIR"

mapfile -t TICKET_IDS < <(echo "$TICKETS_JSON" | jq -r '.[].ticket_id')

#################################
# MAIN LOOP (SEQUENTIAL)
#################################

for TICKET_ID in "${TICKET_IDS[@]}"; do
  echo "======================================"
  echo "Ticket: $TICKET_ID"

  STEP1_DISK=$(get_disk_mb)
  echo "Disk before fetch: ${STEP1_DISK}MB"

  OUTFILE="${OUTPUT_DIR}/log-${TICKET_ID}.bin"
  ARTIFACT_PATH="${ARTIFACT_DIR}/${TICKET_ID}/log.bin"

  mkdir -p "$(dirname "$ARTIFACT_PATH")"

  echo "Fetching logs (test download)..."
  curl -sSfL "$TEST_DOWNLOAD_URL" -o "$OUTFILE"

  STEP2_DISK=$(get_disk_mb)
  echo "Disk after fetch: ${STEP2_DISK}MB"

  if [[ ! -s "$OUTFILE" ]]; then
    echo "WARNING: No logs fetched for $TICKET_ID"
    continue
  fi

  echo "Uploading to artifact path: $ARTIFACT_PATH"
  mv "$OUTFILE" "$ARTIFACT_PATH"

  echo "Local file deleted"

  STEP3_DISK=$(get_disk_mb)
  echo "Disk after cleanup: ${STEP3_DISK}MB"

  if [[ "$STEP3_DISK" -ge "$STEP2_DISK" ]]; then
    echo "ERROR: Disk cleanup failed for $TICKET_ID"
    exit 1
  fi

  echo "✔ Ticket $TICKET_ID processed successfully"
done

echo "======================================"
echo "All tickets processed successfully"
echo "Artifacts stored in: $ARTIFACT_DIR"
