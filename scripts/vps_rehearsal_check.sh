#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${NEUROLEAGUE_PUBLIC_BASE_URL:-}}"
BASE_URL="${BASE_URL%/}"
if [[ -z "${BASE_URL}" ]]; then
  echo "usage: scripts/vps_rehearsal_check.sh <base_url> [admin_token]" >&2
  exit 2
fi

ADMIN_TOKEN="${2:-${NEUROLEAGUE_ADMIN_TOKEN:-}}"

export NEUROLEAGUE_PUBLIC_BASE_URL="${BASE_URL}"
export NEUROLEAGUE_ADMIN_TOKEN="${ADMIN_TOKEN}"
export DEPLOY_SMOKE_EXTENDED="1"

echo "NeuroLeague VPS rehearsal check"
echo "- base_url=${BASE_URL}"
if [[ -n "${ADMIN_TOKEN}" ]]; then
  echo "- admin_token=***"
else
  echo "- admin_token=(missing; /api/ops/status will be skipped)"
fi

./scripts/deploy_smoke.sh

