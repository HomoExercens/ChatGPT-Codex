# HANDOFF REPORT — Creature Lab Auto‑Battle League (NeuroLeague)

## This Sprint Plan (Steam Next Fest Pack)
### Goals
- Steam Next Fest용 **Windows Desktop Demo 빌드** 산출(GitHub Actions artifact)
- Demo 완주 화면에 **Wishlist / Discord CTA** 추가 + 이벤트/ops 집계로 “클릭이 숫자로 보이게”
- Steam Store 에셋(캡슐 4종) **자동 생성 파이프라인 + 체크리스트 문서** 추가
- Festival Ops Pack: 행사 운영 타임라인 문서 + `/ops`에 “Next Fest Live” 카드로 핵심 KPI/상태 한 화면화

### DoD
- Windows runner에서 Desktop Demo artifact 생성(`build-desktop-windows` workflow)
- Demo 완주 화면에 `Wishlist Now` / `Join Discord` CTA가 노출되고 이벤트(`wishlist_click`, `discord_click`)가 기록됨
- `scripts/export_steam_assets.py` 실행으로 `artifacts/steam_assets/`에 캡슐 4종 PNG가 생성됨(결정론/버전 고정)
- `/ops`에 “Next Fest Live” 카드가 표시되고 demo 완주율 + wishlist/kit 다운로드 + 5xx/렌더백로그 + 최근 alerts 요약이 보임(admin-gated)

### Risks / Rollback
- Risks: Desktop 모드에서 Ray 의존/크로스플랫폼 패키징 이슈가 발생할 수 있음 → Desktop 모드에서 Ray-free 로컬 실행기 사용
- Rollback: `NEUROLEAGUE_DESKTOP_MODE=false`로 기존 worker/Ray 경로 유지, Demo CTA는 그대로 유지(웹 프로덕션 영향 최소화)

### Verify Commands
- `make test`
- `NEUROLEAGUE_E2E_FAST=1 make e2e`
- `python scripts/export_steam_assets.py --help`

### Screenshots (docs/screenshots)
- Demo 완료 화면(Wishlist CTA): `54_demo_done_wishlist.png`
- Ops “Next Fest Live” 카드: `55_ops_nextfest_live.png`
- Steam assets export 결과(텍스트 캡처 또는 이미지): `56_steam_assets_tree.png`

## This Sprint Plan (Demo + Rehearsal + Multi‑Instance + Alerts)
### Goals
- Steam Next Fest 대비 “첫 60초 완주율” 개선: Demo Mode + Guided Run(`/demo`)
- 단일 VPS 실배포 리허설을 “복붙 스크립트”로 재현 가능하게(OG/MP4/kit.zip/작업큐)
- 멀티 인스턴스에서 중복 스케줄/중복 Discord/분산 에러 카드 지뢰 제거
- KPI 급락/장애를 Discord로 자동 알림(429/Retry-After 안전, 스팸 억제)

### DoD
- `NEUROLEAGUE_DEMO_MODE=true`에서 Home 최상단 CTA → Demo Run → best clip → kit.zip → Beat This가 끊김 없이 동작
- `scripts/vps_rehearsal_check.sh <base_url>`로 VPS에서 핵심 smoke를 자동 검증
- scheduler/discord outbox/ops errors가 multi-instance에서 중복 실행되지 않음(락/DB 기반)
- Ops(`/ops`)에 demo funnel + recent errors + alerts 카드가 보임(admin-gated)

### Risks / Rollback
- Risks: scheduler interval이 너무 길면 alerts/discord drain이 늦어질 수 있음(권장: 15~60m)
- Rollback: `NEUROLEAGUE_DEMO_MODE=false`, `NEUROLEAGUE_ALERTS_ENABLED=false`로 기능 비활성화(코드/데이터 호환 유지)

### Verify Commands
- `make test`
- `NEUROLEAGUE_E2E_FAST=1 make e2e`
- `./scripts/vps_rehearsal_check.sh https://<your-domain>`

### Screenshots (docs/screenshots)
- `50_demo_home_cta.png`, `51_demo_page.png`, `52_demo_done.png`, `53_demo_replay.png`
- `33_ops.png` (funnels/experiments), `40_ops_deploy_sanity.png` (deploy sanity)

## 1) Executive Summary
- Economy v1.5: Draft에 reroll/level-up/rarity tiered shop을 도입하고, 시너지 threshold를 2/4/6(확장 대비)로 통일.
- Training “checkpoint → blueprint”가 진짜가 됨: 체크포인트 정책을 결정론적으로 inference해 draft를 실행하고 그 결과 spec을 저장(실패 시 안전한 fallback + meta.note 기록).
- Ranked가 기본 “real PvP”: 제출된 다른 유저 청사진(모드/룰셋 분리)에서 Elo 근접 상대를 결정론적으로 선택하고, 풀 부족 시 bot으로 fallback.
- Clip export MVP: replay에서 썸네일 PNG + GIF/WebM 클립을 서버에서 결정론적으로 렌더/캐시(`artifacts/clips/`)하고 Replay UI에서 10초 내 생성/다운로드 가능.
- `make test`/`make e2e`(fast) 통과를 유지하며 결정론/리플레이 digest 안정성 유지.
- 팀전 메타 깊이: “Sigil(시너지 카운트 보너스)” 아이템으로 3v3에서도 T4/T6 시너지가 실제로 발생(리플레이/하이라이트/Analytics에서 tier가 보임).
- PvP 공정성 가드레일: 제출 쿨다운 + 반복 상대 매칭 페널티 + anti-abuse flag 이벤트 기록(차단이 아니라 기록/감쇠부터).
- 공유 확산: `/s/clip/{replay_id}` 서버 렌더(OG meta) + Replay에서 “Copy Share Link” 기본 제공(메신저/트위터 미리보기 목적).
- Deploy Confidence: GitHub Actions에서 `docker-compose.deploy.yml`을 dummy env로 기동해 `/api/ready`, `/s/*` OG meta + og:image never-404, render_jobs, assets allowlist까지 자동 스모크 검증(실패 시 `deploy-smoke-diagnostics` artifact로 docker logs + deploy-smoke/curl 결과 업로드).
- Share Conversion: `/s/clip|build|profile|challenge`에 QR(`/s/qr.png`→`/start?next=...`) + Share Kit(앱 링크/캡션/디스코드 복사/다운로드 MP4 + build code 노출) + CTA 우선순위/experiments 연결 + 이벤트 트래킹(share_open/qr_shown/caption_copied 등).
- Creator Pack: `/s/clip/{replay_id}/kit.zip`로 MP4+thumb+caption+QR을 한 번에 zip 다운로드(결정론/ETag) + `/s/clip`/`/replay`에 `Download Kit` 노출.
- Shorts-ready Best Clip: highlights 기반 segment를 6~12s로 clamp + captions template system(`CAPTIONS_VERSION=capv4`, template_id 기록+cache key 포함)으로 vertical MP4 완제품화를 강화(Clutch/Portal/Augment 템플릿 추가).
- Steam Demo Mode: `NEUROLEAGUE_DEMO_MODE=true`에서 Home 최상단 CTA → `/demo` guided run(게스트) → best clip + Creator Kit.zip + Beat This까지 5분 완주 플로우 제공.
- 렌더 비용 대응: clip/sharecard는 `render_jobs`(DB) + Ray 백그라운드 작업으로 전환(캐시 miss 시 202/job_id → 폴링).
- 최소 운영 장치: 시즌/룰 버전 노출 + 리더보드(/leaderboard) + 유저 프로필(/profile/:id) 추가.
- 스케일 대비: artifacts 저장을 storage backend로 추상화(local 기본, S3/CDN-ready)하고 `/api/assets`(allowlist)로 공유 자산을 안전하게 서빙 + balance report(ops) 생성/노출.
- Public Alpha(배포 대비): `NEUROLEAGUE_PUBLIC_BASE_URL` + 프록시 헤더 신뢰(`NEUROLEAGUE_TRUST_PROXY_HEADERS`)로 OG/공유 URL이 HTTPS/리버스프록시 뒤에서도 정확하게 생성되며, `/api/ready`/`/api/metrics`로 최소 관측성을 제공.
- Production Hardening: `X-Request-Id`(요청/에러 포함) + HTTP latency histogram + ops 최근 60분 에러 카드 + hot query 인덱스 마이그레이션 + dual(user+ip) rate limit/Retry-After 일관화.
- Multi-instance Safety: scheduler/discord outbox는 DB 기반 락/`SKIP LOCKED`로 중복 실행/중복 전송을 방지하고, ops recent errors는 DB에 저장해 인스턴스 간 분산을 제거.
- KPI Drop Alerts: scheduler가 funnel drop/5xx spike/render backlog를 체크하고 Discord outbox(kind=alert)로 쿨다운(2h) 포함 알림을 발송, `/ops`에서 최근 알림/상태를 확인 가능.
- Viral/Growth v2: share landing의 “Open in App”가 `/start`를 통해 토큰 없는 유저도 1‑click 게스트 온보딩 → 리플레이/포지/갤러리로 딥링크, referral(추천인) + cosmetic 보상으로 공유→유입→첫 랭크 완료 루프 강화.
- Trust/Safety: 클립/프로필/빌드 신고(`reports`) + 유저별 숨김(`user_hidden_clips`) + admin ops 조회(`/api/ops/reports`)로 퍼블릭 알파에서 터질 지점을 최소 봉합.
- Ranked 신뢰성: 매치 카드/리플레이에 `matchmaking_reason`(HUMAN/BOT 사유) 표시 + Analytics에 `human_match_rate` KPI 추가.
- Ops 비용 관리: `make ops-clean`로 오래된 render job TTL 정리(옵션으로 local 캐시 파일 purge).
- Metrics/Experiments: 서버 canonical 이벤트(`/api/events/track`) + 결정론적 A/B 배정(`/api/experiments/assign`) + ops 집계/대시보드(`/ops`, daily funnels 포함)로 “측정→실험→최적화” 루프를 추가.
- Launch Ops: 실험 variant별 KPI(표본/전환율) + Featured 내일 미리보기 + Discord daily post에 Beat/Remix/Build Code를 포함(모의 모드 포함)해 런칭 주간 운영 루프를 강화.
- Challenge Links: “Beat This” 도전 링크(`/s/challenge/{id}` OG) → 앱 딥링크(`/start`) → `/challenge/{id}`에서 즉시 매치 생성/관전으로 이어지는 공유 기반 대결 스레드 MVP 구현.
- Content Packs/Preflight: `pack.json` + `pack_hash`를 replay header에 기록하고, pack 비교 리포트(preflight)를 `ops/`에 생성/서빙(`/api/ops/preflight/latest`)하여 패치 전 위험도 점검 루프를 추가.
- Public Alpha Deploy 레퍼런스: `docker-compose.deploy.yml`(Caddy+Postgres+MinIO+Ray+worker+scheduler) + `.env.deploy.example` + `make deploy-up/down/logs`로 “한 대 VPS” 기동 경로를 제공.
- Ops Autopilot: admin-gated `/api/ops/status` + Web `/ops` Deploy Sanity, `/ops/packs`(pack promotion), `/ops/weekly`(weekly override)로 운영 루프를 얇게 완성.
- Community Loop: Discord OAuth(옵션, mock 지원) + guest upgrade/merge + Follow(`/api/users/{id}/follow`) + Following feed(`/social`) 추가.

## 2) Completed Work (Checklist)
- [x] Catalog rarity: `CreatureDef`/`ItemDef`에 `rarity(1..3)` 추가 + 결정론적 rarity index 맵 추가
- [x] Synergy tiers: 2/4/6 threshold 기반 효과 정의 + `SYNERGY_TRIGGER`에 threshold/count 포함
- [x] Draft env v1.5(`neuroleague_draft_parallel_v15`): reroll/level-up + tiered shop + rarity 비용 + draft_log 기록
- [x] to-blueprint 정책 inference: 체크포인트 정책으로 draft를 결정론 실행해 실제 spec 저장 + `meta_json.draft_log` 보관(구버전/오류는 fallback)
- [x] Blueprints 스키마 확장: `meta_json`/`submitted_at` 컬럼 + submit 시각 기록
- [x] PvP matchmaking 기본: Elo 근접 “다른 유저” 제출 청사진 우선 매칭 + deterministic top-K 선택 + bot fallback 유지
- [x] Seed data: day-0 PvP 풀을 위해 lab users + (1v1/team) submitted blueprints + ratings 추가
- [x] Clip export: `thumbnail`(PNG) + `clip`(GIF/WebM) 엔드포인트, digest+params 캐시(`artifacts/clips/`)
- [x] ReplayPage: Clip Export 패널(썸네일 프리뷰/Export 버튼/다운로드 링크/링크 복사) 추가
- [x] 테스트 보강: Draft env 결정론 + to-blueprint inference/fallback 테스트 추가, `make test` PASS / `make e2e` PASS 유지
- [x] Sigil(시너지 보너스) 아이템: 팀 시너지 count에 +N을 더해 T4/T6 실전화 + 이벤트/캡션/Analytics 연동
- [x] Anti-abuse: 제출 쿨다운(429 + retry_after_sec) + 반복 상대 페널티 + Event(type=anti_abuse_flag) 기록
- [x] Share landing OG: `/s/clip/{replay_id}` + `/s/clip/{replay_id}/thumb.png`(never 404, placeholder) + Replay 기본 공유 링크 전환
- [x] Render jobs: `render_jobs` 테이블 + `/api/render_jobs/*` + clip/sharecard job 생성/폴링 UX(캐시 miss 시 비동기)
- [x] Ops: `/api/meta/season`, `/api/leaderboard`, `/api/users/{id}/profile` + Web `/leaderboard`, `/profile/:id`
- [x] Storage abstraction: artifact key 기반 저장(`replays/`, `clips/`, `sharecards/`) + 레거시 absolute path 호환 + `/api/assets/*` 공개 서빙(allowlist)
- [x] Balance bot: `make balance-report` → `artifacts/ops/balance_report_*` + `/api/ops/balance/latest` + MetaPage “Balance Watch” 표시
- [x] Proxy-safe share URLs: `NEUROLEAGUE_PUBLIC_BASE_URL` 우선 + `NEUROLEAGUE_TRUST_PROXY_HEADERS` + host allowlist로 OG/공유 링크 안정화
- [x] Ops endpoints: `/api/ready`(DB/스토리지 sanity) + `/api/metrics`(Prometheus text) 추가
- [x] Prod-like compose: `docker-compose.prod.yml`(postgres+minio+ray+worker+web) + Makefile `prod-up/down/logs`
- [x] Share deep-link: `/start?next=...&ref=...`로 토큰 없는 유저도 1‑click 앱 진입 + open-redirect 방지
- [x] Referrals: guest 생성 시 ref 기록 + 첫 ranked 완료 시 referrer/newbie cosmetic 지급(anti-abuse: device + IP soft-cap)
- [x] Clips trending v2: `algo=v2` + `completion` 이벤트로 “전환(리믹스/랭크)” 가중치 강화
- [x] Moderation MVP: `POST /api/reports`, `POST /api/clips/{replay_id}/hide`, `GET /api/ops/reports`(admin token gate)
- [x] Matchmaking explainability: match responses에 `matchmaking_reason`, analytics overview에 `human_match_rate` 추가
- [x] Ops cleanup: `make ops-clean` / `scripts/cleanup_jobs.py` + 테스트 추가
- [x] Deploy compose: `docker-compose.deploy.yml` + `deploy/Caddyfile` + `.env.deploy.example` + Makefile `deploy-up/down/logs`
- [x] Ops status: `GET /api/ops/status` + Web `/ops` Deploy Sanity 패널
- [x] Discord OAuth: `/api/auth/discord/start|callback` + guest upgrade/merge + `users.discord_id/avatar_url`
- [x] Follow + feed: `follows` + `POST /api/users/{id}/follow` + `GET /api/feed/activity` + Web `/social`
- [x] Weekly override: storage key `ops/weekly_theme_override.json` + `GET/POST /api/ops/weekly*` + Web `/ops/weekly`
- [x] Packs promotion: `GET/POST /api/ops/packs*` + patch notes append(`ops/patch_notes.json`) + Web `/ops/packs`
- [x] CI deploy smoke: `.github/workflows/ci.yml` `deploy-smoke-compose` + `.env.deploy.ci.example` + `scripts/deploy_smoke.sh`(OG/meta/render_jobs/assets) 자동 검증
- [x] Share kit: `/s/qr.png` + deterministic `share_caption`(versioned) + CTA 우선순위 + tracking 이벤트 추가
- [x] Best clip captions v3: deterministic template 선택+template_id 기록(params_json) + min 6s/max 12s segment 정책 + cache key versioning

## 3) Notable Changes
- Draft env는 action/obs가 바뀌어 env name을 `*_v15`로 bump(구버전 체크포인트와 충돌 방지). to-blueprint는 restore 실패/불일치 시 fallback하여 UX를 깨지 않음.
- Blueprint에 `meta_json`/`submitted_at`을 추가해 (1) draft 로그 표시, (2) PvP matchmaking에서 최신 제출본을 안정적으로 선택 가능.
- PvP 매칭은 “재현 가능성”을 위해 `match_id` 기반 결정론적 선택(top-K)로 고정(디버깅/리플레이 일치 보장).
- Clip export는 replay JSON에서 HP state를 재구성해 렌더하며, `digest+params` 캐시로 같은 요청은 동일 바이트/즉시 응답을 목표로 함.
- Artifact 저장은 key 기반으로 전환(`NEUROLEAGUE_ARTIFACTS_DIR` 하위 상대 경로)했으며, 레거시 absolute path도 계속 로드 가능하도록 호환 처리.

### Metrics / Experiments / Challenges / Packs (This Sprint)
- [x] Event taxonomy: `POST /api/events/track` + 서버측 자동 이벤트 기록(share_open/replay_open/ranked_done 등)
- [x] Experiments: `GET /api/experiments/assign` 결정론적 배정 + Web에서 CTA/피드 알고리즘 적용(clips_feed_algo / share_cta_copy / quick_battle_default)
- [x] Ops metrics: rollup(`make ops-metrics-rollup`) + `/api/ops/metrics/*` + Web `/ops` 대시보드 + E2E 스크린샷
- [x] Challenges: `/api/challenges/*` + deterministic match_id + `/s/challenge/{id}` OG landing + Web `/challenge/{id}` accept → replay
- [x] Content packs: `packs/default/v1/pack.json` + loader + replay header `pack_hash`
- [x] Patch preflight: `make ops-preflight` + `scripts/patch_preflight.py` + `/api/ops/preflight/latest`

### Launch Week Engine v1 (Featured / Quests / Discord)
- [x] Featured curation:
  - DB: `featured_items`
  - API: `GET /api/featured` + admin `POST/DELETE /api/ops/featured*`
  - Feed: `/api/clips/feed` first-page pin(cap) + optional `featured` flag
  - Web: `/ops/featured` (add/remove/priority)
- [x] Quests loop:
  - DB: `quests`, `quest_assignments`, `quest_events_applied`, `wallets.cosmetic_points`
  - API: `GET /api/quests/today`, `POST /api/quests/claim`, admin `/api/ops/quests*`
  - Web: Home “Today’s Quests” + Profile quest history + `/ops/quests` override
- [x] Discord launch loop:
  - Modes: `webhook|app|mock` + Ed25519 verify(interactions)
  - Outbox queue: `discord_outbox` + retry/backoff + 429 handling
  - Daily challenge: deterministic id + `featured_items(kind="challenge")` link
  - Web: `/ops/discord` + “Send test post” preview + command register helper(`make discord-register`)
- Evidence screenshots (`docs/screenshots/`):
  - Home quests card: `01_home.png`
  - Ops featured: `41_ops_featured.png`, `42_ops_featured_add.png`
  - Ops quests: `43_ops_quests.png`
  - Ops discord: `44_ops_discord.png`, `45_ops_discord_test_post.png`
- Validation:
  - `make test`: PASS
  - `NEUROLEAGUE_E2E_FAST=1 make e2e`: PASS (also generates screenshots above)
- Note:
  - 로컬 WSL 샌드박스 환경에는 `docker` CLI가 없을 수 있으므로, compose 배포 재현성은 GitHub Actions `deploy-smoke-compose` 결과를 레퍼런스로 삼는다.

### Variety × Virality × UGC (This Sprint)
- [x] Variation Engine (Portals + Augments):
  - Pack: `portals[]`/`augments[]`를 pack에 포함하고 `pack_hash`에 반영(legacy fallback 유지)
  - Match/replay: match_id 기반으로 portal 1개 + augment offers/chosen을 결정론적으로 선택/기록(DB + replay header + timeline events)
  - Analytics: `/api/meta/portals|augments`, `/api/analytics/portals|augments` 추가(표본 부족은 low_confidence)
- [x] Viral Engine v3 (Auto Best Clip):
  - best segment: highlights[0] 우선, 없으면 중간 10초 fallback(결정론)
  - prewarm: match done 시 thumb + 9:16 MP4 render_jobs enqueue(멱등, FAST 모드 sync 지원)
  - share: `/s/clip`은 best clip 중심 CTA(Beat This/Remix/Open Ranked) + OG(best thumb) never-404
- [x] UGC Engine (Build Code + Build of the Day):
  - API: `POST /api/build_code/decode|import`, `GET /api/blueprints/{id}/code` 추가
  - Forge: import preview(warnings) 후 import, lineage에 fork 수(`children_count`) + external origin(`origin_code_hash`) 표시
  - Build of the Day: KST seed로 결정론적 선정 + Ops override(`/ops/build-of-day`) + Discord daily post에서 BOTD 우선 사용
- Evidence screenshots (`docs/screenshots/`):
  - best clip vertical + share landing: `18_best_clip_vertical.png`, `19_share_landing_bestclip.png`
  - build code import modal/result: `46_forge_build_code_import_modal.png`, `47_forge_build_code_imported.png`
  - ops build-of-day override: `48_ops_build_of_day_override.png`
  - build code import → ranked done: `49_build_code_import_ranked_done.png`

### Launch Candidate Polish (This Sprint)
- [x] Ops funnel KPIs: daily rollups(`share_v1`, `clips_v1`) + `/ops` Funnels(daily) 카드(today/7d avg/Δ) + seed demo events
- [x] Share MP4: `/s/clip/{replay_id}/video.mp4`에 ETag + immutable cache + Range(206) 지원(모바일 재생 최적화)
- [x] Share Build: `/s/build/{blueprint_id}`에서 build code를 항상 노출하고 원클릭 복사(UGC 확산 마찰 제거)
- [x] Lineage: blueprint lineage에 “Top Forks” 노출(API + Forge UI)
- [x] Scheduler autopilot: KST day 기준 deterministic featured rotation(clip/build/user) + ops override 존중
- [x] CI deploy smoke: 실패 시 `deploy-smoke-diagnostics`로 docker logs + curl/deploy-smoke 결과를 업로드해 원인 파악 가능

#### Funnel Definitions (Daily)
- `share_v1`: `share_open` → `start_click` → `guest_start_success` → `first_replay_open` → `ranked_queue` → `ranked_done`
- `clips_v1`: `clip_view` → `clip_completion` → `share_open` → `fork_click` → `open_ranked` → `ranked_done`
- Notes:
  - 집계 단위는 “day × distinct user” 기준이며, 샘플이 적을 땐 방향성 지표로만 해석한다.
  - Rollup은 `POST /api/ops/metrics/rollup`(admin) 또는 `make ops-metrics-rollup`로 갱신한다.
  - variants/experiments는 v2에서 유의성(통계)까지 확장한다(현재는 표본수/전환율 관측용).

## 4) How to Run
- Dev: `make dev`
  - API: `http://localhost:8000` (Docs: `http://localhost:8000/docs`)
  - Web: `http://localhost:3000`
- Test: `make test`
- E2E: `make e2e` (screenshots: `docs/screenshots/`)
- Seed reset(샘플 리플레이/봇/청사진 재생성): `make seed-data-reset`
- Ops metrics rollup: `make ops-metrics-rollup`
- Patch preflight: `make ops-preflight` (baseline/candidate pack 비교 리포트 생성)
- Pack snapshot: `make generate-pack` (현재 sim content → `packs/default/v1/pack.json`)
- UI 동기화: `./scripts/sync_ui.sh`
- Deploy (Single VPS reference):
  - `cp .env.deploy.example .env.deploy`
  - `make deploy-up` (or `docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build`)

## 5) How to Verify UX (첫 5분 UX 완주)
0. (Steam Demo Mode) `NEUROLEAGUE_DEMO_MODE=true`로 실행 후:
   - `/home` 상단 CTA `Play Demo Run (5 min)` → `/demo`
   - `Play Demo Run` → best clip 생성 완료 → `Download Kit.zip` 다운로드(4 files) → `Beat This` 진입
1. `/` 로그인 화면에서 `게스트로 시작` 클릭 → `/home`
2. `/training`
   - budget을 낮춘 뒤 `실험 시작` 클릭 → 진행률(%)가 즉시 업데이트
   - `체크포인트` 탭에서 체크포인트가 최소 1개 생성되는지 확인
   - 생성된 체크포인트에서 `To Blueprint` 클릭 → `/forge?bp=...` 이동
3. `/forge`
   - `Draft Summary` 패널이 있으면 펼쳐서 라운드별 offers/actions( reroll/level_up 포함 )가 보이는지 확인
   - blueprint 출처 배지/문구가 `POLICY`(policy_inference) 또는 `FALLBACK`(fallback_deterministic)로 표시되는지 확인
   - `Validate` → OK 확인
   - `제출`(Submit) → submitted 상태 확인
4. `/ranked`
   - submitted 청사진 선택 → `랭크전 입장` 클릭
   - 상태가 `Queued/Running/Done`로 변하며 완료 시 `Open Replay`
   - 결과 카드에서 상대 `HUMAN/BOT` 배지 + (가능하면) 상대 Elo가 보이는지 확인
5. `/replay/{id}`
   - 타임라인 슬라이더 스크럽 시 Canvas 전투 뷰포트가 즉시 변함(HP/타겟/데미지 등)
   - Highlights 카드 3개 각각 `점프` 동작(전환점 구간으로 이동)
   - 상단 `오버레이` 토글 On/Off가 실제 렌더(라인/텍스트/배지)에 반영됨
   - `Set Start`/`Set End` → `Copy Share Link`로 `/s/clip/{replay_id}?start=&end=` 복사 확인
   - `Copy App Link`로 `/replay/{match_id}?t=&end=` 복사 확인(앱 딥링크)
	   - `/s/clip/...` 진입 시: 썸네일 + CTA(앱에서 보기) + OG meta(봇용) 존재 확인
	   - `/s/clip/...`에서 QR + `Copy Caption`/`Copy App Link`가 보이고, `Copy Caption` 클릭 시 토스트(“Copied caption.”)가 뜬다
	   - `Beat This Link` 클릭 → `/s/challenge/{challenge_id}` 링크 생성/복사 → 링크 진입 시 OG meta + CTA 확인 → CTA 클릭 → `/challenge/{id}` → `Beat This` 실행 후 replay로 이동
	   - Clip Export:
	     - `Generate Thumbnail` → 썸네일 프리뷰 표시
	     - `Export GIF` / `Export WebM` → 다운로드 링크 생성 및 파일 다운로드
   - `Share` 클릭 → sharecard job 생성/완료 후 PNG 다운로드 확인
6. `/analytics`
   - `Matchups` / `Build Insights` / `Version Compare`가 실데이터로 채워지는지 확인
7. `/leaderboard` / `/profile/:id`
   - 리더보드 목록이 보이고 row 클릭 시 프로필로 이동
   - 프로필에서 Elo/경기수/최근 경기/대표 청사진이 보이고, 최근 경기 클릭 시 replay로 이동
8. `/ops` (admin)
   - API에 `NEUROLEAGUE_ADMIN_TOKEN` 설정 후 `/ops` 진입
   - admin token 입력 시 KPI/퍼널/실험 카드가 로드됨(`/api/ops/metrics/*`)
   - Alerts 카드가 로드되고 최근 알림/상태가 표시됨(`/api/ops/metrics/alerts_recent`)
   - preflight 카드가 `available`이거나 `make ops-preflight` 안내가 표시됨(`/api/ops/preflight/latest`)
   - Deploy Sanity 패널이 로드됨(`/api/ops/status`)
9. `/ops/packs` (admin)
   - candidate pack 선택/저장(`/api/ops/packs/candidate`)
   - promote → promotion plan 저장 + `/api/meta/season.patch_notes`에 항목 추가(`/api/ops/packs/promote`)
10. `/ops/weekly` (admin)
   - weekly theme 표시(`/api/ops/weekly`)
   - override 저장/clear가 동작하고 `/api/meta/weekly?week_id=` 결과가 바뀜
11. `/social`
	   - 프로필에서 `Follow` 후 `/social`에 following feed가 표시됨(빈 상태면 Empty state + 리더보드 CTA)
12. CI (GitHub Actions)
	   - workflow `ci.yml`의 job `deploy-smoke-compose`가 green인지 확인(WSL 로컬 docker 불필요)

## 6) Replay/Highlights Details
- replay `header.units`(formation_slot/max_hp/tags/items 등)로 초기 스냅샷을 제공 → 프론트는 포메이션+슬롯 기반 고정 좌표로 배치(RNG 사용 없음).
- 뷰포트 렌더: tick 기반 상태 집계(HP, alive) + 이벤트 기반 오버레이(공격/데미지/시너지).
- 하이라이트 선정: DEATH / DAMAGE spike / HP swing / SYNERGY_TRIGGER 후보 점수화 → Top3를 non-overlap(min gap)로 선택 + tags(유닛/시너지/아이템) 부착.
- `SYNERGY_TRIGGER`는 threshold(2/4/6) 정보를 포함해 “몇 단계 시너지인지”를 UI에서 명확히 표시 가능.

## 7) Training UX Details
- CPU-only 고정: `torch==2.9.1+cpu`, CUDA/GPU 초기화 시도 없음.
- 진행 UI: status + progress(%)+ 최근 변화(trend) 표기, 실패 시 에러 요약 + CTA + retries=0 명시.
- E2E fast-path: `NEUROLEAGUE_E2E_FAST=1`에서 iteration=1로 단축(데모/테스트용).
- 체크포인트 → blueprint 변환은 체크포인트 정책 inference 기반이며, draft 기록은 blueprint meta에 저장되어 Forge에서 확인 가능.

## 8) Content Pack
- Catalog(시뮬): `packages/sim/neuroleague_sim/catalog.py` (creatures 12종+, items 18종+, synergies 8종+)
- Pack snapshot: `packs/default/v1/pack.json` (canonical `pack_hash` 포함)
- Replay header: 새로 생성되는 replay JSON은 `header.pack_hash`로 pack 버전을 추적 가능(구버전 리플레이는 None일 수 있음)
- Patch preflight: `make ops-preflight` → `artifacts/ops/preflight_latest.{json,md}` 생성(ops에서 pack 간 밸런스 변화 점검)
- 1v1 + 팀전 봇 아키타입(각 6) 및 seeded replays(총 20, 팀전 10 포함)는 `make seed-data-reset`로 재생성.
- Sample replays: `artifacts/replays/r_seed_001.json` … `r_seed_020.json`
- PvP 풀(day-0): `scripts/seed_data.py`가 lab users(예: alice/bob/…)의 submitted blueprints(1v1/team) + ratings를 생성.

## 9) Known Issues / Next Steps
- Sharecard v2는 Playwright(Chromium) 의존이므로 최초 렌더 시 설치/실행 시간이 늘어날 수 있음(캐시 후 재사용).
- Replay 뷰포트는 현재 “관전 MVP+폴리시” 수준이며 고급 VFX/사운드/카메라 연출은 추후 확장.
- Analytics는 “done matches” 기준 집계라 데이터가 적으면 신뢰도가 낮을 수 있음(샘플 매치 더 생성/필터 UI 추천).
- Ray 종료 시 로컬 로그에 SIGTERM 경고가 남을 수 있음(UX 영향 없음).
- Clip export(WebM/GIF)는 CPU 작업이라 첫 생성 시 수 초가 걸릴 수 있음(캐시 후 즉시 응답). 필요 시 Ray background job로 분리 가능.

## 10) Files Changed (Key)
- `packages/sim/neuroleague_sim/catalog.py`, `packages/sim/neuroleague_sim/simulate.py` — rarity + synergy tiers(2/4/6) + 이벤트 payload 보강
- `packages/rl/neuroleague_rl/env.py`, `packages/rl/neuroleague_rl/training.py`, `packages/rl/neuroleague_rl/infer.py` — draft env v1.5 + PPO env bump + checkpoint policy inference
- `services/api/neuroleague_api/models.py`, `services/api/alembic/versions/0003_blueprint_meta_submitted_at.py` — blueprint meta/submitted_at 스키마
- `services/api/neuroleague_api/routers/training.py` — to-blueprint 정책 inference + fallback
- `services/api/neuroleague_api/routers/matches.py`, `services/api/neuroleague_api/routers/blueprints.py` — PvP 매칭 + 제출 시각 기록 + opponent 정보 응답
- `services/api/neuroleague_api/clip_render.py`, `services/api/neuroleague_api/routers/replays.py`, `requirements.txt` — clip export(썸네일/GIF/WebM) + 캐시
- `apps/web/src/pages/ForgePage.tsx`, `apps/web/src/pages/RankedPage.tsx`, `apps/web/src/pages/ReplayPage.tsx`, `apps/web/src/lib/api.ts`, `apps/web/src/api/types.ts` — Draft Summary / PvP 배지 / Clip Export UI
- `apps/web/e2e/first5min.spec.ts`, `tests/test_draft_env_v15_determinism.py`, `tests/test_to_blueprint_inference.py` — E2E/테스트 보강
- `scripts/seed_data.py`, `scripts/handoff.sh` — 시드 PvP 풀 + handoff zip 보강(클립/테스트 설명 포함)
- `services/api/neuroleague_api/core/config.py`, `services/api/neuroleague_api/main.py` — `NEUROLEAGUE_PUBLIC_BASE_URL`/proxy headers + `/api/ready`/`/api/metrics`
- `services/api/neuroleague_api/routers/share.py`, `apps/web/src/pages/StartPage.tsx` — share landing “Open in App” 딥링크(`/start`) + ref 전파
- `services/api/neuroleague_api/referrals.py`, `services/api/alembic/versions/0009_referrals.py` — referral 모델/보상 지급 파이프라인
- `services/api/neuroleague_api/routers/clips.py`, `tests/test_clips_trending_v2.py` — completion 이벤트 + trending v2(전환 가중치)
- `services/api/neuroleague_api/routers/reports.py`, `services/api/alembic/versions/0010_reports_and_hidden_clips.py` — report/hide + admin ops 조회
- `services/api/neuroleague_api/ops_cleanup.py`, `scripts/cleanup_jobs.py`, `tests/test_ops_cleanup.py` — render job TTL 정리(`make ops-clean`)
- `docker-compose.prod.yml`, `apps/web/Dockerfile.prod`, `apps/web/nginx.conf` — prod-like compose(web nginx + postgres/minio/ray)

## Automated Snapshot
- Timestamp: `2026-01-18T02:39:30+09:00`
- Git: `253eed25571ca62c5198cb4abfe4f02d34dcebd9`
- Recent commits:
- 253eed2 docs(decisions): add sharecard v2 and mode separation
- 7ab71fb docs(handoff): update report and checklists
- 6065836 test(e2e): add team flow and sharecard capture
- 8da1302 fix(web): fix BattleViewport TS syntax
- e2b24de feat(analytics): add coach recommendation cards
- Last handoff tag: `handoff/20260118_012137`
- Base for diff: `handoff/20260118_012137`
- Changed files since base:
- apps/web/e2e/first5min.spec.ts
- apps/web/scripts/render_sharecard.mjs
- apps/web/src/api/types.ts
- apps/web/src/components/replay/BattleViewport.tsx
- apps/web/src/pages/AnalyticsPage.tsx
- apps/web/src/pages/ForgePage.tsx
- apps/web/src/pages/RankedPage.tsx
- apps/web/src/pages/ReplayHubPage.tsx
- apps/web/src/pages/ReplayPage.tsx
- apps/web/src/pages/TrainingPage.tsx
- docs/ARCHITECTURE_NOTES.md
- docs/HANDOFF_REPORT.md
- docs/QA_CHECKLIST.md
- docs/decisions.md
- scripts/seed_data.py
- services/api/neuroleague_api/routers/analytics.py
- services/api/neuroleague_api/routers/matches.py
- services/api/neuroleague_api/routers/replays.py
- services/api/neuroleague_api/routers/training.py
- Diff stat since base:
```
 apps/web/e2e/first5min.spec.ts                    | 103 +++-
 apps/web/scripts/render_sharecard.mjs             |  62 +++
 apps/web/src/api/types.ts                         |   1 +
 apps/web/src/components/replay/BattleViewport.tsx | 588 ++++++++++++++++------
 apps/web/src/pages/AnalyticsPage.tsx              | 182 +++++--
 apps/web/src/pages/ForgePage.tsx                  |  21 +-
 apps/web/src/pages/RankedPage.tsx                 |  47 +-
 apps/web/src/pages/ReplayHubPage.tsx              |   1 +
 apps/web/src/pages/ReplayPage.tsx                 |  36 +-
 apps/web/src/pages/TrainingPage.tsx               |  30 +-
 docs/ARCHITECTURE_NOTES.md                        |   8 +-
 docs/HANDOFF_REPORT.md                            |  39 +-
 docs/QA_CHECKLIST.md                              |   8 +-
 docs/decisions.md                                 |  10 +
 scripts/seed_data.py                              | 237 ++++++++-
 services/api/neuroleague_api/routers/analytics.py | 366 +++++++++++++-
 services/api/neuroleague_api/routers/matches.py   |  16 +-
 services/api/neuroleague_api/routers/replays.py   | 433 +++++++++++++++-
 services/api/neuroleague_api/routers/training.py  | 144 ++++++
 19 files changed, 2066 insertions(+), 266 deletions(-)
```

## Automated Snapshot
- Timestamp: `2026-01-18T20:56:27+09:00`
- Git: `daf31c4c968111429ca553e6cce94144a75879f7`
- Recent commits:
- daf31c4 docs(handoff): update metrics, challenges, and packs notes
- 637fe94 test(e2e): cover ops and challenge flows
- f094df2 fix(api): repair ranked queue wrapper
- 8d7dbcf feat(web): add ops dashboard and challenge flow
- 687f50b feat(packs): add pack hash and preflight ops
- Last handoff tag: `handoff/20260118_190758`
- Base for diff: `handoff/20260118_190758`
- Changed files since base:
- Makefile
- apps/web/e2e/first5min.spec.ts
- apps/web/src/App.tsx
- apps/web/src/lib/api.ts
- apps/web/src/lib/experiments.ts
- apps/web/src/pages/ChallengePage.tsx
- apps/web/src/pages/ClipsPage.tsx
- apps/web/src/pages/GalleryPage.tsx
- apps/web/src/pages/HomePage.tsx
- apps/web/src/pages/OpsPage.tsx
- apps/web/src/pages/ReplayPage.tsx
- apps/web/src/pages/StartPage.tsx
- docs/ARCHITECTURE_NOTES.md
- docs/HANDOFF.json
- docs/HANDOFF_REPORT.md
- docs/QA_CHECKLIST.md
- docs/decisions.md
- packages/sim/neuroleague_sim/models.py
- packages/sim/neuroleague_sim/pack_loader.py
- packages/sim/neuroleague_sim/simulate.py
- packs/default/v1/pack.json
- scripts/e2e.sh
- scripts/generate_pack.py
- scripts/metrics_rollup.py
- scripts/patch_preflight.py
- services/api/alembic/versions/0011_metrics_and_experiments.py
- services/api/alembic/versions/0012_challenges.py
- services/api/neuroleague_api/challenges.py
- services/api/neuroleague_api/eventlog.py
- services/api/neuroleague_api/experiments.py
- services/api/neuroleague_api/growth_metrics.py
- services/api/neuroleague_api/main.py
- services/api/neuroleague_api/models.py
- services/api/neuroleague_api/ray_tasks.py
- services/api/neuroleague_api/routers/auth.py
- services/api/neuroleague_api/routers/blueprints.py
- services/api/neuroleague_api/routers/challenges.py
- services/api/neuroleague_api/routers/clips.py
- services/api/neuroleague_api/routers/events.py
- services/api/neuroleague_api/routers/experiments.py
- services/api/neuroleague_api/routers/matches.py
- services/api/neuroleague_api/routers/ops.py
- services/api/neuroleague_api/routers/ranked.py
- services/api/neuroleague_api/routers/share.py
- services/api/neuroleague_api/routers/tournament.py
- tests/test_api_schema.py
- tests/test_challenges.py
- tests/test_content_pack.py
- tests/test_experiments_assignment.py
- tests/test_ops_metrics_api.py
- tests/test_ops_preflight_api.py
- Diff stat since base:
```
 Makefile                                           |   19 +-
 apps/web/e2e/first5min.spec.ts                     |   80 ++
 apps/web/src/App.tsx                               |    4 +
 apps/web/src/lib/api.ts                            |   77 +-
 apps/web/src/lib/experiments.ts                    |   31 +
 apps/web/src/pages/ChallengePage.tsx               |  204 ++++
 apps/web/src/pages/ClipsPage.tsx                   |   65 +-
 apps/web/src/pages/GalleryPage.tsx                 |   23 +-
 apps/web/src/pages/HomePage.tsx                    |   66 +-
 apps/web/src/pages/OpsPage.tsx                     |  290 +++++
 apps/web/src/pages/ReplayPage.tsx                  |   52 +
 apps/web/src/pages/StartPage.tsx                   |    3 +-
 docs/ARCHITECTURE_NOTES.md                         |   41 +
 docs/HANDOFF.json                                  |   32 +-
 docs/HANDOFF_REPORT.md                             |   22 +
 docs/QA_CHECKLIST.md                               |   25 +
 docs/decisions.md                                  |   34 +
 packages/sim/neuroleague_sim/models.py             |    1 +
 packages/sim/neuroleague_sim/pack_loader.py        |  266 +++++
 packages/sim/neuroleague_sim/simulate.py           |    3 +
 packs/default/v1/pack.json                         | 1193 ++++++++++++++++++++
 scripts/e2e.sh                                     |    3 +-
 scripts/generate_pack.py                           |  132 +++
 scripts/metrics_rollup.py                          |   41 +
 scripts/patch_preflight.py                         |  213 ++++
 .../versions/0011_metrics_and_experiments.py       |   92 ++
 services/api/alembic/versions/0012_challenges.py   |  139 +++
 services/api/neuroleague_api/challenges.py         |   10 +
 services/api/neuroleague_api/eventlog.py           |  118 ++
 services/api/neuroleague_api/experiments.py        |  163 +++
 services/api/neuroleague_api/growth_metrics.py     |  379 +++++++
 services/api/neuroleague_api/main.py               |    6 +
 services/api/neuroleague_api/models.py             |  131 ++-
 services/api/neuroleague_api/ray_tasks.py          |   47 +
 services/api/neuroleague_api/routers/auth.py       |   19 +
 services/api/neuroleague_api/routers/blueprints.py |   41 +-
 services/api/neuroleague_api/routers/challenges.py |  488 ++++++++
 services/api/neuroleague_api/routers/clips.py      |   19 +-
 services/api/neuroleague_api/routers/events.py     |   74 ++
 .../api/neuroleague_api/routers/experiments.py     |   60 +
 services/api/neuroleague_api/routers/matches.py    |   77 +-
 services/api/neuroleague_api/routers/ops.py        |  231 +++-
 services/api/neuroleague_api/routers/ranked.py     |   10 +-
 services/api/neuroleague_api/routers/share.py      |  238 +++-
 services/api/neuroleague_api/routers/tournament.py |   30 +-
 tests/test_api_schema.py                           |   10 +
 tests/test_challenges.py                           |   66 ++
 tests/test_content_pack.py                         |   44 +
 tests/test_experiments_assignment.py               |   33 +
 tests/test_ops_metrics_api.py                      |   30 +
 tests/test_ops_preflight_api.py                    |   47 +
 51 files changed, 5458 insertions(+), 64 deletions(-)
```

## Automated Snapshot
- Timestamp: `2026-01-20T08:39:58+09:00`
- Git: `8984061114a8a8248b30d5d23741b629d2253e42`
- Recent commits:
- 8984061 docs(handoff): launch candidate KPIs and checks
- b54a273 chore(ci): upload deploy smoke diagnostics
- cd9165d feat(scheduler): rotate featured daily
- 959a8fe test(e2e): cover build code import to ranked
- f030d24 test(share): assert build share exposes build code
- Last handoff tag: `handoff/20260120_032820`
- Base for diff: `handoff/20260120_032820`
- Changed files since base:
- .github/workflows/ci.yml
- apps/web/e2e/first5min.spec.ts
- apps/web/src/api/types.ts
- apps/web/src/pages/ForgePage.tsx
- apps/web/src/pages/OpsPage.tsx
- docs/HANDOFF.json
- docs/HANDOFF_REPORT.md
- docs/QA_CHECKLIST.md
- docs/RUNBOOK_DEPLOY.md
- scripts/handoff.sh
- scripts/seed_data.py
- services/api/neuroleague_api/featured_rotation.py
- services/api/neuroleague_api/growth_metrics.py
- services/api/neuroleague_api/routers/auth.py
- services/api/neuroleague_api/routers/blueprints.py
- services/api/neuroleague_api/routers/events.py
- services/api/neuroleague_api/routers/matches.py
- services/api/neuroleague_api/routers/ops.py
- services/api/neuroleague_api/routers/share.py
- services/api/neuroleague_api/scheduler_main.py
- tests/test_featured_rotation.py
- tests/test_ops_metrics_api.py
- tests/test_share_landing.py
- Diff stat since base:
```
 .github/workflows/ci.yml                           |  42 ++++-
 apps/web/e2e/first5min.spec.ts                     |  56 ++++++
 apps/web/src/api/types.ts                          |  12 ++
 apps/web/src/pages/ForgePage.tsx                   |  38 ++++
 apps/web/src/pages/OpsPage.tsx                     |  82 +++++++++
 docs/HANDOFF.json                                  |  30 ++--
 docs/HANDOFF_REPORT.md                             |  25 ++-
 docs/QA_CHECKLIST.md                               |   8 +
 docs/RUNBOOK_DEPLOY.md                             |   2 +-
 scripts/handoff.sh                                 |   6 +-
 scripts/seed_data.py                               | 176 ++++++++++++++++++
 services/api/neuroleague_api/featured_rotation.py  | 198 +++++++++++++++++++++
 services/api/neuroleague_api/growth_metrics.py     | 111 ++++++++++--
 services/api/neuroleague_api/routers/auth.py       |  13 ++
 services/api/neuroleague_api/routers/blueprints.py |  59 +++++-
 services/api/neuroleague_api/routers/events.py     |   2 +
 services/api/neuroleague_api/routers/matches.py    |  19 ++
 services/api/neuroleague_api/routers/ops.py        | 114 ++++++++++++
 services/api/neuroleague_api/routers/share.py      |  75 +++++++-
 services/api/neuroleague_api/scheduler_main.py     |   3 +
 tests/test_featured_rotation.py                    | 105 +++++++++++
 tests/test_ops_metrics_api.py                      |  21 +++
 tests/test_share_landing.py                        |  79 ++++++++
 23 files changed, 1225 insertions(+), 51 deletions(-)
```

## Automated Snapshot
- Timestamp: `2026-01-21T23:32:09+09:00`
- Git: `7474b4dc24305bb065ad5f73289d1dccd4d471af`
- Recent commits:
- 7474b4d feat(analytics): shorts variant breakdown + propagation
- 04b99f6 feat(android): TWA wrapper + assetlinks + deeplink events
- 518238b feat(onboarding): first win in 45s share→ranked flow
- 29ebb17 feat(captions): captions_v2 templates + CAPTIONS_VERSION bump
- 149bb08 feat(clips): mint share URLs with clip_len_v1
- Last handoff tag: `handoff/20260121_045048`
- Base for diff: `handoff/20260121_045048`
- Changed files since base:
- .env.deploy.example
- apps/android-twa/.gitignore
- apps/android-twa/app/build.gradle
- apps/android-twa/app/proguard-rules.pro
- apps/android-twa/app/src/main/AndroidManifest.xml
- apps/android-twa/app/src/main/java/com/neuroleague/twa/DeeplinkAnalytics.kt
- apps/android-twa/app/src/main/java/com/neuroleague/twa/MainActivity.kt
- apps/android-twa/app/src/main/res/values/strings.xml
- apps/android-twa/app/src/main/res/values/styles.xml
- apps/android-twa/build.gradle
- apps/android-twa/gradle.properties
- apps/android-twa/gradle/wrapper/gradle-wrapper.jar
- apps/android-twa/gradle/wrapper/gradle-wrapper.properties
- apps/android-twa/gradlew
- apps/android-twa/gradlew.bat
- apps/android-twa/settings.gradle
- apps/web/e2e/first5min.spec.ts
- apps/web/src/lib/experiments.ts
- apps/web/src/lib/shareVariants.ts
- apps/web/src/pages/ClipsPage.tsx
- apps/web/src/pages/HomePage.tsx
- apps/web/src/pages/OpsPage.tsx
- apps/web/src/pages/QuickPage.tsx
- apps/web/src/pages/RankedPage.tsx
- apps/web/src/pages/ReplayPage.tsx
- apps/web/src/pages/StartPage.tsx
- apps/web/vite.config.ts
- docs/RUNBOOK_ANDROID_DEEPLINKS.md
- scripts/seed_data.py
- services/api/neuroleague_api/clip_render.py
- services/api/neuroleague_api/core/config.py
- services/api/neuroleague_api/experiments.py
- services/api/neuroleague_api/growth_metrics.py
- services/api/neuroleague_api/main.py
- services/api/neuroleague_api/routers/auth.py
- services/api/neuroleague_api/routers/clips.py
- services/api/neuroleague_api/routers/events.py
- services/api/neuroleague_api/routers/matches.py
- services/api/neuroleague_api/routers/ops.py
- services/api/neuroleague_api/routers/share.py
- services/api/neuroleague_api/routers/well_known.py
- tests/test_api_schema.py
- tests/test_best_clip.py
- tests/test_clip_share_url.py
- tests/test_ops_metrics_api.py
- Diff stat since base:
```
 .env.deploy.example                                |   7 +
 apps/android-twa/.gitignore                        |  14 +
 apps/android-twa/app/build.gradle                  |  40 +
 apps/android-twa/app/proguard-rules.pro            |   2 +
 apps/android-twa/app/src/main/AndroidManifest.xml  |  40 +
 .../java/com/neuroleague/twa/DeeplinkAnalytics.kt  |  86 ++
 .../main/java/com/neuroleague/twa/MainActivity.kt  |  24 +
 .../app/src/main/res/values/strings.xml            |   7 +
 .../android-twa/app/src/main/res/values/styles.xml |   4 +
 apps/android-twa/build.gradle                      |  22 +
 apps/android-twa/gradle.properties                 |   4 +
 apps/android-twa/gradle/wrapper/gradle-wrapper.jar | Bin 0 -> 43453 bytes
 .../gradle/wrapper/gradle-wrapper.properties       |   6 +
 apps/android-twa/gradlew                           | 249 ++++++
 apps/android-twa/gradlew.bat                       |  92 ++
 apps/android-twa/settings.gradle                   |   3 +
 apps/web/e2e/first5min.spec.ts                     | 927 +--------------------
 apps/web/src/lib/experiments.ts                    |   3 +-
 apps/web/src/lib/shareVariants.ts                  |  55 ++
 apps/web/src/pages/ClipsPage.tsx                   |  35 +-
 apps/web/src/pages/HomePage.tsx                    |   3 +-
 apps/web/src/pages/OpsPage.tsx                     |  78 ++
 apps/web/src/pages/QuickPage.tsx                   |   4 +-
 apps/web/src/pages/RankedPage.tsx                  |   3 +-
 apps/web/src/pages/ReplayPage.tsx                  | 116 ++-
 apps/web/src/pages/StartPage.tsx                   |  11 +-
 apps/web/vite.config.ts                            |   1 +
 docs/RUNBOOK_ANDROID_DEEPLINKS.md                  |  77 ++
 scripts/seed_data.py                               |   2 +
 services/api/neuroleague_api/clip_render.py        |  43 +-
 services/api/neuroleague_api/core/config.py        |   5 +
 services/api/neuroleague_api/experiments.py        |  16 +
 services/api/neuroleague_api/growth_metrics.py     | 237 ++++++
 services/api/neuroleague_api/main.py               |   2 +
 services/api/neuroleague_api/routers/auth.py       |  19 +
 services/api/neuroleague_api/routers/clips.py      | 138 +++
 services/api/neuroleague_api/routers/events.py     |  76 ++
 services/api/neuroleague_api/routers/matches.py    |  18 +-
 services/api/neuroleague_api/routers/ops.py        |  64 ++
 services/api/neuroleague_api/routers/share.py      | 238 +++++-
 services/api/neuroleague_api/routers/well_known.py |  65 ++
 tests/test_api_schema.py                           |   2 +
 tests/test_best_clip.py                            |  27 +
 tests/test_clip_share_url.py                       |  45 +
 tests/test_ops_metrics_api.py                      |   7 +
 45 files changed, 1958 insertions(+), 959 deletions(-)
```
