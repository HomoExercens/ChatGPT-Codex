#!/usr/bin/env bash
set -euo pipefail

# Safe, single-VPS deploy helper (no destructive ops).
# Requirements (must be provided by the operator):
#   DEPLOY_DOMAIN
#   DEPLOY_SSH_HOST     (e.g. ubuntu@1.2.3.4)
#   DEPLOY_SSH_KEY_PATH (local path to private key)
#
# Optional:
#   DEPLOY_REPO_URL     (defaults to this repo's origin)
#   DEPLOY_REMOTE_DIR   (default: /opt/neuroleague)
#
# Notes:
# - This script does NOT run unless you execute it.
# - It will NOT create real secrets for you; if .env.deploy is missing it copies the example and stops.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

DEPLOY_DOMAIN="${DEPLOY_DOMAIN:-}"
DEPLOY_SSH_HOST="${DEPLOY_SSH_HOST:-}"
DEPLOY_SSH_KEY_PATH="${DEPLOY_SSH_KEY_PATH:-}"
DEPLOY_REMOTE_DIR="${DEPLOY_REMOTE_DIR:-/opt/neuroleague}"

if [[ -z "${DEPLOY_DOMAIN}" ]]; then
  echo "Missing DEPLOY_DOMAIN" >&2
  exit 2
fi
if [[ -z "${DEPLOY_SSH_HOST}" ]]; then
  echo "Missing DEPLOY_SSH_HOST (e.g. ubuntu@1.2.3.4)" >&2
  exit 2
fi
if [[ -z "${DEPLOY_SSH_KEY_PATH}" ]]; then
  echo "Missing DEPLOY_SSH_KEY_PATH" >&2
  exit 2
fi
if [[ ! -f "${DEPLOY_SSH_KEY_PATH}" ]]; then
  echo "SSH key not found: ${DEPLOY_SSH_KEY_PATH}" >&2
  exit 2
fi

DEPLOY_REPO_URL="${DEPLOY_REPO_URL:-}"
if [[ -z "${DEPLOY_REPO_URL}" ]]; then
  DEPLOY_REPO_URL="$(git -C "${ROOT_DIR}" config --get remote.origin.url || true)"
fi
if [[ -z "${DEPLOY_REPO_URL}" ]]; then
  echo "Missing DEPLOY_REPO_URL (could not infer from git remote)" >&2
  exit 2
fi

REMOTE_REPO_DIR="${DEPLOY_REMOTE_DIR}/repo"

ssh_opts=(
  -i "${DEPLOY_SSH_KEY_PATH}"
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=accept-new
)

echo "[deploy] host=${DEPLOY_SSH_HOST} domain=${DEPLOY_DOMAIN} repo=${DEPLOY_REPO_URL}" >&2

ssh "${ssh_opts[@]}" "${DEPLOY_SSH_HOST}" bash -lc "set -euo pipefail
  sudo mkdir -p '${DEPLOY_REMOTE_DIR}';
  sudo chown -R \"\$(id -u)\":\"\$(id -g)\" '${DEPLOY_REMOTE_DIR}';

  if [[ ! -d '${REMOTE_REPO_DIR}/.git' ]]; then
    git clone '${DEPLOY_REPO_URL}' '${REMOTE_REPO_DIR}';
  fi

  cd '${REMOTE_REPO_DIR}';
  PREV_SHA=\"\$(git rev-parse HEAD 2>/dev/null || true)\";

  git fetch origin;
  git checkout main;
  git pull --ff-only origin main;

  if [[ ! -f .env.deploy ]]; then
    cp .env.deploy.example .env.deploy;
    chmod 600 .env.deploy || true;
    echo '[deploy] Created .env.deploy from template. Edit secrets + domain, then re-run.' >&2;
    exit 3;
  fi

  # Basic lint: ensure DEPLOY_DOMAIN matches.
  if ! grep -qE '^DEPLOY_DOMAIN=' .env.deploy >/dev/null 2>&1; then
    echo '[deploy] .env.deploy missing DEPLOY_DOMAIN=...' >&2;
    exit 3;
  fi
  WANT_DOMAIN='${DEPLOY_DOMAIN}';
  GOT_DOMAIN=\"\$(grep -E '^DEPLOY_DOMAIN=' .env.deploy | tail -n 1 | cut -d= -f2- | tr -d '\\r' || true)\";
  if [[ -n \"\${WANT_DOMAIN}\" && -n \"\${GOT_DOMAIN}\" && \"\${WANT_DOMAIN}\" != \"\${GOT_DOMAIN}\" ]]; then
    echo \"[deploy] .env.deploy DEPLOY_DOMAIN mismatch (want=\${WANT_DOMAIN}, got=\${GOT_DOMAIN})\" >&2;
    echo '[deploy] Edit .env.deploy (server-only) then re-run.' >&2;
    exit 3;
  fi
  if ! grep -qE '^CADDY_ACME_CA=' .env.deploy >/dev/null 2>&1; then
    echo '[deploy] note: CADDY_ACME_CA not set → default is production Let\\x27s Encrypt (rate limits may apply).' >&2;
    echo '[deploy] rehearsal hint: set CADDY_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory' >&2;
  fi

  docker compose -f docker-compose.deploy.yml --env-file .env.deploy pull || true;

  if ! docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build; then
    echo '[deploy] compose up failed' >&2;
    if [[ -n \"\${PREV_SHA}\" ]]; then
      echo \"[deploy] rollback hint: git checkout \${PREV_SHA} && docker compose ... up -d --build\" >&2;
    fi
    exit 4;
  fi

  # Smoke: wait for /api/ready via Caddy.
  READY_OK='0';
  for i in \$(seq 1 60); do
    if curl -fsS 'http://127.0.0.1/api/ready' >/dev/null 2>&1; then
      READY_OK='1';
      break;
    fi
    sleep 2;
  done

  if [[ \"\${READY_OK}\" != '1' ]]; then
    echo '[deploy] ready: TIMEOUT' >&2;
    docker compose -f docker-compose.deploy.yml --env-file .env.deploy ps >&2 || true;
    docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs --tail=200 api >&2 || true;
    exit 5;
  fi
  echo '[deploy] ready: OK' >&2;

  # Extended smoke (no admin token required).
  smoke_fail() {
    echo \"[deploy] smoke: FAIL - \${1}\" >&2;
    docker compose -f docker-compose.deploy.yml --env-file .env.deploy ps >&2 || true;
    docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs --tail=200 caddy >&2 || true;
    docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs --tail=200 api >&2 || true;
    if [[ -n \"\${PREV_SHA}\" ]]; then
      echo \"[deploy] rollback hint: git checkout \${PREV_SHA} && docker compose ... up -d --build\" >&2;
    fi
    exit 6;
  }

  if ! curl -fsS 'http://127.0.0.1/' >/dev/null 2>&1; then
    smoke_fail 'GET / failed';
  fi
  if ! curl -fsS 'http://127.0.0.1/playtest' >/dev/null 2>&1; then
    smoke_fail 'GET /playtest failed';
  fi
  OPS_CODE=\"\$(curl -sS -o /dev/null -w '%{http_code}' 'http://127.0.0.1/api/ops/status' || echo 000)\";
  if [[ \"\${OPS_CODE}\" != '401' ]]; then
    smoke_fail \"/api/ops/status expected 401 (locked), got \${OPS_CODE}\";
  fi

  DEMO_REPLAY_ID=\"\$(curl -fsS 'http://127.0.0.1/api/assets/ops/demo_ids.json' | python3 -c 'import json,sys;print(json.load(sys.stdin).get(\"clip_replay_id\",\"\"))' || true)\";
  if [[ -z \"\${DEMO_REPLAY_ID}\" ]]; then
    smoke_fail 'missing demo_ids.json clip_replay_id (seed not run?)';
  fi
  OG_HTML=\"\$(curl -fsS \"http://127.0.0.1/s/clip/\${DEMO_REPLAY_ID}?start=0.0&end=2.0&v=1\" || true)\";
  if ! echo \"\${OG_HTML}\" | grep -q 'property=\"og:image\"'; then
    smoke_fail 'OG missing og:image';
  fi
  OG_IMAGE_URL=\"\$(python3 - <<'PY'
import re,sys
html=sys.stdin.read()
m=re.search(r'property=\"og:image\" content=\"([^\"]+)\"', html)
print(m.group(1) if m else '')
PY
<<<\"\${OG_HTML}\")\";
  if [[ -z \"\${OG_IMAGE_URL}\" ]]; then
    smoke_fail 'og:image empty';
  fi
  OG_PATH=\"\$(python3 - <<'PY'
import sys
from urllib.parse import urlparse
u=sys.stdin.read().strip()
p=urlparse(u)
path=p.path or ''
if p.query:
  path += '?' + p.query
print(path)
PY
<<<\"\${OG_IMAGE_URL}\")\";
  if [[ -z \"\${OG_PATH}\" ]]; then
    smoke_fail 'og:image path parse failed';
  fi
  IMG_CODE=\"\$(curl -sS -o /dev/null -w '%{http_code}' \"http://127.0.0.1\${OG_PATH}\" || echo 000)\";
  if [[ \"\${IMG_CODE}\" != '200' && \"\${IMG_CODE}\" != '307' ]]; then
    smoke_fail \"og:image expected 200/307 (never-404), got \${IMG_CODE}\";
  fi
  echo '[deploy] smoke: OK' >&2;
  exit 0;
"

echo "[deploy] done" >&2
