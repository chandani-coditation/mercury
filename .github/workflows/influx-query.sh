name: influx-query

on:
  workflow_dispatch:
    inputs:
      tickets:
        description: "Tickets JSON array"
        required: true
        type: string
      window_minutes:
        description: "Time window before ticket creation"
        required: false
        default: "15"

permissions:
  contents: read

jobs:
  influx-query:
    runs-on: self-hosted
    timeout-minutes: 10

    strategy:
      fail-fast: false
      matrix:
        ticket: ${{ fromJson(inputs.tickets) }}

    environment: np

    env:
      INFLUX_URL: ${{ vars.INFLUX_URL }}
      ORG: ${{ vars.ORG }}
      BUCKET: ${{ vars.BUCKET }}
      INFLUX_TOKEN: ${{ secrets.INFLUX_TOKEN }}

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Fetch logs for ticket
        shell: bash
        run: |
          set -e
          chmod +x scripts/influx-query.sh
          scripts/influx-query.sh \
            '${{ toJson(matrix.ticket) }}' \
            '${{ inputs.window_minutes }}'

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: influx-${{ matrix.ticket.ticket_id }}
          path: outputs/influx-${{ matrix.ticket.ticket_id }}.csv
          retention-days: 1

      - name: Cleanup local files
        if: always()
        run: rm -rf outputs
