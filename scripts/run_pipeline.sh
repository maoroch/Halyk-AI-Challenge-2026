#!/usr/bin/env bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

echo "============================================================"
echo " Starting Halyk AI Challenge Agent Pipeline "
echo "============================================================"

"$PYTHON_BIN" scripts/run_pipeline.py

echo "============================================================"
echo " Execution finished successfully! Result saved to submission.json "
echo "============================================================"
