#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${NEUROLEAGUE_PUBLIC_BASE_URL:-${PUBLIC_BASE_URL:-}}"
BASE_URL="${BASE_URL%/}"
if [[ -z "${BASE_URL}" ]]; then
  BASE_URL="http://127.0.0.1:3000"
fi

ADMIN_TOKEN="${NEUROLEAGUE_ADMIN_TOKEN:-${ADMIN_TOKEN:-}}"

body_tmp="$(mktemp)"
headers_tmp="$(mktemp)"
trap 'rm -f "${body_tmp}" "${headers_tmp}"' EXIT

fail() {
  echo "FAIL: ${1}" >&2
  exit 1
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

curl_code() {
  local method="${1}"
  local url="${2}"
  shift 2
  curl -sS -o "${body_tmp}" -w '%{http_code}' -X "${method}" "$@" "${url}" || echo "000"
}

curl_headers_code() {
  local method="${1}"
  local url="${2}"
  shift 2
  curl -sS -o "${body_tmp}" -D "${headers_tmp}" -w '%{http_code}' -X "${method}" "$@" "${url}" || echo "000"
}

curl_head_code() {
  local url="${1}"
  shift 1
  curl -sS -o /dev/null -D "${headers_tmp}" -w '%{http_code}' -I "$@" "${url}" || echo "000"
}

print_headers() {
  grep -i -E '^(HTTP/|etag:|cache-control:|accept-ranges:|content-range:|content-length:|location:)' "${headers_tmp}" \
    | tr -d '\r' \
    || true
}

require_header() {
  local header="${1}"
  local label="${2}"
  if ! grep -qi "^${header}:" "${headers_tmp}"; then
    echo "---- ${label} headers ----" >&2
    cat "${headers_tmp}" >&2 || true
    fail "${label}: missing header ${header}"
  fi
}

expect_code() {
  local got="${1}"
  local want="${2}"
  local label="${3}"
  if [[ "${got}" != "${want}" ]]; then
    echo "---- ${label} ----" >&2
    cat "${body_tmp}" >&2 || true
    fail "${label} (expected ${want}, got ${got})"
  fi
}

echo "NeuroLeague deploy smoke"
echo "- BASE_URL: ${BASE_URL}"

og_check() {
  local url="${1}"
  local label="${2}"

  local code
  code="$(curl_code GET "${url}")"
  expect_code "${code}" "200" "${label}"

  grep -q 'property="og:title"' "${body_tmp}" || fail "${label}: OG missing og:title"
  grep -q 'property="og:description"' "${body_tmp}" || fail "${label}: OG missing og:description"
  grep -q 'property="og:image"' "${body_tmp}" || fail "${label}: OG missing og:image"
  grep -q 'property="og:image:secure_url"' "${body_tmp}" || fail "${label}: OG missing og:image:secure_url"
  grep -q 'property="og:image:width"' "${body_tmp}" || fail "${label}: OG missing og:image:width"
  grep -q 'property="og:image:height"' "${body_tmp}" || fail "${label}: OG missing og:image:height"
  grep -q 'property="og:image:alt"' "${body_tmp}" || fail "${label}: OG missing og:image:alt"
  grep -q 'property="og:url"' "${body_tmp}" || fail "${label}: OG missing og:url"
  grep -q 'name="twitter:card"' "${body_tmp}" || fail "${label}: OG missing twitter:card"

  local og_image
  og_image="$(
    python3 - "${body_tmp}" <<'PY'
import re
import sys

html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'property="og:image" content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
  )"
  if [[ -z "${og_image}" ]]; then
    fail "${label}: og:image empty"
  fi

  local img_code
  img_code="$(curl_code GET "${og_image}")"
  expect_code_any "${img_code}" "200 307" "${label}: GET og:image"
}

HEALTH_CODE="$(curl_code GET "${BASE_URL}/api/health")"
expect_code "${HEALTH_CODE}" "200" "GET /api/health"
echo "OK: /api/health"

READY_CODE="$(curl_code GET "${BASE_URL}/api/ready")"
expect_code "${READY_CODE}" "200" "GET /api/ready"
python3 - "${body_tmp}" <<'PY'
import json
import sys

path = sys.argv[1]
obj = json.loads(open(path, encoding="utf-8").read())
if not isinstance(obj, dict):
    raise SystemExit("ready: invalid json")
status = obj.get("status")
db_ok = bool((obj.get("db") or {}).get("ok"))
storage_ok = bool((obj.get("storage") or {}).get("ok"))
if status not in ("ok", "fail"):
    raise SystemExit("ready: missing status")
if not db_ok:
    raise SystemExit("ready: db not ok")
if not storage_ok:
    raise SystemExit("ready: storage not ok")
PY
echo "OK: /api/ready (db/storage ok)"

SEASON_CODE="$(curl_code GET "${BASE_URL}/api/meta/season")"
expect_code "${SEASON_CODE}" "200" "GET /api/meta/season"
echo "OK: /api/meta/season"

# Create a guest token (used for auth-gated checks).
GUEST_CODE="$(curl_code POST "${BASE_URL}/api/auth/guest" -H 'content-type: application/json' -d '{}')"
expect_code "${GUEST_CODE}" "200" "POST /api/auth/guest"
ACCESS_TOKEN="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(obj.get("access_token") or "")
PY
)"
if [[ -z "${ACCESS_TOKEN}" ]]; then
  fail "guest token missing"
fi
echo "OK: /api/auth/guest"

REPLAY_ID=""
MATCH_ID=""
BUILD_ID=""
PROFILE_USER_ID=""
CHALLENGE_ID=""

# Prefer a stable demo replay id if seeded (served via /api/assets allowlist).
DEMO_CODE="$(curl_code GET "${BASE_URL}/api/assets/ops/demo_ids.json" -L)"
if [[ "${DEMO_CODE}" == "200" ]]; then
  REPLAY_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("clip_replay_id") or ""))
PY
)"
  MATCH_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("clip_match_id") or ""))
PY
)"
  BUILD_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("best_build_id") or ""))
PY
)"
  PROFILE_USER_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("featured_user_id") or ""))
PY
)"
  CHALLENGE_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("clip_challenge_id") or ""))
PY
)"
  if [[ -n "${REPLAY_ID}" ]]; then
    echo "OK: /api/assets/ops/demo_ids.json (replay_id=${REPLAY_ID})"
  fi
fi

if [[ -z "${REPLAY_ID}" ]]; then
  CLIPS_CODE="$(curl_code GET "${BASE_URL}/api/clips/feed?mode=1v1&sort=trending&algo=v2&limit=1" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
  expect_code "${CLIPS_CODE}" "200" "GET /api/clips/feed"
  REPLAY_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
items = obj.get("items") or []
rid = ""
if isinstance(items, list) and items:
    first = items[0]
    if isinstance(first, dict):
        rid = str(first.get("replay_id") or "")
print(rid)
PY
)"
fi
if [[ -z "${REPLAY_ID}" ]]; then
  fail "clips feed returned no replay_id (seed missing?)"
fi
echo "OK: replay_id=${REPLAY_ID}"

og_check "${BASE_URL}/s/clip/${REPLAY_ID}?start=0&end=12&v=1" "GET /s/clip/{replay_id}"
echo "OK: /s/clip OG meta + og:image"

ASSET_ALLOWLIST_CODE="$(curl_code GET "${BASE_URL}/api/assets/neuroleague.db")"
expect_code_any "${ASSET_ALLOWLIST_CODE}" "404" "GET /api/assets/neuroleague.db (allowlist)"
echo "OK: /api/assets allowlist (blocks neuroleague.db)"

if [[ -n "${BUILD_ID}" ]]; then
  og_check "${BASE_URL}/s/build/${BUILD_ID}" "GET /s/build/{blueprint_id}"
  echo "OK: /s/build OG meta + og:image"
fi
if [[ -n "${PROFILE_USER_ID}" ]]; then
  og_check "${BASE_URL}/s/profile/${PROFILE_USER_ID}" "GET /s/profile/{user_id}"
  echo "OK: /s/profile OG meta + og:image"
fi
if [[ -n "${CHALLENGE_ID}" ]]; then
  og_check "${BASE_URL}/s/challenge/${CHALLENGE_ID}" "GET /s/challenge/{id}"
  echo "OK: /s/challenge OG meta + og:image"
else
  echo "WARN: demo_ids missing clip_challenge_id; skipping /s/challenge OG check"
fi

START_CODE="$(curl_code GET "${BASE_URL}/start?next=%2Fhome")"
if [[ "${START_CODE}" != "200" && "${START_CODE}" != "302" ]]; then
  echo "---- GET /start ----" >&2
  cat "${body_tmp}" >&2 || true
  fail "GET /start (expected 200/302, got ${START_CODE})"
fi
echo "OK: /start deep link (${START_CODE})"

  if [[ "${DEPLOY_SMOKE_EXTENDED:-}" == "1" ]]; then
  QR_URL="${BASE_URL}/s/qr.png?next=%2Fhome&src=deploy_smoke&scale=6"
  QR_CODE="$(curl_headers_code GET "${QR_URL}")"
  expect_code "${QR_CODE}" "200" "GET /s/qr.png"
  require_header "ETag" "GET /s/qr.png"
  require_header "Cache-Control" "GET /s/qr.png"
  QR_ETAG="$(grep -i '^ETag:' "${headers_tmp}" | head -n 1 | cut -d':' -f2- | tr -d '\r' | xargs)"
  echo "OK: /s/qr.png headers"
  print_headers

  QR_304_CODE="$(curl_headers_code GET "${QR_URL}" -H "If-None-Match: ${QR_ETAG}")"
  expect_code "${QR_304_CODE}" "304" "GET /s/qr.png (If-None-Match)"
  echo "OK: /s/qr.png ETag caching (304)"

  MP4_URL="${BASE_URL}/s/clip/${REPLAY_ID}/video.mp4?start=0&end=12&fps=12&scale=1&theme=dark&aspect=9:16&captions=1"
  echo "- MP4_URL: ${MP4_URL}"
  MP4_CODE="000"
  for i in {1..30}; do
    MP4_CODE="$(curl_head_code "${MP4_URL}")"
    if [[ "${MP4_CODE}" != "404" ]]; then
      break
    fi
    sleep 2
  done
  if [[ "${MP4_CODE}" == "404" ]]; then
    echo "WARN: /s/clip/{replay_id}/video.mp4 not cached yet (404)"
  else
    expect_code_any "${MP4_CODE}" "200 307 304" "HEAD /s/clip/{replay_id}/video.mp4"
    require_header "ETag" "HEAD /s/clip/{replay_id}/video.mp4"
    require_header "Cache-Control" "HEAD /s/clip/{replay_id}/video.mp4"
    echo "OK: /s/clip/{replay_id}/video.mp4 headers"
    print_headers

    MP4_RANGE_CODE="$(curl_headers_code GET "${MP4_URL}" -H 'Range: bytes=0-1023' -L)"
    expect_code "${MP4_RANGE_CODE}" "206" "GET /s/clip/{replay_id}/video.mp4 (Range 206)"
    require_header "Accept-Ranges" "GET /s/clip/{replay_id}/video.mp4 (Range)"
    require_header "Content-Range" "GET /s/clip/{replay_id}/video.mp4 (Range)"
    echo "OK: /s/clip/{replay_id}/video.mp4 Range (206)"
    print_headers
  fi
fi

EVENT_CODE="$(curl_code POST "${BASE_URL}/api/events/track" -H "Authorization: Bearer ${ACCESS_TOKEN}" -H 'content-type: application/json' -d '{"type":"share_open","source":"deploy_smoke","meta":{"ok":true}}')"
expect_code "${EVENT_CODE}" "200" "POST /api/events/track"
echo "OK: /api/events/track"

if [[ -n "${ADMIN_TOKEN}" ]]; then
  STATUS_CODE="$(curl_code GET "${BASE_URL}/api/ops/status" -H "X-Admin-Token: ${ADMIN_TOKEN}")"
  expect_code "${STATUS_CODE}" "200" "GET /api/ops/status"
  python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
ray_ok = bool((obj.get("ray") or {}).get("ok"))
worker_ok = bool(obj.get("worker_ok") or ray_ok)
pending = int(obj.get("pending_jobs_count") or 0)
if not worker_ok:
    raise SystemExit("ops/status: worker_ok false")
print(f"pending_jobs_count={pending}")
PY
  echo "OK: /api/ops/status (admin)"
else
  echo "WARN: NEUROLEAGUE_ADMIN_TOKEN not set; skipping /api/ops/status"
fi

if [[ "${DEPLOY_SMOKE_EXTENDED:-0}" == "1" ]]; then
  echo "Extended checks: match + render_jobs"

  BP_CODE="$(curl_code POST "${BASE_URL}/api/blueprints" -H "Authorization: Bearer ${ACCESS_TOKEN}" -H 'content-type: application/json' -d '{"name":"Deploy Smoke Build","mode":"1v1"}')"
  expect_code "${BP_CODE}" "200" "POST /api/blueprints"
  BP_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("id") or ""))
PY
)"
  if [[ -z "${BP_ID}" ]]; then
    fail "blueprint id missing"
  fi

  SUBMIT_CODE="$(curl_code POST "${BASE_URL}/api/blueprints/${BP_ID}/submit" -H "Authorization: Bearer ${ACCESS_TOKEN}" -H 'content-type: application/json' -d '{}')"
  expect_code "${SUBMIT_CODE}" "200" "POST /api/blueprints/{id}/submit"

  QUEUE_CODE="$(curl_code POST "${BASE_URL}/api/ranked/queue" -H "Authorization: Bearer ${ACCESS_TOKEN}" -H 'content-type: application/json' -d "{\"blueprint_id\":\"${BP_ID}\",\"seed_set_count\":1}")"
  expect_code "${QUEUE_CODE}" "200" "POST /api/ranked/queue"
  NEW_MATCH_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("match_id") or ""))
PY
)"
  if [[ -z "${NEW_MATCH_ID}" ]]; then
    fail "match_id missing"
  fi

  NEW_REPLAY_ID=""
  for i in {1..120}; do
    M_CODE="$(curl_code GET "${BASE_URL}/api/matches/${NEW_MATCH_ID}" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
    expect_code "${M_CODE}" "200" "GET /api/matches/{match_id}"
    STATUS="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("status") or ""))
PY
)"
    if [[ "${STATUS}" == "failed" ]]; then
      cat "${body_tmp}" >&2 || true
      fail "match failed"
    fi
    if [[ "${STATUS}" == "done" ]]; then
      NEW_REPLAY_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("replay_id") or ""))
PY
)"
      break
    fi
    sleep 1
    if [[ "${i}" == "120" ]]; then
      fail "match did not complete in time"
    fi
  done

  if [[ -z "${NEW_REPLAY_ID}" ]]; then
    fail "match done but replay_id missing"
  fi

  BEST_CODE="$(curl_code POST "${BASE_URL}/api/matches/${NEW_MATCH_ID}/best_clip_jobs" -H "Authorization: Bearer ${ACCESS_TOKEN}" -H 'content-type: application/json' -d '{}')"
  expect_code "${BEST_CODE}" "200" "POST /api/matches/{match_id}/best_clip_jobs"
  THUMB_JOB_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(((obj.get("thumbnail") or {}) if isinstance(obj, dict) else {}).get("job_id") or ""))
PY
)"
  MP4_JOB_ID="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(((obj.get("vertical_mp4") or {}) if isinstance(obj, dict) else {}).get("job_id") or ""))
PY
)"
  if [[ -z "${THUMB_JOB_ID}" || -z "${MP4_JOB_ID}" ]]; then
    cat "${body_tmp}" >&2 || true
    fail "best_clip_jobs missing job ids"
  fi

  for job in "${THUMB_JOB_ID}" "${MP4_JOB_ID}"; do
    for i in {1..120}; do
      J_CODE="$(curl_code GET "${BASE_URL}/api/render_jobs/${job}" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
      expect_code "${J_CODE}" "200" "GET /api/render_jobs/{job_id}"
      J_STATUS="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("status") or ""))
PY
)"
      if [[ "${J_STATUS}" == "failed" ]]; then
        cat "${body_tmp}" >&2 || true
        fail "render job failed"
      fi
      if [[ "${J_STATUS}" == "done" ]]; then
        ART="$(python3 - "${body_tmp}" <<'PY'
import json
import sys

obj = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(str(obj.get("artifact_url") or ""))
PY
)"
        if [[ -n "${ART}" ]]; then
          A_CODE="$(curl_code GET "${BASE_URL}${ART}" -H "Authorization: Bearer ${ACCESS_TOKEN}")"
          expect_code_any "${A_CODE}" "200 307" "GET render artifact"
        fi
        break
      fi
      sleep 1
      if [[ "${i}" == "120" ]]; then
        fail "render job did not complete in time"
      fi
    done
  done

  echo "OK: render_jobs (thumbnail + mp4)"

  echo "Extended checks: share MP4 Range + kit.zip (creator pack)"

  S_CLIP_CODE="$(curl_code GET "${BASE_URL}/s/clip/${NEW_REPLAY_ID}")"
  expect_code "${S_CLIP_CODE}" "200" "GET /s/clip/{replay_id} (new match)"
  OG_URL="$(
    python3 - "${body_tmp}" <<'PY'
import re
import sys

html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'property="og:url" content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
  )"
  if [[ -z "${OG_URL}" ]]; then
    fail "new /s/clip og:url missing"
  fi
  START_S="$(python3 - <<PY
import sys
from urllib.parse import urlparse, parse_qs
u = "${OG_URL}"
q = parse_qs(urlparse(u).query)
print((q.get("start") or ["0.0"])[0])
PY
)"
  END_S="$(python3 - <<PY
import sys
from urllib.parse import urlparse, parse_qs
u = "${OG_URL}"
q = parse_qs(urlparse(u).query)
print((q.get("end") or ["12.0"])[0])
PY
)"

  MP4_URL2="${BASE_URL}/s/clip/${NEW_REPLAY_ID}/video.mp4?start=${START_S}&end=${END_S}&fps=12&scale=1&theme=dark&aspect=9:16&captions=1"
  MP4_HEAD2="$(curl_head_code "${MP4_URL2}")"
  expect_code_any "${MP4_HEAD2}" "200 307 304" "HEAD /s/clip/{replay_id}/video.mp4 (new match)"
  MP4_RANGE2="$(curl_headers_code GET "${MP4_URL2}" -H 'Range: bytes=0-1023' -L)"
  expect_code "${MP4_RANGE2}" "206" "GET /s/clip/{replay_id}/video.mp4 (new match Range 206)"

  KIT_URL="${BASE_URL}/s/clip/${NEW_REPLAY_ID}/kit.zip?start=${START_S}&end=${END_S}"
  KIT_FILE="$(mktemp)"
  KIT_CODE="$(curl -sS -L -o "${KIT_FILE}" -w '%{http_code}' "${KIT_URL}" || echo "000")"
  expect_code "${KIT_CODE}" "200" "GET /s/clip/{replay_id}/kit.zip"

  if ! command -v unzip >/dev/null 2>&1; then
    fail "unzip missing (required to validate kit.zip)"
  fi
  unzip -l "${KIT_FILE}" | grep -q 'neuroleague_best_clip_' || fail "kit.zip missing best clip mp4"
  unzip -l "${KIT_FILE}" | grep -q 'neuroleague_thumb_' || fail "kit.zip missing thumb png"
  unzip -l "${KIT_FILE}" | grep -q 'neuroleague_caption_' || fail "kit.zip missing caption txt"
  unzip -l "${KIT_FILE}" | grep -q 'neuroleague_qr_' || fail "kit.zip missing qr png"
  echo "OK: kit.zip (mp4 + thumb + caption + qr)"
  rm -f "${KIT_FILE}" || true
fi

echo "PASS"
