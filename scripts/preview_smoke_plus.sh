#!/usr/bin/env bash
set -euo pipefail

# preview_smoke_plus.sh
# - Starts (or reuses) the local dev stack and validates:
#   - /api/ready, /playtest, /s/clip/<demo> OG meta + never-404 og:image
#   - playtest events can be written (basic DB check for sqlite dev)
#
# Output:
#   artifacts/handoff/preview_smoke_plus.log
#
# Notes:
# - This is designed for local "Quick Tunnel preview" workflows.
# - It does NOT require Docker.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OUT_DIR="${ROOT_DIR}/artifacts/handoff"
mkdir -p "${OUT_DIR}"
LOG_PATH="${OUT_DIR}/preview_smoke_plus.log"

exec > >(tee "${LOG_PATH}") 2>&1

BASE_URL="${SMOKE_BASE_URL:-http://127.0.0.1:3000}"
BASE_URL="${BASE_URL%/}"

echo "NeuroLeague preview_smoke_plus"
echo "- time: $(date -Is)"
echo "- BASE_URL: ${BASE_URL}"
echo "- cwd: ${ROOT_DIR}"

body_tmp="$(mktemp)"
headers_tmp="$(mktemp)"

fail() {
  echo "FAIL: ${1}" >&2
  exit 1
}

curl_code() {
  local method="${1}"
  local url="${2}"
  shift 2
  curl -sS -o "${body_tmp}" -w '%{http_code}' -X "${method}" "$@" "${url}" || echo "000"
}

expect_code_any() {
  local got="${1}"
  local wants="${2}"
  local label="${3}"
  for w in ${wants}; do
    if [[ "${got}" == "${w}" ]]; then
      return 0
    fi
  done
  echo "---- ${label} ----" >&2
  cat "${body_tmp}" >&2 || true
  fail "${label} (expected one of ${wants}, got ${got})"
}

DEV_STARTED="0"
DEV_PID=""

cleanup_all() {
  if [[ "${DEV_STARTED}" == "1" && -n "${DEV_PID}" ]]; then
    echo "[dev] stopping pid=${DEV_PID}"
    kill "${DEV_PID}" 2>/dev/null || true
  fi
  rm -f "${body_tmp}" "${headers_tmp}" 2>/dev/null || true
}
trap cleanup_all EXIT INT TERM

echo "[check] api ready?"
READY_CODE="$(curl_code GET "http://127.0.0.1:8000/api/ready")"
if [[ "${READY_CODE}" != "200" ]]; then
  mkdir -p "${ROOT_DIR}/artifacts/preview"
  echo "[dev] starting ./scripts/dev.sh (api not ready: code=${READY_CODE})"
  "${ROOT_DIR}/scripts/dev.sh" >"${ROOT_DIR}/artifacts/preview/dev_smoke.log" 2>&1 &
  DEV_PID=$!
  DEV_STARTED="1"
fi

echo "[wait] for /api/ready"
for i in $(seq 1 60); do
  READY_CODE="$(curl_code GET "http://127.0.0.1:8000/api/ready")"
  if [[ "${READY_CODE}" == "200" ]]; then
    echo "OK: /api/ready"
    break
  fi
  sleep 1
done
if [[ "${READY_CODE}" != "200" ]]; then
  fail "/api/ready timeout (code=${READY_CODE})"
fi

echo "[check] GET /playtest"
PLAYTEST_CODE="$(curl_code GET "${BASE_URL}/playtest")"
expect_code_any "${PLAYTEST_CODE}" "200 304" "GET /playtest"
echo "OK: /playtest"

echo "[check] demo_ids.json"
DEMO_CODE="$(curl_code GET "${BASE_URL}/api/assets/ops/demo_ids.json" -L)"
expect_code_any "${DEMO_CODE}" "200" "GET /api/assets/ops/demo_ids.json"
DEMO_REPLAY_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("clip_replay_id") or "").strip())
PY
)"
if [[ -z "${DEMO_REPLAY_ID}" ]]; then
  fail "demo_ids.json missing clip_replay_id"
fi
echo "OK: demo replay_id=${DEMO_REPLAY_ID}"

OG_URL="${BASE_URL}/s/clip/${DEMO_REPLAY_ID}?start=0.0&end=2.0&v=1"
echo "[check] share OG: ${OG_URL}"
OG_CODE="$(curl_code GET "${OG_URL}")"
expect_code_any "${OG_CODE}" "200" "GET /s/clip/<demo>"
grep -q 'property="og:title"' "${body_tmp}" || fail "OG missing og:title"
grep -q 'property="og:image"' "${body_tmp}" || fail "OG missing og:image"
OG_IMAGE="$(
  python3 - "${body_tmp}" <<'PY'
import re
import sys

html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'property="og:image" content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
)"
if [[ -z "${OG_IMAGE}" ]]; then
  fail "og:image empty"
fi
IMG_CODE="$(curl_code GET "${OG_IMAGE}")"
expect_code_any "${IMG_CODE}" "200 307" "GET og:image"
echo "OK: OG meta + og:image (never-404)"

echo "[check] create guest token"
GUEST_CODE="$(curl_code POST "${BASE_URL}/api/auth/guest" -H 'content-type: application/json' -d '{}')"
expect_code_any "${GUEST_CODE}" "200" "POST /api/auth/guest"
ACCESS_TOKEN="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(obj.get("access_token") or "")
PY
)"
if [[ -z "${ACCESS_TOKEN}" ]]; then
  fail "guest access_token missing"
fi
echo "OK: guest token"

SMOKE_ID="$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)"

echo "[check] playtest_opened event"
EV_CODE="$(curl_code POST "${BASE_URL}/api/events/track" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H 'content-type: application/json' \
  -d "{\"type\":\"playtest_opened\",\"source\":\"preview_smoke_plus\",\"meta\":{\"smoke_id\":\"${SMOKE_ID}\",\"demo_replay_id\":\"${DEMO_REPLAY_ID}\"}}")"
expect_code_any "${EV_CODE}" "200" "POST /api/events/track (playtest_opened)"
echo "OK: playtest_opened tracked"

echo "[check] playtest_step_completed event"
EV2_CODE="$(curl_code POST "${BASE_URL}/api/events/track" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H 'content-type: application/json' \
  -d "{\"type\":\"playtest_step_completed\",\"source\":\"preview_smoke_plus\",\"meta\":{\"smoke_id\":\"${SMOKE_ID}\",\"step_id\":1,\"demo_replay_id\":\"${DEMO_REPLAY_ID}\"}}")"
expect_code_any "${EV2_CODE}" "200" "POST /api/events/track (playtest_step_completed)"
echo "OK: playtest_step_completed tracked"

# Best-effort DB verification (sqlite dev default).
DB_PATH="${ROOT_DIR}/artifacts/neuroleague.db"
if [[ -f "${DB_PATH}" ]]; then
  echo "[check] sqlite events persisted (${DB_PATH})"
  python3 - "${DB_PATH}" "${SMOKE_ID}" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
smoke_id = sys.argv[2]
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute(
    "select count(*) from events where payload_json like ?",
    (f"%{smoke_id}%",),
)
n = int(cur.fetchone()[0] or 0)
if n <= 0:
    raise SystemExit("missing events row for smoke_id")
print(f"OK: events rows with smoke_id={smoke_id}: {n}")
PY
else
  echo "[skip] sqlite DB not found at ${DB_PATH} (cannot verify persistence)"
fi

echo "PASS: preview_smoke_plus"
