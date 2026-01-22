#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SOURCE="/home/clutch/cursor-workspace/cursor/뉴로리그/"
DEST="${ROOT_DIR}/ui/"

mkdir -p "${DEST}"

tmp_out="$(mktemp)"
trap 'rm -f "${tmp_out}"' EXIT

rsync -a --delete --itemize-changes \
  --exclude 'ui' \
  --include '.env.local' \
  --include '.gitignore' \
  --include 'App.tsx' \
  --include 'README.md' \
  --include 'components/***' \
  --include 'lib/***' \
  --include 'views/***' \
  --include 'constants.ts' \
  --include 'index.html' \
  --include 'index.tsx' \
  --include 'metadata.json' \
  --include 'package.json' \
  --include 'tsconfig.json' \
  --include 'types.ts' \
  --include 'vite.config.ts' \
  --exclude '*' \
  "${SOURCE}" "${DEST}" | tee "${tmp_out}" >/dev/null

if command -v rg >/dev/null 2>&1; then
  transferred_files="$(rg -c '^>f' "${tmp_out}" || echo 0)"
  created_files="$(rg -c '^>f\\+\\+\\+\\+\\+\\+\\+\\+\\+' "${tmp_out}" || echo 0)"
  deleted_entries="$(rg -c '^\\*deleting ' "${tmp_out}" || echo 0)"
else
  transferred_files="$(grep -cE '^>f' "${tmp_out}" || echo 0)"
  created_files="$(grep -cE '^>f\\+\\+\\+\\+\\+\\+\\+\\+\\+' "${tmp_out}" || echo 0)"
  deleted_entries="$(grep -cE '^\\*deleting ' "${tmp_out}" || echo 0)"
fi
updated_files="$((transferred_files - created_files))"
total_changes="$((created_files + updated_files + deleted_entries))"

echo "UI sync complete."
echo "  Source: ${SOURCE}"
echo "  Dest:   ${DEST}"
echo "  New files:            ${created_files}"
echo "  Updated files:        ${updated_files}"
echo "  Deleted entries:      ${deleted_entries}"
echo "  Total changes:        ${total_changes}"
