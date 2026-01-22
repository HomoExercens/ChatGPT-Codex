#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT_DIR}/.venv"

export PYTHONPATH="${ROOT_DIR}/services/api:${ROOT_DIR}/packages/sim:${ROOT_DIR}/packages/rl:${ROOT_DIR}/packages/shared"
export NEUROLEAGUE_DB_URL="${NEUROLEAGUE_DB_URL:-sqlite:///${ROOT_DIR}/artifacts/neuroleague.db}"
export NEUROLEAGUE_ARTIFACTS_DIR="${NEUROLEAGUE_ARTIFACTS_DIR:-${ROOT_DIR}/artifacts}"

if [[ "${NEUROLEAGUE_E2E_FAST:-}" == "1" ]]; then
  exec "${VENV}/bin/uvicorn" neuroleague_api.main:app --host 0.0.0.0 --port 8000
else
  exec "${VENV}/bin/uvicorn" neuroleague_api.main:app --host 0.0.0.0 --port 8000 --reload
fi
