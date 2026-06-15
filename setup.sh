#!/bin/bash
# One-time setup on Triton. Run once after copying the project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# On Triton, load a Python module if needed:
# module load python/3.10  (or whichever version is available — check with: module avail python)

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete. Add the cron job with: crontab -e"
echo "  0 8 * * 1-5 $SCRIPT_DIR/run_daily.sh >> $SCRIPT_DIR/logs/daily.log 2>&1"
mkdir -p "$SCRIPT_DIR/logs"
