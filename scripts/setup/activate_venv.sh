#!/bin/bash
# Helper script to activate virtual environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -d "$PROJECT_ROOT/venv" ]; then
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/venv/bin/activate"
    echo " Virtual environment activated"
    echo "  Python: $(which python)"
    echo "  Project: $PROJECT_ROOT"
else
    echo " Virtual environment not found at $PROJECT_ROOT/venv"
    echo "  Create it with: python3 -m venv venv"
    exit 1
fi

