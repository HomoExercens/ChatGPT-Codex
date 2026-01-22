#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OUT_DIR="${ROOT_DIR}/artifacts/steam_assets"
OUT_FILE="${OUT_DIR}/trailer_teaser.mp4"

mkdir -p "${OUT_DIR}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[make_trailer_teaser] ffmpeg not found; skipping (install ffmpeg to generate a trailer)."
  exit 0
fi

mapfile -t INPUTS < <(ls -1 "${ROOT_DIR}/artifacts/clips/mp4/"*.mp4 2>/dev/null | sort | head -n 5 || true)
if [[ ${#INPUTS[@]} -eq 0 ]]; then
  echo "[make_trailer_teaser] no inputs under artifacts/clips/mp4; skipping."
  exit 0
fi

TMP_LIST="$(mktemp)"
cleanup() { rm -f "${TMP_LIST}"; }
trap cleanup EXIT

for f in "${INPUTS[@]}"; do
  printf "file '%s'\n" "${f}" >> "${TMP_LIST}"
done

echo "[make_trailer_teaser] inputs:"
printf "  - %s\n" "${INPUTS[@]}"

# Output: 1280x720 (16:9) letterbox, re-encoded for broad compatibility.
ffmpeg -hide_banner -y \
  -f concat -safe 0 -i "${TMP_LIST}" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black" \
  -r 30 \
  -c:v libx264 -crf 22 -preset veryfast \
  -pix_fmt yuv420p \
  -an \
  "${OUT_FILE}"

echo "[make_trailer_teaser] wrote: ${OUT_FILE}"

