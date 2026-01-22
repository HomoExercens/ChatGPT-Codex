#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT_DIR}/.venv"

if [[ -d "${VENV}" && ! -x "${VENV}/bin/pip" ]]; then
  echo "Detected broken venv (missing pip). Recreating ${VENV}..." >&2
  rm -rf "${VENV}"
fi

if [[ ! -d "${VENV}" ]]; then
  if python3 -m venv "${VENV}" 2>/dev/null; then
    :
  else
    echo "python3 -m venv unavailable; bootstrapping via virtualenv.pyz" >&2
    TMP_DIR="$(mktemp -d)"
    curl -sS https://bootstrap.pypa.io/virtualenv.pyz -o "${TMP_DIR}/virtualenv.pyz"
    python3 "${TMP_DIR}/virtualenv.pyz" "${VENV}"
  fi
fi

"${VENV}/bin/python" -m pip install --upgrade pip >/dev/null
"${VENV}/bin/pip" install -r "${ROOT_DIR}/requirements.txt"

if [[ -f "${ROOT_DIR}/apps/web/package.json" ]]; then
  if [[ ! -d "${ROOT_DIR}/apps/web/node_modules" ]]; then
    (cd "${ROOT_DIR}/apps/web" && npm install)
  fi
fi
