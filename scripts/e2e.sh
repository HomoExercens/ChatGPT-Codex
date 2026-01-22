#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export NEUROLEAGUE_E2E_FAST="1"
export NEUROLEAGUE_DEMO_MODE="${NEUROLEAGUE_DEMO_MODE:-1}"
export NEUROLEAGUE_ADMIN_TOKEN="${NEUROLEAGUE_ADMIN_TOKEN:-admintest}"
export NEUROLEAGUE_DISCORD_OAUTH_MOCK="${NEUROLEAGUE_DISCORD_OAUTH_MOCK:-1}"
export NEUROLEAGUE_DISCORD_MODE="${NEUROLEAGUE_DISCORD_MODE:-mock}"
export NEUROLEAGUE_PUBLIC_BASE_URL="${NEUROLEAGUE_PUBLIC_BASE_URL:-http://127.0.0.1:3000}"
export NEUROLEAGUE_STEAM_APP_ID="${NEUROLEAGUE_STEAM_APP_ID:-480}"
export NEUROLEAGUE_DISCORD_INVITE_URL="${NEUROLEAGUE_DISCORD_INVITE_URL:-https://discord.com/}"

kill_tree() {
  local pid="${1}"
  local children
  children="$(pgrep -P "${pid}" 2>/dev/null || true)"
  for c in ${children}; do
    kill_tree "${c}"
  done
  kill "${pid}" 2>/dev/null || true
}

mkdir -p "${ROOT_DIR}/docs/screenshots"
rm -f "${ROOT_DIR}/docs/screenshots/"*.png || true

make -C "${ROOT_DIR}" db-init seed-data-reset
make -C "${ROOT_DIR}" ops-preflight POOL_LIMIT=6 OPPONENTS=3 SEED_SET_COUNT=1

if [[ ! -d "${ROOT_DIR}/apps/web/node_modules" ]]; then
  (cd "${ROOT_DIR}/apps/web" && npm ci)
fi

if [[ "${CI:-}" == "true" ]]; then
  (cd "${ROOT_DIR}/apps/web" && npx playwright install --with-deps chromium)
else
  (cd "${ROOT_DIR}/apps/web" && npx playwright install chromium)
fi

DEV_PID=""
cleanup() {
  if [[ -n "${DEV_PID}" ]]; then
    kill_tree "${DEV_PID}"
  fi
}
trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

"${ROOT_DIR}/scripts/dev.sh" &
DEV_PID=$!

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:3000" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

(cd "${ROOT_DIR}/apps/web" && npx playwright test)
