#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "${ROOT_DIR}"

need_cmd() {
  if ! command -v "${1}" >/dev/null 2>&1; then
    echo "Missing required command: ${1}" >&2
    exit 1
  fi
}

need_cmd git
need_cmd unzip
need_cmd date
need_cmd python3
need_cmd rg

HAVE_ZIP=0
if command -v zip >/dev/null 2>&1; then
  HAVE_ZIP=1
fi

zip_update() {
  local zip_path="${1}"
  shift

  if [[ "$#" -eq 0 ]]; then
    return 0
  fi

  if [[ "${HAVE_ZIP}" == "1" ]]; then
    zip -ur "${zip_path}" "$@" >/dev/null
    return 0
  fi

  python3 - "$zip_path" "$@" <<'PY'
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path


def add_path(zf: zipfile.ZipFile, p: Path) -> None:
    if p.is_dir():
        for root, _, files in os.walk(p):
            root_path = Path(root)
            for filename in files:
                file_path = root_path / filename
                zf.write(file_path, arcname=file_path.as_posix())
        return
    if p.is_file():
        zf.write(p, arcname=p.as_posix())


zip_path = Path(sys.argv[1])
paths = [Path(arg) for arg in sys.argv[2:]]

replace_files: set[str] = set()
replace_prefixes: list[str] = []
for p in paths:
    p_posix = p.as_posix().rstrip("/")
    if p_posix == ".":
        continue
    if p.is_dir():
        replace_prefixes.append(p_posix + "/")
    else:
        replace_files.add(p_posix)

tmp_path = zip_path.with_suffix(zip_path.suffix + ".tmp")

with zipfile.ZipFile(zip_path, mode="r") as src, zipfile.ZipFile(
    tmp_path, mode="w", compression=zipfile.ZIP_DEFLATED
) as dst:
    for info in src.infolist():
        name = info.filename
        if name in replace_files:
            continue
        if any(name.startswith(prefix) for prefix in replace_prefixes):
            continue
        dst.writestr(info, src.read(name))

    for p in paths:
        if not p.exists():
            continue
        add_path(dst, p)

tmp_path.replace(zip_path)
PY
}

TEST_TMP="$(mktemp)"
E2E_TMP="$(mktemp)"
trap 'rm -f "${TEST_TMP}" "${E2E_TMP}"' EXIT

TEST_START_EPOCH="$(date +%s)"
if make test 2>&1 | tee "${TEST_TMP}"; then
  TEST_STATUS="PASS"
else
  TEST_STATUS="FAIL"
  exit 1
fi
TEST_END_EPOCH="$(date +%s)"
TEST_RUNTIME_SEC="$((TEST_END_EPOCH - TEST_START_EPOCH))"
TEST_SUMMARY="$(rg -o "\\d+ passed.*" "${TEST_TMP}" | tail -n 1 || true)"

E2E_START_EPOCH="$(date +%s)"
if NEUROLEAGUE_E2E_FAST=1 make e2e 2>&1 | tee "${E2E_TMP}"; then
  E2E_STATUS="PASS"
else
  E2E_STATUS="FAIL"
  exit 1
fi
E2E_END_EPOCH="$(date +%s)"
E2E_RUNTIME_SEC="$((E2E_END_EPOCH - E2E_START_EPOCH))"
E2E_SUMMARY="$(rg -o "\\d+ passed.*" "${E2E_TMP}" | tail -n 1 || true)"

# E2E deletes screenshots; regenerate non-e2e artifacts expected in the handoff bundle.
if [[ -f "${ROOT_DIR}/scripts/capture_steam_assets_tree_png.py" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/capture_steam_assets_tree_png.py" >/dev/null
  else
    python3 "${ROOT_DIR}/scripts/capture_steam_assets_tree_png.py" >/dev/null
  fi
fi

HEAD_SHA="$(git rev-parse HEAD)"
LOG5="$(git log -5 --oneline)"
LAST_TAG="$(git tag --list "handoff/*" --sort=-creatordate | head -n 1 || true)"
if [[ -n "${LAST_TAG}" ]]; then
  BASE="${LAST_TAG}"
else
  BASE="$(git rev-list --max-parents=0 HEAD)"
fi

DIFF_NAMES="$(git diff --name-only "${BASE}"..HEAD || true)"
DIFF_STAT="$(git diff --stat "${BASE}"..HEAD || true)"

mkdir -p docs

NOW_ISO="$(date -Iseconds)"

NOW_ISO="${NOW_ISO}" HEAD_SHA="${HEAD_SHA}" LAST_TAG="${LAST_TAG}" BASE="${BASE}" LOG5="${LOG5}" DIFF_NAMES="${DIFF_NAMES}" DIFF_STAT="${DIFF_STAT}" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

now = os.environ["NOW_ISO"]
head_sha = os.environ["HEAD_SHA"]
last_tag = os.environ.get("LAST_TAG", "")
base = os.environ["BASE"]
log5 = os.environ.get("LOG5", "").splitlines()
diff_names = [line for line in os.environ.get("DIFF_NAMES", "").splitlines() if line.strip()]
diff_stat = os.environ.get("DIFF_STAT", "")

path = Path("docs/HANDOFF.json")
existing: dict = {}
if path.exists():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    except Exception:
        existing = {}

existing["timestamp"] = now
existing["git_head"] = head_sha
existing["last_handoff_tag"] = last_tag or None
existing["base"] = base
existing["recent_commits"] = log5
existing["changed_files_since_base"] = diff_names
existing["diff_stat_since_base"] = diff_stat

commands = existing.get("commands") if isinstance(existing.get("commands"), dict) else {}
commands.update(
    {
        "dev": "make dev",
        "test": "make test",
        "e2e": "make e2e",
        "handoff": "make handoff",
        "balance_report": "make balance-report",
    }
)
existing["commands"] = commands

path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

cat > docs/TEST_RESULTS.md <<EOF
# TEST RESULTS

## Latest Results
- Timestamp: \`${NOW_ISO}\`
- Command: \`make test\`
- Status: ${TEST_STATUS}${TEST_SUMMARY:+ (\`${TEST_SUMMARY}\`)}
- Runtime: ~\`${TEST_RUNTIME_SEC}s\`
- Commit: \`${HEAD_SHA}\`

## E2E Results (FAST)
- Timestamp: \`${NOW_ISO}\`
- Command: \`NEUROLEAGUE_E2E_FAST=1 make e2e\`
- Status: ${E2E_STATUS}${E2E_SUMMARY:+ (\`${E2E_SUMMARY}\`)}
- Runtime: ~\`${E2E_RUNTIME_SEC}s\`
- Commit: \`${HEAD_SHA}\`

## E2E Scenarios Covered
- \`apps/web/e2e/first5min.spec.ts\` — guest onboarding, demo run(1st 60s), training→forge→ranked→replay, ops funnels, share landing(QR/caption/video/kit/build code), build code import→ranked, challenges flow, deploy smoke script.

## What Each Test Verifies
- \`tests/test_sim_determinism.py::test_sim_determinism_digest_stable_100x\` — 동일 입력을 100회 실행해도 replay digest가 변하지 않음을 검증.
- \`tests/test_replay_repro.py::test_replay_repro_same_end_summary_and_digest\` — replay 재생(동일 match_id/seed/spec) 시 end_summary/digest가 동일함을 검증.
- \`tests/test_elo.py::test_elo_win_updates_as_expected\` — Elo 승리 업데이트(K-factor 포함)가 기대값과 일치함을 검증.
- \`tests/test_elo.py::test_elo_draw_no_change_when_equal\` — 동 Elo에서 무승부는 delta 0(대칭)임을 검증.
- \`tests/test_api_schema.py::test_openapi_contains_core_paths\` — OpenAPI에 핵심 엔드포인트가 존재함을 검증.
- \`tests/test_api_schema.py::test_auth_login_home_blueprints_and_match_smoke\` — 로그인→홈→블루프린트→seed match 조회→highlights/analytics 응답 shape을 스모크 검증.
- \`tests/test_draft_env_v15_determinism.py::test_draft_env_v15_determinism_same_seed_same_actions\` — 동일 seed + 동일 action 시퀀스에서 shop offer / draft_log / 최종 blueprint spec이 동일함을 검증.
- \`tests/test_to_blueprint_inference.py::test_to_blueprint_fallback_when_checkpoint_missing\` — 체크포인트가 없을 때 to-blueprint가 안전하게 fallback하며 meta.note에 사유를 기록함을 검증.
- \`tests/test_to_blueprint_inference.py::test_to_blueprint_policy_inference_stores_meta\` — 체크포인트 정책 inference로 생성된 blueprint가 spec 검증을 통과하고 draft_log/meta가 저장됨을 검증.
- \`tests/test_balance_report.py::test_balance_report_deterministic\` — balance report 생성(집계/정렬)이 동일 입력에서 결정론적으로 동일함을 검증.
- \`tests/test_ops_balance_api.py::test_ops_balance_latest_shape\` — \`/api/ops/balance/latest\` 응답 shape이 기대값과 일치함을 스모크 검증.
- \`tests/test_ops_metrics_api.py::test_ops_metrics_endpoints_shape\` — \`/api/ops/metrics/funnel_daily\`(share_v1/clips_v1) + rollup endpoint shape을 검증.
- \`tests/test_demo_mode.py::test_demo_presets_and_run_are_idempotent\` — demo presets + demo run의 결정론/멱등(match_id/replay_id/challenge_id)이 유지됨을 검증.
- \`tests/test_advisory_locks.py::test_advisory_lock_key_is_stable_and_distinct\` — advisory lock key가 stable hash로 결정론적이며 서로 충돌하지 않음을 검증.
- \`tests/test_alerts.py::test_alerts_funnel_drop_cooldown\` — funnel drop 알림이 조건 충족 시 1회 발송되고 cooldown(2h)이 적용됨을 검증.
- \`tests/test_share_landing.py::test_share_clip_video_mp4_is_cacheable_and_supports_range\` — \`/s/clip/{replay_id}/video.mp4\` ETag/immutable cache + Range(206)을 검증.
- \`tests/test_share_landing.py::test_share_build_landing_exposes_build_code_copy\` — \`/s/build/{blueprint_id}\` build code 노출/복사를 검증.
- \`tests/test_featured_rotation.py::test_featured_rotation_creates_daily_items\` — scheduler featured rotation(결정론 + ops override)을 검증.
EOF

if [[ ! -f docs/QA_CHECKLIST.md ]]; then
  cat > docs/QA_CHECKLIST.md <<EOF
# QA CHECKLIST

- (Autogenerated placeholder) Add manual QA items here.
EOF
fi

if [[ ! -f docs/ARCHITECTURE_NOTES.md ]]; then
  cat > docs/ARCHITECTURE_NOTES.md <<EOF
# ARCHITECTURE NOTES

- (Autogenerated placeholder) Add architecture notes here.
EOF
fi

if [[ ! -f docs/HANDOFF_REPORT.md ]]; then
  cat > docs/HANDOFF_REPORT.md <<EOF
# HANDOFF REPORT

EOF
fi

cat >> docs/HANDOFF_REPORT.md <<EOF

## Automated Snapshot
- Timestamp: \`${NOW_ISO}\`
- Git: \`${HEAD_SHA}\`
- Recent commits:
$(printf "%s\n" "${LOG5}" | sed 's/^/- /')
- Last handoff tag: \`${LAST_TAG:-none}\`
- Base for diff: \`${BASE}\`
- Changed files since base:
$(printf "%s\n" "${DIFF_NAMES:-}" | sed 's/^/- /' || true)
- Diff stat since base:
\`\`\`
${DIFF_STAT:-}
\`\`\`
EOF

mkdir -p artifacts/handoff
TS="$(date +"%Y%m%d_%H%M%S")"
OUT_REL="artifacts/handoff/neuroleague_handoff_bundle_${TS}.zip"

git archive --format=zip --output "${OUT_REL}" HEAD

EXTRA_PATHS=(docs/HANDOFF_REPORT.md docs/QA_CHECKLIST.md docs/TEST_RESULTS.md docs/HANDOFF.json docs/ARCHITECTURE_NOTES.md)
[[ -d ui ]] && EXTRA_PATHS+=(ui)
[[ -d docs/screenshots ]] && EXTRA_PATHS+=(docs/screenshots)
[[ -d artifacts/replays ]] && EXTRA_PATHS+=(artifacts/replays)
[[ -d artifacts/replay ]] && EXTRA_PATHS+=(artifacts/replay)
[[ -d artifacts/sharecards ]] && EXTRA_PATHS+=(artifacts/sharecards)
[[ -d artifacts/clips ]] && EXTRA_PATHS+=(artifacts/clips)
[[ -d artifacts/ops ]] && EXTRA_PATHS+=(artifacts/ops)

# Ensure required handoff docs + non-tracked artifacts exist in the zip.
zip_update "${OUT_REL}" "${EXTRA_PATHS[@]}"

git tag -a "handoff/${TS}" -m "handoff ${TS}"

OUT_ABS="$(pwd -P)/${OUT_REL}"
UNC="\\\\wsl$\\Ubuntu$(pwd -P | sed 's|/|\\\\|g')\\\\${OUT_REL//\//\\\\}"

unzip -l "${OUT_REL}" | head -n 40 || true
echo "HANDOFF_ZIP_READY: ${OUT_ABS} | ${UNC}"
