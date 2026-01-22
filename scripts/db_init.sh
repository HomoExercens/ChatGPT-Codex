#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT_DIR}/.venv"

export PYTHONPATH="${ROOT_DIR}/services/api:${ROOT_DIR}/packages/sim:${ROOT_DIR}/packages/rl:${ROOT_DIR}/packages/shared"
export NEUROLEAGUE_DB_URL="${NEUROLEAGUE_DB_URL:-sqlite:///${ROOT_DIR}/artifacts/neuroleague.db}"

mkdir -p "${ROOT_DIR}/artifacts"

"${VENV}/bin/alembic" -c "${ROOT_DIR}/services/api/alembic.ini" upgrade head
