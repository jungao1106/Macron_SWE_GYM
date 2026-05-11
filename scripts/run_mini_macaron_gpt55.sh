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

exec mini \
  -c mini.yaml \
  -c configs/mini-swe-agent/macaron_gpt55.yaml \
  -c "model.model_kwargs.api_base=${MACARON_BASE_URL:-https://pi-api.macaron.xin}" \
  -m "${MACARON_MODEL:-gpt-5.5}" \
  "$@"
