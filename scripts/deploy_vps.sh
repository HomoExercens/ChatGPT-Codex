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

  docker compose -f docker-compose.deploy.yml --env-file .env.deploy pull || true;

  if ! docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build; then
    echo '[deploy] compose up failed' >&2;
    if [[ -n \"\${PREV_SHA}\" ]]; then
      echo \"[deploy] rollback hint: git checkout \${PREV_SHA} && docker compose ... up -d --build\" >&2;
    fi
    exit 4;
  fi

  # Smoke: wait for /api/ready via Caddy.
  for i in \$(seq 1 60); do
    if curl -fsS 'http://127.0.0.1/api/ready' >/dev/null 2>&1; then
      echo '[deploy] ready: OK' >&2;
      exit 0;
    fi
    sleep 2;
  done

  echo '[deploy] ready: TIMEOUT' >&2;
  docker compose -f docker-compose.deploy.yml --env-file .env.deploy ps >&2 || true;
  docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs --tail=200 api >&2 || true;
  exit 5;
"

echo "[deploy] done" >&2
