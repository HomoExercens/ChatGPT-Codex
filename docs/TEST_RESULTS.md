# TEST RESULTS

## Latest Results
- Timestamp: `2026-01-21T23:32:09+09:00`
- Command: `make test`
- Status: PASS (`80 passed in 9.77s`)
- Runtime: ~`13s`
- Commit: `7474b4dc24305bb065ad5f73289d1dccd4d471af`

## E2E Results (FAST)
- Timestamp: `2026-01-21T23:32:09+09:00`
- Command: `NEUROLEAGUE_E2E_FAST=1 make e2e`
- Status: PASS (`1 passed (2.7s)`)
- Runtime: ~`11s`
- Commit: `7474b4dc24305bb065ad5f73289d1dccd4d471af`

## E2E Scenarios Covered
- `apps/web/e2e/first5min.spec.ts` — guest onboarding, demo run(1st 60s), training→forge→ranked→replay, ops funnels, share landing(QR/caption/video/kit/build code), build code import→ranked, challenges flow, deploy smoke script.

## What Each Test Verifies
- `tests/test_sim_determinism.py::test_sim_determinism_digest_stable_100x` — 동일 입력을 100회 실행해도 replay digest가 변하지 않음을 검증.
- `tests/test_replay_repro.py::test_replay_repro_same_end_summary_and_digest` — replay 재생(동일 match_id/seed/spec) 시 end_summary/digest가 동일함을 검증.
- `tests/test_elo.py::test_elo_win_updates_as_expected` — Elo 승리 업데이트(K-factor 포함)가 기대값과 일치함을 검증.
- `tests/test_elo.py::test_elo_draw_no_change_when_equal` — 동 Elo에서 무승부는 delta 0(대칭)임을 검증.
- `tests/test_api_schema.py::test_openapi_contains_core_paths` — OpenAPI에 핵심 엔드포인트가 존재함을 검증.
- `tests/test_api_schema.py::test_auth_login_home_blueprints_and_match_smoke` — 로그인→홈→블루프린트→seed match 조회→highlights/analytics 응답 shape을 스모크 검증.
- `tests/test_draft_env_v15_determinism.py::test_draft_env_v15_determinism_same_seed_same_actions` — 동일 seed + 동일 action 시퀀스에서 shop offer / draft_log / 최종 blueprint spec이 동일함을 검증.
- `tests/test_to_blueprint_inference.py::test_to_blueprint_fallback_when_checkpoint_missing` — 체크포인트가 없을 때 to-blueprint가 안전하게 fallback하며 meta.note에 사유를 기록함을 검증.
- `tests/test_to_blueprint_inference.py::test_to_blueprint_policy_inference_stores_meta` — 체크포인트 정책 inference로 생성된 blueprint가 spec 검증을 통과하고 draft_log/meta가 저장됨을 검증.
- `tests/test_balance_report.py::test_balance_report_deterministic` — balance report 생성(집계/정렬)이 동일 입력에서 결정론적으로 동일함을 검증.
- `tests/test_ops_balance_api.py::test_ops_balance_latest_shape` — `/api/ops/balance/latest` 응답 shape이 기대값과 일치함을 스모크 검증.
- `tests/test_ops_metrics_api.py::test_ops_metrics_endpoints_shape` — `/api/ops/metrics/funnel_daily`(share_v1/clips_v1) + rollup endpoint shape을 검증.
- `tests/test_demo_mode.py::test_demo_presets_and_run_are_idempotent` — demo presets + demo run의 결정론/멱등(match_id/replay_id/challenge_id)이 유지됨을 검증.
- `tests/test_advisory_locks.py::test_advisory_lock_key_is_stable_and_distinct` — advisory lock key가 stable hash로 결정론적이며 서로 충돌하지 않음을 검증.
- `tests/test_alerts.py::test_alerts_funnel_drop_cooldown` — funnel drop 알림이 조건 충족 시 1회 발송되고 cooldown(2h)이 적용됨을 검증.
- `tests/test_share_landing.py::test_share_clip_video_mp4_is_cacheable_and_supports_range` — `/s/clip/{replay_id}/video.mp4` ETag/immutable cache + Range(206)을 검증.
- `tests/test_share_landing.py::test_share_build_landing_exposes_build_code_copy` — `/s/build/{blueprint_id}` build code 노출/복사를 검증.
- `tests/test_featured_rotation.py::test_featured_rotation_creates_daily_items` — scheduler featured rotation(결정론 + ops override)을 검증.
