#!/bin/bash
# Run one FormSaathi task with Muse Code (headless). Usage: ./run_task.sh N
set -o pipefail
SPECS="$(cd "$(dirname "$0")" && pwd)"
WS="${WS:-$HOME/Desktop/formsaathi-muse}"
cd "$WS" || exit 1
source "$WS/.venv/bin/activate"
N=$(printf "%02d" "$1")
echo "=== Task $1 started $(date) ==="
muse exec --workspace "$WS" --model muse-spark-1.3 --effort high --approval-mode never \
  --sandbox-network enabled --max-model-steps 120 --prompt-file "$SPECS/run_$N.md" 2>&1 | tee "$SPECS/log_$N.txt"
status=$?
echo "=== Task $1 finished (exit $status) $(date) ==="; git -C "$WS" log --oneline | head -3
exit $status
