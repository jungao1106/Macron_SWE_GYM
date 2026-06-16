#!/usr/bin/env bash
# Launch a SWE-Bench benchmark job in the background inside a tmux session.
#
# The job runs `scripts/run_benchmark.py` with the active `.env` loaded, names
# the tmux session after the job, and streams shell output to
# `run_logs/<job>.out`. This is the layout `scripts/monitor_benchmark_job.sh`
# expects, so you can launch here and watch there.
#
# Usage:
#   scripts/start_benchmark.sh [--job-name NAME] [extra run_benchmark.py args...]
#
# Examples:
#   scripts/start_benchmark.sh
#   scripts/start_benchmark.sh --job-name full_pi_novita
#   AGENT_TYPE=mini LLM_PROVIDER=macaron scripts/start_benchmark.sh \
#     --job-name smoke_mini_macaron --n-tasks 1
#
# After launch:
#   scripts/monitor_benchmark_job.sh <job-name>
#   tmux attach -t <job-name>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

command -v tmux >/dev/null 2>&1 || { echo "tmux is required but not installed" >&2; exit 1; }

# Resolve the job name from --job-name, then JOB_NAME, with a provider/agent default.
job_name=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-name)
      job_name="${2:?--job-name needs a value}"
      shift 2
      ;;
    --job-name=*)
      job_name="${1#*=}"
      shift
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$job_name" ]]; then
  job_name="${JOB_NAME:-${AGENT_TYPE:-pi}_${LLM_PROVIDER:-novita}_swebench}"
fi

run_log="${ROOT}/run_logs/${job_name}.out"
mkdir -p "${ROOT}/run_logs"

if tmux has-session -t "$job_name" 2>/dev/null; then
  echo "tmux session '${job_name}' already exists. Attach with: tmux attach -t ${job_name}" >&2
  exit 1
fi

# Build the inner command. Re-source .env inside the tmux shell so the job has
# the same environment regardless of how tmux inherits it. Override the
# interpreter with PYTHON= when not running inside the marcronv1 conda env.
python_bin="${PYTHON:-python}"
python_cmd="${python_bin} scripts/run_benchmark.py --job-name ${job_name}"
for a in "${args[@]+"${args[@]}"}"; do
  python_cmd+=" $(printf '%q' "$a")"
done

inner="cd $(printf '%q' "$ROOT"); \
if [[ -f .env ]]; then set -a; source .env; set +a; fi; \
${python_cmd} 2>&1 | tee $(printf '%q' "$run_log")"

tmux new-session -d -s "$job_name" "$inner"

echo "Started job '${job_name}' in tmux session '${job_name}'."
echo "  shell output: ${run_log}"
echo "  runtime log:  ${ROOT}/logs/${job_name}.log"
echo "  monitor:      scripts/monitor_benchmark_job.sh ${job_name}"
echo "  attach:       tmux attach -t ${job_name}"
