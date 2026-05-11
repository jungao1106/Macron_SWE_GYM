#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${MACARON_API_KEY:?Set MACARON_API_KEY in .env or the environment}"
export OPENAI_API_KEY="$MACARON_API_KEY"
export MSWEA_CONFIGURED="${MSWEA_CONFIGURED:-true}"
export MSWEA_COST_TRACKING="${MSWEA_COST_TRACKING:-ignore_errors}"

subset="${MSWEA_SWEBENCH_SUBSET:-verified}"
split="${MSWEA_SWEBENCH_SPLIT:-test}"
slice="${MSWEA_SWEBENCH_SLICE:-0:1}"
workers="${MSWEA_WORKERS:-1}"
output="${MSWEA_OUTPUT_DIR:-traces/mini_macaron_gpt55}"

exec mini-extra swebench \
  -c swebench.yaml \
  -c configs/mini-swe-agent/macaron_gpt55.yaml \
  -c "model.model_kwargs.api_base=${MACARON_BASE_URL:-https://pi-api.macaron.xin}" \
  -m "${MACARON_MODEL:-gpt-5.5}" \
  --subset "$subset" \
  --split "$split" \
  --slice "$slice" \
  --workers "$workers" \
  --output "$output" \
  "$@"
