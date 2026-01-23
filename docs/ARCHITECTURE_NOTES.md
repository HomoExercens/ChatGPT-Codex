# ARCHITECTURE NOTES — NeuroLeague Prototype

## Monorepo Layout
- `apps/web` — React + TS + Vite + Tailwind, React Router, TanStack Query, Zustand
- `services/api` — FastAPI, SQLAlchemy 2.x, Alembic, SQLite, Ray job orchestration
- `packages/sim` — 결정론 시뮬레이터 + replay 포맷 + highlights
- `packages/rl` — PettingZoo ParallelEnv + RLlib PPO(로컬 CPU)
- `packages/shared` — (v1) 공용 경로만 설정
- `artifacts/` — SQLite DB + replay JSON + 모델 체크포인트 저장
- `ui/` — UI 산출물 복사본(원본은 루트 경로, 동기화는 `scripts/sync_ui.sh`)

## Data Flow (End-to-End)
1. Web: 로그인(`POST /api/auth/guest` 또는 `/api/auth/login`) → JWT 토큰을 클라이언트에 저장
2. Web: Training → 체크포인트 → Blueprint 변환(정책 inference)
   - `POST /api/training/runs`로 Run 생성/시작(모드별)
   - `POST /api/training/runs/{run_id}/to-blueprint`가 체크포인트 정책으로 draft를 결정론적으로 실행 → blueprint 생성
   - blueprint에는 `meta_json.draft_log`/`draft_seed` 등이 저장되어 Forge에서 “Draft Summary”로 확인 가능
3. Web: Blueprint CRUD/검증/제출
   - `GET/POST/PUT /api/blueprints`
   - `POST /api/blueprints/{id}/validate`
   - `POST /api/blueprints/{id}/submit`
4. Web: Ranked 큐(비동기, PvP 우선)
   - `POST /api/ranked/queue` (wrapper) 또는 `POST /api/matches/queue` → 즉시 `match_id` 반환(status=queued)
5. API: Ray 비동기 match job 실행
   - `ranked_match_job`이 seed_set_count 만큼 sim → 다수결 승패 → Elo 업데이트 → replay 저장
   - 진행상태/에러는 `matches.status/progress/error_message`로 DB에 기록
6. Web: Match 폴링 + Replay viewer
   - `GET /api/matches/{match_id}`로 status/progress/replay_id를 폴링
   - `GET /api/matches/{match_id}/replay`로 replay payload(timeline_events, highlights, digest) 수신
7. Web: 모드 분리(1v1 / team)
   - `GET /api/matches?mode=...` 및 `GET /api/analytics/*?mode=...`로 Elo/히스토리/분석이 모드별로 분리됨

## Draft Economy v1.5 + Checkpoint Inference
- Draft env: `packages/rl/neuroleague_rl/env.py` (`neuroleague_draft_parallel_v15`)
  - action: buy(0..5), pass(6), reroll(7), level_up(8)
  - rarity 기반 tiered shop + reroll/level-up 경제 규칙을 포함
  - episode 종료 시 `infos.draft_spec_*` + `infos.draft_log_*`를 반환(작게, JSON-serializable)
- to-blueprint(정책 기반):
  - API: `services/api/neuroleague_api/routers/training.py`에서 체크포인트를 로드하고 `packages/rl/neuroleague_rl/infer.py`로 결정론적 draft inference 수행
  - seed: `(run_id, checkpoint_id, mode)` 기반 sha256 → u64
  - 실패/구버전 체크포인트는 fallback deterministic blueprint로 안전하게 전환(`meta_json.note`)

## Determinism / Seeds / Replay
- 시뮬 entry: `packages/sim/neuroleague_sim/simulate.py#simulate_match`
- RNG: `packages/sim/neuroleague_sim/rng.py#derive_seed`
  - 입력: `(match_id, seed_index)` → `sha256` 기반 seed → NumPy RNG 단일 스트림
- Replay 초기 스냅샷:
  - `ReplayHeader.units`에 유닛 메타(formation_slot/max_hp/tags/items 등)를 포함해 프론트가 RNG 없이 전투 상태를 복원
- Replay digest:
  - `packages/sim/neuroleague_sim/canonical.py`의 canonical JSON + sha256
  - digest 대상: `header + timeline_events + end_summary + highlights`
- Replay 저장:
  - API가 저장한 JSON은 `services/api/neuroleague_api/storage.py#save_replay_json`로 저장하며, DB에는 stable key(`replays/<id>.json`)를 `replays.artifact_path`에 보관
  - 레거시(absolute path)도 `load_replay_json`에서 계속 로드 가능하도록 호환 처리

## Storage Backend (LocalFS default, S3-ready)
- Backend: `services/api/neuroleague_api/storage_backend.py`
  - `LocalFSBackend`(default): `NEUROLEAGUE_ARTIFACTS_DIR` 하위에 key 기반으로 저장
  - `S3Backend`(optional): env 기반(설정 시 boto3 필요)
- Public assets: `GET /api/assets/{key:path}` (allowlist: `clips/`, `sharecards/`, `ops/`)
  - 공유/클립/리포트 등 “공개 가능 자산”만 서빙하도록 제한(DB 파일 노출 방지)

## Synergy Tiers (2/4/6) + Amplifiers (Sigils)
- 시너지 tier:
  - `packages/sim/neuroleague_sim/simulate.py`는 태그별 count를 계산한 뒤 `2/4/6` 중 `count 이하의 최대 threshold`를 적용
  - `SYNERGY_TRIGGER` 이벤트 payload에 `team/tag/count/threshold`를 포함해 관전/분석에서 tier를 명시
- Sigil(시너지 카운트 보너스):
  - `packages/sim/neuroleague_sim/catalog.py`의 일부 Utility 아이템은 `synergy_bonus: {tag: +N}`을 보유
  - 팀 태그 count 계산 시 `base tags + equipped items synergy_bonus`를 합산하여 3v3에서도 T4/T6에 도달 가능
  - `SYNERGY_TRIGGER` payload에 `base_count/bonus/bonus_breakdown`을 포함해 “왜 tier가 올라갔는지” 설명 가능

## Sharecard (PNG)
- 생성/제공:
  - (권장) Job 기반:
    - `POST /api/matches/{match_id}/sharecard_jobs` → `{job_id}`
    - `GET /api/render_jobs/{job_id}` 폴링 → `artifact_url` 다운로드
  - (호환) Sync GET:
    - `GET /api/replays/{replay_id}/sharecard` → 캐시 hit 시 즉시 반환
    - 캐시 miss 시 기본은 `202 + job_id`(단, `async=0`이면 동기 렌더 시도)
  - 캐시 위치: `artifacts/sharecards/`
  - 렌더러: `apps/web/scripts/render_sharecard.mjs` (Playwright Chromium)
  - E2E fast-path: `NEUROLEAGUE_E2E_FAST=1`에서 sharecard는 안정성을 위해 v1(Pillow) fallback을 기본으로 사용

## Highlights Pipeline
- 생성: `packages/sim/neuroleague_sim/highlights.py#generate_highlights`
  - 이벤트 기반(죽음/폭딜/HP 스윙/시너지)
  - Top3 + non-overlap(min gap) + tags(unit/creature/item/synergy)
- 제공:
  - `/api/matches/{match_id}`에 replay payload의 `highlights` 포함
  - `/api/matches/{match_id}/highlights`는 저장된 highlights만 반환

## Ranked PvP Matchmaking (Elo-Near)
- 제출된 청사진 풀:
  - `blueprints.status == "submitted"`이며 `blueprints.submitted_at`이 최신인 “사용자별 1개”를 후보로 사용
- 상대 선택:
  - 본인 Elo와 후보 Elo의 차이를 기준으로 top-K(예: 5~10)에서 `sha256(match_id)`로 결정론적으로 선택
  - 후보가 없으면 deterministic bot fallback
- 응답 shape:
  - match row/detail에 `opponent_type`(`human|bot`) + `opponent_elo` 포함(프론트에서 배지로 표기)

## Ray Jobs / Training Polling
- Training task: `services/api/neuroleague_api/ray_tasks.py#training_job` (max_retries=0)
  - worker 환경: `CUDA_VISIBLE_DEVICES=""`, DB/artifacts 경로를 env로 전달
  - 매 iteration마다:
    - RLlib `algo.train()` 실행
    - `training_runs.progress/metrics_json` 업데이트
    - `checkpoints` row + checkpoint artifact_path 저장
- 상태 폴링:
  - API `GET /api/training/runs/{run_id}`에서 `_maybe_refresh_ray_status` 호출
  - 저장된 `ray_job_id`(ObjectRef hex)로 `ray.wait` → 완료/예외 감지 → 실패 상태로 DB 반영
- E2E fast-path:
  - `NEUROLEAGUE_E2E_FAST=1`에서 training iteration을 1로 낮춰 E2E 실행 시간을 단축

## Analytics Coach
- 추천 카드: `GET /api/analytics/coach?mode=...`에서 3개 추천(약점 매치업 / 아이템·시너지 교체 / 라인업 제안)과 근거(승률/표본/CTA)를 반환

## Clip Export (Thumbnail / WebM / GIF)
- API:
  - (권장) Job 기반:
    - `POST /api/replays/{replay_id}/thumbnail_jobs`
    - `POST /api/replays/{replay_id}/clip_jobs`
    - `GET /api/render_jobs/{job_id}` 폴링 → `artifact_url` 다운로드/프리뷰
  - (호환) Sync GET:
    - `GET /api/replays/{replay_id}/thumbnail?start=...&end=...`
    - `GET /api/replays/{replay_id}/clip?start=...&end=...&format=gif|webm`
    - 캐시 miss 시 기본은 `202 + job_id`(단, `async=0`이면 동기 렌더 시도)
- Renderer:
  - `services/api/neuroleague_api/clip_render.py`에서 replay header + timeline events로 HP state를 재구성하고 Pillow로 프레임을 결정론적으로 렌더
  - WebM은 `imageio-ffmpeg`의 ffmpeg 바이너리로 인코딩(동일 입력 → 동일 바이트)
- Cache:
  - key: `(replay.digest + params)` sha256
  - 저장: `artifacts/clips/` 하위(thumbnails/gif/webm)

## Render Jobs (Clip/Thumbnail/Sharecard)
- DB: `render_jobs` 테이블이 asset 생성 작업을 추적(queued/running/done/failed + progress + artifact_path)
- API:
  - `GET /api/render_jobs/{job_id}` → status/progress/artifact_url/error_message 반환
- 실행:
  - 기본은 Ray task로 백그라운드 렌더(캐시 miss 시 202 + job_id → 폴링)
  - E2E fast-path(`NEUROLEAGUE_E2E_FAST=1`)에서는 같은 엔드포인트를 “동기 실행”으로 처리해 Ray 의존을 회피
- 캐시 재사용:
  - cache_key는 `replay.digest + params` 기반 sha256로 고정(동일 입력 → 동일 파일 재사용)

## Public Share Landing (/s/*)
- 목적: SNS/메신저 미리보기(OG/Twitter meta)는 SPA JS 실행이 없으므로 서버 렌더 HTML을 제공
- 엔드포인트:
  - `GET /s/clip/{replay_id}?start=&end=` → text/html (OG meta 포함) + “앱에서 보기” CTA
  - `GET /s/clip/{replay_id}/thumb.png?...` → `never 404`(캐시 없으면 placeholder)로 OG image 안정성 확보
  - `GET /s/qr.png?next=...` → `/start?next=...`로 바로 진입하는 QR PNG(결정론적 content, ETag + immutable 캐시)
- Share Kit:
  - 서버 렌더 share page에 QR + “Copy App Link / Copy Caption / Copy for Discord”
  - 캡션 생성은 `services/api/neuroleague_api/share_caption.py`(versioned)
- 절대 URL:
  - `NEUROLEAGUE_PUBLIC_BASE_URL`가 설정되어 있으면 이를 최우선으로 사용(리버스 프록시/HTTPS 뒤에서도 링크가 정확)
  - 없으면 `request.base_url` 기반으로 fallback(로컬에서도 동작)
  - 프록시 환경에서는 `NEUROLEAGUE_TRUST_PROXY_HEADERS=true`로 `X-Forwarded-*`를 신뢰하도록 설정하며, `NEUROLEAGUE_ALLOWED_HOSTS`로 Host allowlist를 함께 적용

## PvP Guardrails (Anti‑Abuse)
- Submit cooldown:
  - `POST /api/blueprints/{id}/submit`은 `(user, mode, ruleset)` 기준으로 cooldown을 적용(기본 120s)
  - 위반 시 `429 + {error:"submit_cooldown", retry_after_sec}`로 UI가 남은 시간을 표시 가능
- Repeat avoidance:
  - PvP 매칭에서 최근 상대 반복에 penalty를 부여해 다양성을 높임(완전 차단 대신 “강한 감쇠”)
- Ops flag:
  - 의심 패턴(반복 매칭/쿨다운 위반 등)은 `Event(type="anti_abuse_flag")`로 기록(차단보다 관측 우선)

## Matchmaking Explainability (Reason + KPI)
- Match 응답:
  - `GET /api/matches/{match_id}` 및 `GET /api/matches`에 `matchmaking_reason`을 포함
  - HUMAN: `similar Elo, different user`, BOT: `pool low, bot fallback` (간단하지만 “왜”를 설명 가능하게)
- Analytics KPI:
  - `GET /api/analytics/overview`의 `summary.human_match_rate` / `summary.human_matches`로 “내 매치 중 인간 비율”을 노출

## Ops Surface (Season / Leaderboard / Profile)
- Backend:
  - `GET /api/meta/season` — ruleset_version/season_name/patch_notes
  - `GET /api/leaderboard?mode=&limit=` — Elo desc, games_played desc
  - `GET /api/users/{user_id}/profile?mode=` — 유저/레이트/대표 청사진/최근 경기
- Web:
  - `/leaderboard`, `/profile/:userId` 라우트로 “서비스 같은” 탐색 경험 제공

## Clip Feed / Remix (Public Alpha Growth Loop)
- Feed API: `GET /api/clips/feed?mode=...&sort=trending|new&limit=&cursor=...`
  - Source of truth: `matches(status=done)` + `replays` (clip unit = replay)
  - Segment: replay highlights Top1 기반 + min 6s/max 12s로 clamp한 “대표 클립”(결정론)
  - Output includes:
    - author, blueprint_id/name, share URLs(`/s/clip/...&v=1`), thumb URL(`/s/clip/.../thumb.png`), simple tags(하이라이트 tags)
- Tracking API: `POST /api/clips/{replay_id}/event`
  - Event types: `view|like|share|fork_click|open_ranked|completion`
  - Storage:
    - `events` table: `clip_view`, `clip_share`, `clip_fork_click`, `clip_open_ranked`
    - `clip_likes` table: like toggle(유저별 0/1) + 카운트 집계용
- Trending score:
  - Last 7 days + time decay(half-life 48h)
  - per-user/day dedupe로 간단한 스팸 완화
  - `algo=v2`는 전환 이벤트(특히 `fork_click/open_ranked/completion`)에 더 큰 가중치를 둠(클립→리믹스/랭크 전환을 최적화)
- Web: `/clips`
  - Vertical(9:16) best clip이 있으면 video, 없으면 `/s/clip/.../thumb.png`로 fallback
  - CTA: Like/Share(Remote link)/Remix(fork→Forge)/Rank(포크+제출+큐)

## Blueprint Lineage / Fork (Remix Flywheel v1)
- DB: `blueprints`에 lineage 캐시 컬럼을 추가해 “부모 1명 + 자식 다수” 트리를 유지
  - `forked_from_id` = parent blueprint id(기존 필드)
  - `fork_root_blueprint_id` = lineage root id
  - `fork_depth` = root로부터 depth(0=root)
  - `fork_count` = 누적 fork 수(ancestor에 캐시 업데이트)
  - `source_replay_id` = 어디서 포크됐는지(주로 `/s/clip/{replay_id}`)
- API:
  - `POST /api/blueprints/{blueprint_id}/fork` → spec 복제 + lineage 계산 + fork_count 캐시 업데이트
  - `GET /api/blueprints/{blueprint_id}/lineage` → `root/ancestors/self/children` + back-compat `chain`
  - Blueprint 조회 응답에 `fork_count`, `fork_root_blueprint_id`, `fork_depth` 포함
- Web:
  - Share Landing의 Remix CTA는 `/remix?...`로 진입 → (필요 시) `/start?next=...` → fork 생성 → `/forge/{new_blueprint_id}`
  - Forge에서 lineage UI(루트→…→내 빌드)와 `Remixes {fork_count}`를 노출
- Analytics:
  - Events: `fork_click`, `fork_created`, `lineage_viewed`
  - Rollup: `metrics_daily.fork_click_events`, `metrics_daily.fork_created_events`, funnel `remix_v1`

## Share Deep Link (/start) + Referrals
- `/start?next=...&ref=...` (SPA route):
  - 토큰이 없으면 자동으로 `POST /api/auth/guest`를 호출해 guest 토큰을 발급
  - `next`로 이동(오픈 리다이렉트 방지: 상대 경로만 허용)
  - `device_id`(localStorage)와 `ref`(추천인)를 보존해 attribution에 사용
- 추천인(Referral):
  - guest 생성 시 `ref`가 있으면 DB에 `referrals` row 생성
  - “첫 ranked 완료” 시점에 referrer/newbie 모두 cosmetic badge 지급(악용은 device/IP 기반으로 soft 제한)

## Trust/Safety (Report/Hide)
- Report:
  - `POST /api/reports`로 clip/profile/build 신고를 기록(`reports` table)
  - 운영 조회: `GET /api/ops/reports` (admin token gate: `NEUROLEAGUE_ADMIN_TOKEN`, header `X-Admin-Token`)
- Hide:
  - `POST /api/clips/{replay_id}/hide`로 유저별 숨김 토글(`user_hidden_clips`)
  - feed에서 숨김 반영(개인 필터)

## Ops Cleanup (Render Job Retention)
- `make ops-clean` / `scripts/cleanup_jobs.py`:
  - 오래된 `render_jobs`를 정리(done/failed TTL 기본 7일)
  - 오래 멈춘 queued/running job은 orphan으로 간주하고 failed 처리(orphan TTL 기본 12시간)
  - `--purge-artifacts` 옵션으로 local backend에서만 캐시 파일까지 삭제(기본은 DB만 정리)

## Share (OG) — Build/Profile
- 목적: SNS/메신저 크롤러가 JS를 실행하지 않아도 OG meta가 있는 HTML을 받도록 server-rendered landing 제공
- Endpoints:
  - `/s/build/{blueprint_id}` + `/s/build/{blueprint_id}/og.png` (never 404)
  - `/s/profile/{user_id}?mode=...` + `/s/profile/{user_id}/og.png` (never 404)
- OG image:
  - 우선 cached sharecard v2(있으면) 사용
  - 없으면 placeholder PNG 반환(절대 404 금지)

## Public Alpha Guardrails (Rate Limit)
- `services/api/neuroleague_api/rate_limit.py`:
  - fixed-window in-memory limiter(per-process)로 “폭주/비용” 방지
- 적용 위치:
  - Training run 생성
  - Render job 생성(clip/thumbnail/sharecard)
  - Clip event tracking
- 응답:
  - 초과 시 `429` + JSON payload(프론트가 친절히 표시 가능)

## Docker / Launch
- `docker-compose.yml`: `api` + `web` 최소 구성(artifacts volume 포함)
- Web dev proxy:
  - `apps/web/vite.config.ts`에서 `NEUROLEAGUE_API_PROXY_TARGET`로 `/api` 및 `/s/` 프록시 대상을 설정
  - 로컬 기본값: `http://127.0.0.1:8000`
  - Docker compose: `http://api:8000`

## Metrics / Experiments (Growth Ops)
- Event canonicalization:
  - `services/api/neuroleague_api/eventlog.py`가 `X-Device-Id`/`X-Session-Id` + IP/UA hash(SECRET 기반)로 이벤트 식별자/메타를 채움.
  - 클라이언트는 `apps/web/src/lib/api.ts`에서 모든 요청에 `X-Device-Id`/`X-Session-Id`를 자동 첨부.
- Event tracking:
  - `POST /api/events/track`는 서버 canonical taxonomy에 맞춘 이벤트(share_open, replay_open, blueprint_submit 등)를 저장.
  - 일부 핵심 이벤트는 서버가 자동 기록(share landings, ranked/tournament queue/done, replay_open 등).
- Experiments:
  - `GET /api/experiments/assign?keys=...`는 user/guest 기반 hash로 variant를 결정론적으로 배정하고(`ab_assignments`), 신규 배정 시 `experiment_exposed` 이벤트를 기록.
  - Web은 실험에 따라 UI/피드 알고리즘을 바꿈(예: clips_feed_algo v2/v3).
- Rollups:
  - `scripts/metrics_rollup.py` → `metrics_daily`, `funnel_daily`를 일별로 집계(ops-friendly).
  - Ops API: `/api/ops/metrics/*` (admin token gate).
- Ops UI:
  - Web `/ops` 페이지는 `X-Admin-Token`으로 ops endpoints를 호출해 KPI/퍼널/실험 결과를 가볍게 표시.

## Challenges (“Beat This”)
- 모델:
  - `challenges`는 “타겟(build|clip)”과 “룰(모드/portal/augments)”을 고정하고 shareable id를 부여.
  - `challenge_attempts`는 challenger별 시도/결과를 기록.
- 결정론:
  - attempt match_id는 `(challenge_id, challenger_id, attempt_index)`를 sha256로 파생해 재현 가능한 match를 만든다.
  - queue_type은 `challenge`이며 Elo 업데이트는 기본 off(update_ratings=False).
- Endpoints:
  - `POST /api/challenges`, `POST /api/challenges/{id}/accept`, `GET /api/challenges/{id}/leaderboard`
  - Share landing: `/s/challenge/{id}` (OG meta 포함) → `/start?next=/challenge/{id}`로 앱 딥링크.
- Web:
  - `/challenge/:id`에서 “Beat This”를 클릭하면 match를 큐잉하고 완료되면 `/replay/:match_id`로 이동.

## Content Packs + Patch Preflight
- Pack format:
  - `packs/default/v1/pack.json`에 catalog/synergies/modifiers를 “팩” 단위로 snapshot.
  - `pack_hash`는 canonical pack JSON(메타 제외)의 sha256.
- Loader:
  - `packages/sim/neuroleague_sim/pack_loader.py`가 ruleset env를 기준으로 pack을 로드하고, catalog/modifiers 전역을 in-place로 교체.
  - Replay `header.pack_hash`에 active pack_hash를 기록해 리플레이 재현/분석에서 버전을 추적 가능.
  - 구버전 replay는 pack_hash가 없을 수 있으며(None), 레거시 catalog로 계속 재생 가능.
- Preflight:
  - `scripts/patch_preflight.py`가 baseline vs candidate pack을 비교해 deterministic seeds로 matchup winrate 변화를 계산하고 `ops/preflight_latest.*`를 storage backend에 저장.
  - Ops API: `GET /api/ops/preflight/latest` (admin token gate) + public asset 링크(`/api/assets/ops/...`).

## Public Alpha Deploy (Single VPS Reference)
- Compose: `docker-compose.deploy.yml`
  - `caddy`(HTTPS) → `web`/`api` reverse proxy
  - `db`(Postgres)
  - `minio` + `minio_init`(S3-compatible storage + bucket bootstrap)
  - `rayhead` + `worker`(Ray cluster)
  - `scheduler`(metrics/balance rollups; optional)
  - `api`(migrate + seed + uvicorn)
- Env template: `.env.deploy.example`
  - 핵심: `NEUROLEAGUE_PUBLIC_BASE_URL`, `NEUROLEAGUE_TRUST_PROXY_HEADERS`, `NEUROLEAGUE_ALLOWED_HOSTS`,
    `NEUROLEAGUE_ADMIN_TOKEN`, `NEUROLEAGUE_AUTH_JWT_SECRET`
  - storage: `NEUROLEAGUE_STORAGE_BACKEND=s3` + MinIO endpoint/bucket/keys
- Health:
  - `/api/health`(liveness), `/api/ready`(DB+storage readiness), `/api/metrics`(Prometheus text)

## Ops Status / Weekly / Packs (Admin)
- Admin gate:
  - `NEUROLEAGUE_ADMIN_TOKEN` + header `X-Admin-Token`
- Deploy sanity:
  - `GET /api/ops/status`는 DB/storage/Ray/render_jobs/scheduler 상태를 한 번에 요약
  - Web `/ops`에서 “Deploy Sanity” 패널로 표시
- Weekly override:
  - public: `GET /api/meta/weekly`
  - admin: `GET /api/ops/weekly`, `POST /api/ops/weekly/override`
  - override 저장소: storage backend key `ops/weekly_theme_override.json`
- Packs promotion:
  - admin: `GET /api/ops/packs`, `POST /api/ops/packs/candidate`, `POST /api/ops/packs/promote`
  - candidate: `ops/pack_candidate.json`, promotion plan: `ops/pack_promotion_latest.json`
  - patch notes: `ops/patch_notes.json`를 `/api/meta/season.patch_notes`에 합쳐 노출

## Scheduler (Ops Autopilot)
- Entry: `services/api/neuroleague_api/scheduler_main.py`
- 주기 실행(ENV로 on/off):
  - metrics rollup: `rollup_growth_metrics()` → `metrics_daily`/`funnel_daily`
  - balance report: `compute_balance_report()` → `ops/balance_report_latest.*` 저장
- 상태 추적:
  - scheduler는 실행 시 `Event(type="ops_metrics_rollup")` / `Event(type="ops_balance_report")`를 남기고,
    `/api/ops/status.last_rollup_at/last_balance_report_at`에서 확인 가능

## Discord OAuth + Guest Upgrade
- OAuth:
  - `GET /api/auth/discord/start` → external auth URL(또는 mock callback)로 redirect
  - `GET /api/auth/discord/callback` → token 발급 + (옵션) guest 연결/merge
- Mock:
  - `NEUROLEAGUE_DISCORD_OAUTH_MOCK=true` 또는 client id 미설정 시 외부 Discord 호출 없이 mock id로 연결(E2E 안정성 목적)
- Merge(최소 정책):
  - guest가 이미 존재하는 discord 계정으로 연결을 시도하면 guest 데이터를 target으로 이관 후 guest 삭제

## Follow + Activity Feed
- Model:
  - `follows(follower_user_id, followee_user_id, created_at)`
- API:
  - `POST /api/users/{id}/follow` toggle
  - `GET /api/feed/activity`는 팔로우한 유저들의 서버 이벤트를 모아 feed를 구성(허용 타입 allowlist 적용)
- Web:
  - `/profile/:id`에서 Follow/Unfollow
  - `/social`에서 Following Feed(Empty state + CTA 포함)

## Deploy Smoke Script (Post‑Deploy, 60s Sanity)
- Script: `scripts/deploy_smoke.sh` (`make deploy-smoke`)
  - Checks: `/api/health`, `/api/ready`, `/api/meta/season`, `/s/clip/* OG meta`, `/start` deep link, `/api/events/track`
  - If `NEUROLEAGUE_ADMIN_TOKEN` is set, also checks `/api/ops/status` (worker_ok + pending_jobs_count)
- Demo replay selection:
  - Prefer `GET /api/assets/ops/demo_ids.json` → `clip_replay_id`
  - Fallback: `GET /api/clips/feed?limit=1` → first `replay_id`

## Backup / Restore (Postgres → MinIO/S3)
- Scripts:
  - `scripts/backup_pg_to_s3.sh` — `pg_dump` → upload to S3/MinIO, keep last N keys, write `ops/last_backup.json`
  - `scripts/restore_pg_from_s3.sh` — download latest (or specified key) and `pg_restore --clean`
- Deploy compose:
  - `docker-compose.deploy.yml` includes a `backup` service (daily loop) when enabled via env.
- Ops status integration:
  - `/api/ops/status` reads `ops/last_backup.json` (via storage backend) and exposes `last_backup_at/last_backup_key`.

## Artifact Retention (Optional, Safe‑By‑Default)
- Scheduler path:
  - `services/api/neuroleague_api/scheduler_main.py` can run retention when `NEUROLEAGUE_ARTIFACTS_RETENTION_ENABLED=true`.
  - Latest run summary is written to `ops/retention_latest.json`.
- Cleanup tooling:
  - `scripts/cleanup_jobs.py` supports `--dry-run` and `--keep-shared-days`.
  - “Keep shared” guard uses recent `share_open` events to avoid deleting assets that are likely referenced by shared links.
- Storage backend:
  - Retention deletes cached artifacts through `StorageBackend.delete()` (LocalFS + S3 supported).

## Ops Moderation Inbox (Admin)
- Tables:
  - `reports` has `status(open/resolved)` + `resolved_at` for triage.
  - `moderation_hides` stores globally hidden targets (clip/build/profile).
  - `user_soft_bans` stores time‑boxed bans (block share/render generation).
- API (admin gated via `X-Admin-Token`):
  - `GET /api/ops/reports?status=open|resolved|all`
  - `POST /api/ops/reports/{id}/resolve`
  - `POST /api/ops/moderation/hide_target`
  - `POST /api/ops/moderation/soft_ban_user`
- Enforcement:
  - Feed/gallery exclude globally hidden targets.
  - Render job creation endpoints reject soft‑banned users (friendly 403).

## Seed Demo IDs (Never‑Empty Public Alpha)
- Seed script: `scripts/seed_data.py`
  - Always writes `ops/demo_ids.json` (key: `ops/demo_ids.json`, public via `/api/assets/ops/demo_ids.json`)
  - Used by deploy smoke and for “known-good” share links in a fresh deploy.
- Deploy:
  - `docker-compose.deploy.yml` seeds demo content on boot when `NEUROLEAGUE_SEED_ON_BOOT=1` (idempotent).

## Featured Curation (Launch Week)
- Table:
  - `featured_items(kind="clip"|"build"|"user"|"challenge", target_id, title_override, priority, starts_at, ends_at, status, created_at, created_by)`
- API:
  - Public: `GET /api/featured?kind=&active=true`
  - Admin: `GET/POST/DELETE /api/ops/featured*` + `POST /api/ops/featured/{id}/update` + `POST /api/ops/featured/expire`
- Feed integration:
  - `GET /api/clips/feed` first page pins up to 3 active featured clips (cap `min(3, limit-1)`) and avoids duplicates.
  - Response adds optional `featured: true` per item (backward compatible).
- Ops UI:
  - Web `/ops/featured` supports listing/filtering + add/remove + priority update.
- Maintenance:
  - Scheduler expires `ends_at <= now` rows by setting `status="expired"` (safe to run any time).

## Quests (Daily / Weekly)
- Tables:
  - `quests` (definitions), `quest_assignments` (per-user progress), `quest_events_applied` (idempotency)
  - `wallets.cosmetic_points` (duplicate cosmetic reward fallback)
- Engine: `services/api/neuroleague_api/quests_engine.py`
  - KST period keys: daily `YYYY-MM-DD`, weekly ISO `YYYYW##`
  - Deterministic set selection: sort by `sha256(seed|quest.key)` where seed=`cadence|period_key|ruleset_version`
  - Ops override stored in storage backend key `ops/quests_override.json`
  - Idempotency enforced via `quest_events_applied(event_id, assignment_id)`
- API:
  - `GET /api/quests/today` returns daily+weekly assignments (created lazily per user)
  - `POST /api/quests/claim` validates completion, grants cosmetic (or points), sets `claimed_at`
  - Admin: `GET/POST /api/ops/quests` + `POST /api/ops/quests/override`
- Event integration:
  - Event ingest paths call `apply_event_to_quests()` so progress is server-side updated whenever events are written.
- Web:
  - Home: “Today’s Quests” card (progress + claim)
  - Profile: recent quest history (last 7 days)
  - Ops: `/ops/quests` shows current set + override controls

## Discord Launch Loop (Webhook / App / Mock)
- Settings: `NEUROLEAGUE_DISCORD_*` envs (also accepts unprefixed `DISCORD_*` for deploy convenience)
  - mode: `webhook|app|mock` (default webhook)
- Outbox:
  - `discord_outbox` stores payload + status + retry bookkeeping.
  - Sender respects 429 Retry-After and uses backoff; scheduler drains outbox.
- Daily challenge:
  - `ensure_daily_challenge()` deterministically creates/reuses a daily `Challenge` id and links it via `featured_items(kind="challenge")`.
- API:
  - Interactions: `POST /api/discord/interactions` (app mode verifies Ed25519 signature)
  - Ops: `GET /api/ops/discord`, `POST /api/ops/discord/test_post`, `POST /api/ops/discord/register_commands`
- Web:
  - Ops UI: `/ops/discord` shows mode/status + test post payload preview + register commands button
- Tooling:
  - `scripts/discord_register_commands.py` (called by `make discord-register`) registers `/nl` commands in app mode.

## Variation Engine (Portals + Augments)
- Pack schema:
  - `packs/*/pack.json` includes top-level `portals[]` and `augments[]` (included in `pack_hash` canonicalization).
  - Loader supports legacy fallback (`modifiers.portals/augments`) for backward compatibility.
- Deterministic selection:
  - `packages/sim/neuroleague_sim/modifiers.py#select_match_modifiers` picks:
    - 1 portal per match_id
    - augment offers (3 options) + chosen per phase/round
  - Offers/chosen are stored in DB (`matches.portal_id`, `matches.augments_*_json`) and replay header.
- Replay events:
  - `PORTAL_SELECTED`, `AUGMENT_OFFERED`, `AUGMENT_CHOSEN` are emitted into `timeline_events` so UI can render a deterministic timeline.
- Analytics:
  - `GET /api/analytics/portals|augments` aggregates pick/winrate from matches, with `low_confidence` below sample threshold.

## Viral Engine v3 (Best Clip Prewarm + Captions)
- Best segment selection:
  - `services/api/neuroleague_api/clip_render.py#best_clip_segment` chooses highlights[0] else middle 10s (deterministic clamp).
- Prewarm:
  - On match completion, thumbnail + vertical MP4 render jobs are enqueued (idempotent; heavy work stays in `render_jobs`/worker).
  - In `NEUROLEAGUE_E2E_FAST=1`, renders may run synchronously for test stability.
- Share landing:
  - `/s/clip/{replay_id}` defaults to the best segment and prefers cached vertical MP4 + thumb; OG `og:image` is never-404.
  - Creator Pack: `/s/clip/{replay_id}/kit.zip` bundles mp4/thumb/caption/qr into a deterministic zip (ETag + immutable cache).
  - Captions: overlay templates are versioned (`CAPTIONS_VERSION=capv4`) and the chosen `template_id` is included in the clip cache key.

## UGC Engine (Build Code + Lineage + Build of the Day)
- Build code:
  - Encoder/decoder: `services/api/neuroleague_api/build_code.py`
  - API:
    - `POST /api/build_code/decode` returns preview + warnings (ruleset/pack mismatch).
    - `POST /api/build_code/import` creates a draft blueprint and links lineage when possible.
    - `GET /api/blueprints/{id}/code` returns the build code for a blueprint (owner or submitted).
  - DB:
    - `blueprints.origin_code_hash` stores sha256(build_code) for external import traceability.
- Lineage:
  - `GET /api/blueprints/{id}/lineage` returns a parent chain plus `children_count` for fork count.
- Build of the Day:
  - Public: `GET /api/gallery/build_of_day` returns KST date + deterministic pick; override is applied first.
  - Ops: `/api/ops/build_of_day` + `/api/ops/build_of_day/override` store overrides in `ops/build_of_day_override.json` (storage backend).
  - Discord: daily post prefers BOTD blueprint for the build embed.
