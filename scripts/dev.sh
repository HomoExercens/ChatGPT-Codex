#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PYTHONPATH="${ROOT_DIR}/services/api:${ROOT_DIR}/packages/sim:${ROOT_DIR}/packages/rl:${ROOT_DIR}/packages/shared"
export NEUROLEAGUE_DB_URL="${NEUROLEAGUE_DB_URL:-sqlite:///${ROOT_DIR}/artifacts/neuroleague.db}"
export NEUROLEAGUE_ARTIFACTS_DIR="${NEUROLEAGUE_ARTIFACTS_DIR:-${ROOT_DIR}/artifacts}"
export NEUROLEAGUE_PUBLIC_BASE_URL="${NEUROLEAGUE_PUBLIC_BASE_URL:-http://127.0.0.1:3000}"

API_PID=""
WEB_PID=""

kill_tree() {
  local pid="${1}"
  local children
  children="$(pgrep -P "${pid}" 2>/dev/null || true)"
  for c in ${children}; do
    kill_tree "${c}"
  done
  kill "${pid}" 2>/dev/null || true
}

cleanup() {
  if [[ -n "${API_PID}" ]]; then
    kill_tree "${API_PID}"
  fi
  if [[ -n "${WEB_PID}" ]]; then
    kill_tree "${WEB_PID}"
  fi
}
trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

"${ROOT_DIR}/scripts/run_api.sh" &
API_PID=$!

(cd "${ROOT_DIR}/apps/web" && npm run dev -- --host 0.0.0.0 --port 3000) &
WEB_PID=$!

wait "${API_PID}" "${WEB_PID}"
