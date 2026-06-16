#!/usr/bin/env bash
# Stop a benchmark job launched with scripts/start_benchmark.sh by killing its
# tmux session. Runtime logs and job outputs are left in place.
#
# Usage:
#   scripts/stop_benchmark.sh JOB_NAME
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 JOB_NAME" >&2
  exit 2
fi

job_name="$1"

if ! tmux has-session -t "$job_name" 2>/dev/null; then
  echo "No tmux session named '${job_name}'." >&2
  exit 1
fi

tmux kill-session -t "$job_name"
echo "Stopped job '${job_name}'."
