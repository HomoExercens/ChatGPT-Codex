# Decisions

## 2026-01-17 — Repo Layout
- Use the recommended monorepo folders (`apps/`, `services/`, `packages/`) while preserving the original UI export under `ui/`.

## 2026-01-17 — Dev Orchestration
- Provide `make dev` (and scripts under `scripts/`) to bootstrap deps, migrate DB, seed sample data, and start API+Web together.

## 2026-01-17 — Determinism + Replay Digest
- Match RNG uses a single NumPy RNG stream seeded by `sha256(f\"{match_id}:{seed_index}\")`.
- Replay `digest` is `sha256(canonical_json(header + timeline_events + end_summary + highlights))`.

## 2026-01-17 — Elo Draw Policy
- Draws use `score_a = 0.5` (symmetrical) and the same K-factor rule as wins/losses.
- K-factor: `40` for first 20 games, then `32` (per-player, per-mode).

## 2026-01-17 — CPU-Only Torch (WSL/Sandbox)
- Use `torch==2.9.1+cpu` (via `https://download.pytorch.org/whl/cpu`) to avoid CUDA init crashes in Ray/RLlib workers.

## 2026-01-17 — Replay Highlights (Turning Points)
- Highlights are generated from replay timeline events with a simple deterministic scoring model.
- Types: synergy trigger, unit death, damage spike (2s window), HP swing (2s net damage delta).
- Top 3 segments are selected with a minimum gap (0.75s) to avoid overlap; each highlight includes tags for units/items/synergies.

## 2026-01-17 — Ranked Bot Selection
- Ranked queue selects the opponent blueprint from the seeded `bot_%` pool deterministically by `sha256(match_id)` so the matchup is stable for that match id while still varying across matches.

## 2026-01-17 — Seed Data Regeneration
- `scripts/seed_data.py` supports `--reset` (also exposed as `make seed-data-reset`) to delete seeded rows/artifacts and regenerate sample content + replays.

## 2026-01-17 — Content Pack v1 Scope
- Expand sim catalog to 12 creatures, 18 items, and 8+ synergy effects so Training benchmarks and replay variety are meaningful in v1.

## 2026-01-18 — Sharecard v2 Rendering
- Generate share cards via HTML template (UI tokens as CSS variables) → Playwright(Chromium) screenshot → PNG cached under `artifacts/sharecards/`.
- Keep v1(Pillow) as a fallback if Chromium/Playwright rendering fails; v2 is the default path.

## 2026-01-18 — Mode Separation (1v1 / team)
- Treat `mode` as a first-class filter for match history + analytics (`/api/matches?mode=...`, `/api/analytics/*?mode=...`), and ensure seeded data includes both modes for day-0 observability.

## 2026-01-18 — Analytics Coach Cards
- Provide a simple, deterministic “coach” layer (`/api/analytics/coach`) that outputs 3 recommendation cards with evidence (winrate/sample size) and CTAs.

## 2026-01-18 — Economy v1.5 (Draft)
- Draft env is versioned as `neuroleague_draft_parallel_v15` (action space/obs changed) to avoid breaking legacy checkpoints.
- Economy rules(v1.5):
  - Rounds: 6
  - Start gold: 10, round income: +5
  - Shop: 3 creatures + 3 items per round
  - Reroll: cost 1 gold, refreshes current-round offers (deterministic RNG consumption)
  - Level: starts 1, max 5, costs to level up: 1→2=4, 2→3=6, 3→4=8, 4→5=10
  - Rarity odds by level: L1 100/0/0, L2 80/20/0, L3 60/30/10, L4 40/40/20, L5 20/50/30 (r1/r2/r3)
  - Buy costs: creatures r1=4 r2=6 r3=8, items r1=2 r2=4 r3=6

## 2026-01-18 — Synergy Tiers 2/4/6 (Forward-Compatible)
- Synergy definitions use threshold maps (`{2,4,6}`) so future team-size expansions won’t require refactors.
- Sim applies the best threshold ≤ count and emits `SYNERGY_TRIGGER` payload including `count` and `threshold`.

## 2026-01-18 — Catalog Rarity (Creatures/Items)
- `CreatureDef` and `ItemDef` include `rarity: int (1..3)` (default 1).
- Catalog provides deterministic lookup maps (`CREATURES_BY_RARITY`, `ITEMS_BY_RARITY_SLOT`) using sorted IDs for stable RNG sampling.

## 2026-01-18 — Checkpoint → Blueprint via Deterministic Policy Inference
- `to-blueprint` runs RLlib checkpoint policy inference on the draft env and stores the resulting build (not a deterministic placeholder).
- Inference seed: `sha256(f"{run_id}:{checkpoint_id}:{mode}:draft")[:8]` (little-endian u64) so the same checkpoint yields the same draft result.
- Blueprint stores `meta_json` with `draft_env`, `draft_seed`, `draft_log`, and `note=policy_inference`.
- Backward compatibility: if checkpoint restore/action mismatch occurs, fall back to the existing deterministic blueprint method and store `note=fallback_deterministic` with error summary.

## 2026-01-18 — Ranked PvP Matchmaking (Elo-Near, Deterministic)
- Default opponent selection prefers other users’ latest submitted blueprints near the player’s Elo (mode/ruleset separated).
- Selection is deterministic per `match_id`: choose from top-K closest by Elo using `sha256(match_id) % K`; fallback to deterministic bots if the pool is empty.

## 2026-01-18 — Clip Export (Deterministic + Cached)
- Clip assets are rendered server-side from replay JSON (no browser rendering) to keep outputs stable and cacheable.
- Cache keys use `(replay.digest + params)` so identical requests return identical bytes and reuse artifacts.
- Exports:
  - Thumbnail: PNG
  - Clip: WebM (via `imageio-ffmpeg`) and GIF (via Pillow)

## 2026-01-18 — Synergy Amplifiers (“Sigils”) for T4/T6 in 3v3
- Add Utility items with `synergy_bonus: {tag: +N}` so team-mode can reach synergy thresholds 4/6 even with 3 units.
- Bonus only applies once a synergy is already online by base tags (`base_count >= 2`) to avoid “free synergy” exploits in 1v1.
- `SYNERGY_TRIGGER` payload includes `base_count`, `bonus`, `bonus_breakdown`, and `threshold` for spectator clarity.

## 2026-01-18 — PvP Guardrails (Repeat Avoidance + Submit Cooldown)
- Blueprint submit cooldown is enforced server-side (default 120s) per `(user, mode, ruleset)`.
- PvP matchmaking prefers Elo-near humans but applies a deterministic repeat-opponent penalty using recent match history.
- Suspected patterns are recorded as `Event(type="anti_abuse_flag")` for ops visibility (flag-only, not hard bans).

## 2026-01-18 — Share Landing (OG Meta) for Clips
- Add public, server-rendered landing pages under `/s` to provide OG/Twitter meta without relying on SPA JS execution.
- `/s/clip/{replay_id}/thumb.png` never 404s (placeholder until a cached thumbnail exists) and uses absolute URLs built from `request.base_url`.

## 2026-01-18 — Render Jobs (DB-backed + Cached)
- Add `render_jobs` table to track clip/sharecard generation as background work (queued/running/done/failed).
- Default GET endpoints return cached artifacts immediately; on cache miss they create a render job (202) unless `async=0`.
- `NEUROLEAGUE_E2E_FAST=1` runs render jobs synchronously to keep E2E stable while preserving the same API surface.

## 2026-01-18 — Minimal Ops Surface
- Add `/api/meta/season` (ruleset + season name + patch notes), `/api/leaderboard`, and `/api/users/{user_id}/profile`.
- Web routes: `/leaderboard` and `/profile/:userId` for “service-like” navigation from Home/Ranked.

## 2026-01-18 — Storage Backend Abstraction (Local default, S3-ready)
- Introduce a pluggable storage backend (`local` by default) to support future S3/CDN without changing cache keys or determinism logic.
- Store artifact identifiers as stable *keys* relative to `NEUROLEAGUE_ARTIFACTS_DIR` (e.g. `replays/r_*.json`, `clips/...`, `sharecards/...`) while keeping backward-compatible support for legacy absolute paths.
- Public static serving is intentionally limited to shareable artifacts via `/api/assets/*` with an allowlist (`clips/`, `sharecards/`, `ops/`) to prevent leaking the DB file.
- Share landing pages prefer storage `public_url()` for already-rendered clip assets (crawler-friendly, CDN-compatible); never-404 placeholder strategy is preserved for OG thumbnails.

## 2026-01-18 — Balance Report Bot (Deterministic, Ops-friendly)
- Balance snapshots are computed from `matches` (default: `queue_type=ranked`, `ruleset_version=current`) and are deterministic given a fixed timestamp input.
- Metrics are computed from the **A-side** (queueing player) perspective for consistency with ranked UX (`elo_delta_a`, `blueprint_a`, `augments_a`).
- Low-confidence threshold defaults to `50` samples; UI surfaces “not enough data” when below threshold.
- Outputs:
  - Script: `make balance-report` → `artifacts/ops/balance_report_YYYYMMDD.{json,md}` + `balance_report_latest.*`
  - API: `/api/ops/balance/latest` (mode-filterable)

## 2026-01-18 — Clip Feed (Trending/New) + Event Tracking
- Clip unit = replay’s Top1 highlight segment (stored conceptually; `clip_id == replay_id`).
- Feed API:
  - `GET /api/clips/feed?mode=...&sort=trending|new&cursor=...`
- Tracking:
  - `POST /api/clips/{replay_id}/event` with types `view|like|share|fork_click|open_ranked`
  - Use `events` table for metrics events and a dedicated `clip_likes` table for like toggle + counts.
- Trending score:
  - Weighted sum: `views*1 + likes*3 + shares*5 + forks*6 + open_ranked*4`
  - Last 7 days only + exponential time decay (half-life 48h)
  - Dedupe per user/day for views/shares/forks/open_ranked to reduce obvious spam.

## 2026-01-18 — Public OG Pages (Build/Profile)
- Add server-rendered share landings to avoid SPA OG failures:
  - `/s/build/{blueprint_id}` + `/s/build/{blueprint_id}/og.png` (never-404)
  - `/s/profile/{user_id}?mode=...` + `/s/profile/{user_id}/og.png` (never-404)
- OG images reuse cached sharecards when present; otherwise fall back to a placeholder image.

## 2026-01-18 — Public Alpha Rate Limits (In-memory)
- Add a fixed-window, in-memory rate limiter (per-process) for:
  - Training run creation
  - Render job creation (clips/sharecards)
  - Clip feed event tracking
- On exceed: return `429` with a friendly JSON error payload.

## 2026-01-18 — Docker Compose (API + Web)
- Add `docker-compose.yml` for “2 commands to boot” demo runs (api + web + local artifacts volume).
- Vite dev proxy target is configurable via `NEUROLEAGUE_API_PROXY_TARGET` (defaults to `http://127.0.0.1:8000`, Docker uses `http://api:8000`).

## 2026-01-18 — Public Base URL + Proxy Header Trust
- Add `NEUROLEAGUE_PUBLIC_BASE_URL` as the canonical external URL used for OG meta, share URLs, and public asset URLs behind proxies.
- Add `NEUROLEAGUE_TRUST_PROXY_HEADERS` to safely honor `X-Forwarded-Proto/Host` (paired with `NEUROLEAGUE_ALLOWED_HOSTS` allowlist).
- Fallback behavior: if `NEUROLEAGUE_PUBLIC_BASE_URL` is unset, derive absolute URLs from the request (local dev friendly).

## 2026-01-18 — Prod-like Compose (Postgres + MinIO + Ray)
- Keep `docker-compose.yml` dev-friendly, and add `docker-compose.prod.yml` for a more prod-like split:
  - `db` (Postgres), `minio` (S3-compatible), `rayhead` + `worker` (Ray cluster), `api`, `web` (nginx static)
- Default storage backend in prod compose is S3 (MinIO) via `NEUROLEAGUE_STORAGE_*` env.

## 2026-01-18 — Share Deep-Link Start Route (/start)
- Implement a SPA `/start?next=...&ref=...` route to:
  - auto-issue a guest token if missing,
  - preserve `device_id` + `ref` attribution,
  - prevent open redirects by only allowing same-origin relative paths.

## 2026-01-18 — Referral Rewards (Cosmetics, Anti-Abuse)
- Referral is created at guest issuance time when `ref` is present (`POST /api/auth/guest`).
- Credit is granted on the **first ranked completion** (based on `rating.games_played==0` before update) to avoid farming via non-ranked actions.
- Anti-abuse:
  - device-based “one credit per device” gate
  - IP-based daily credit soft-cap (default 3) to reduce obvious abuse without blocking shared networks too aggressively

## 2026-01-18 — Clips Trending v2 (Conversion-Weighted)
- Keep `algo=v1` compatible and introduce `algo=v2` for the feed ranking.
- Add a new event type `completion` (>=80% watch) and increase weight for `fork_click`/`open_ranked`/`completion` to optimize “clip → remix/ranked” conversion.

## 2026-01-18 — Trust/Safety MVP (Report + Hide)
- Add `reports` table and `/api/reports` endpoint for clip/profile/build reporting.
- Add per-user clip hide via `user_hidden_clips` and `POST /api/clips/{replay_id}/hide` (feed respects hide).
- Admin-only ops listing via `GET /api/ops/reports` gated by `NEUROLEAGUE_ADMIN_TOKEN` + `X-Admin-Token`.

## 2026-01-18 — Matchmaking Explainability + KPI
- Expose `matchmaking_reason` in match responses:
  - human: `similar Elo, different user`
  - bot: `pool low, bot fallback`
- Expose `human_match_rate` / `human_matches` in `GET /api/analytics/overview` summary to quantify PvP pool health for a player.

## 2026-01-18 — Ops Cleanup (Render Job TTL)
- Add `make ops-clean` to clean up render job records:
  - mark queued/running older than 12h as failed (“orphaned”)
  - delete done/failed older than 7d
  - optional `--purge-artifacts` to delete local cache files (local backend only; off by default)

## 2026-01-18 — Growth Metrics + Experiments (A/B)
- Canonical event endpoint: `POST /api/events/track` (서버가 device/session/ip/ua hash를 채움).
- Deterministic assignment:
  - `GET /api/experiments/assign?keys=...`는 user_id/guest_id 기반 hash로 variant를 결정론적으로 선택.
  - 배정은 `ab_assignments`에 저장되어 “동일 유저는 항상 동일 variant”를 보장.
- Rollups:
  - `scripts/metrics_rollup.py` (`make ops-metrics-rollup`)가 `metrics_daily`/`funnel_daily`에 일별 집계를 저장.
  - ops API는 rollup 테이블을 읽는 방식으로 운영 부담을 낮춤(데이터가 없을 때도 0/빈 리스트로 안정 응답).
- Web 적용(최소 3개):
  - `clips_feed_algo`: `v2` vs `v3` (feed ranking 파라미터)
  - `share_cta_copy`: `beat_this` vs `remix` (Clips CTA 강조)
  - `quick_battle_default`: `quick_battle` vs `watch_clips` (Home CTA 강조/순서)

## 2026-01-18 — Challenges (“Beat This”)
- Challenge는 “타겟(build|clip)”과 “룰(모드/portal/augments)”을 고정한 shareable object로 저장.
- Determinism:
  - attempt match_id는 `(challenge_id, challenger_id, attempt_index)` sha256 기반으로 파생(재현 가능).
  - clip segment는 최대 12초로 clamp(링크 안정 + 비용 통제).
- Queue semantics:
  - `queue_type="challenge"`로 분리하고 Elo 업데이트는 기본 off(update_ratings=False)로 공정성/운영 단순화.
- Share landing:
  - `/s/challenge/{id}`는 OG meta 포함 HTML을 반환하고 CTA는 `/start?next=/challenge/{id}`로 앱 딥링크(토큰 없으면 guest 자동 발급).

## 2026-01-18 — Content Packs + Patch Preflight
- Pack snapshot:
  - `packs/default/v1/pack.json`을 “ruleset content pack”의 최소 단위로 정의.
  - `pack_hash`는 pack JSON에서 `created_at`/`pack_hash`를 제외하고 canonical sort 후 sha256.
- Replay traceability:
  - 새로 생성되는 replay `header.pack_hash`에 active pack_hash를 기록(캐시 키/리플레이 재현 추적에 사용).
  - 구버전 replay는 pack_hash가 없을 수 있으며(None), 레거시 catalog로 계속 재생 가능.
- Preflight:
  - `scripts/patch_preflight.py` (`make ops-preflight`)는 baseline vs candidate pack을 비교해 deterministic seeds로 winrate delta를 계산하고 `ops/preflight_latest.*`로 저장.
  - ops 조회: `GET /api/ops/preflight/latest` (admin token gate) + 공유 가능한 asset 링크(`/api/assets/ops/...`).

## 2026-01-18 — Deploy Compose (Single VPS Reference)
- Public alpha 배포 레퍼런스는 `docker-compose.deploy.yml`을 “정답”으로 둔다:
  - reverse proxy: Caddy(HTTPS 자동)
  - db: Postgres
  - storage: MinIO(S3-compatible) + public read bucket
  - compute: Ray head + worker
  - scheduler: metrics/balance 주기 실행(옵션)
- 배포에선 `NEUROLEAGUE_PUBLIC_BASE_URL` + `NEUROLEAGUE_TRUST_PROXY_HEADERS=true`를 기본으로 사용해 `/s/*` OG absolute URL이 HTTPS 도메인으로 고정되게 한다.

## 2026-01-18 — Ops Status (Deploy Sanity)
- 운영자 확인용으로 admin-gated `GET /api/ops/status`를 추가하고 Web `/ops`에서 “Deploy Sanity” 패널로 노출한다.
- Ray는 로컬/테스트에서 자동 기동하지 않도록:
  - `NEUROLEAGUE_RAY_ADDRESS`가 있으면 연결/노드 확인,
  - 없으면 `not_initialized`로 표시(강제 init 금지).

## 2026-01-18 — Discord OAuth (Guest Upgrade)
- Discord OAuth는 optional이며, 미설정(local/dev/e2e)에서는 외부 의존을 피하기 위해 mock 경로를 사용한다:
  - `NEUROLEAGUE_DISCORD_OAUTH_MOCK=true` 또는 `NEUROLEAGUE_DISCORD_CLIENT_ID` 미설정 → `/api/auth/discord/start`가 mock callback으로 redirect.
- Guest → Discord 연결 정책(최소/실용):
  - guest 유저가 Discord 연결 시 동일 레코드에 `discord_id`를 부여해 “승격”.
  - 이미 동일 `discord_id`를 가진 계정이 있으면 guest 데이터를 그 계정으로 merge 후 guest 삭제(blueprints/training_runs/wallet/cosmetics/likes/hides/referrals 등을 가능한 범위에서 이관).

## 2026-01-18 — Follow + Activity Feed
- Follow는 toggle로 단순화: `POST /api/users/{id}/follow` (self-follow 금지).
- Following feed는 server-side 이벤트(`events` table) 기반으로 구성하고, 허용 타입만 노출한다:
  - `ranked_done`, `tournament_done`, `blueprint_submit`, `clip_share`, `clip_completion`, `challenge_done`
- Rate limit은 in-memory fixed-window(프로세스 단위)로 시작하고, deploy에서는 Redis로 교체 가능하도록 인터페이스 분리를 유지한다(현 sprint에서는 in-memory 유지).

## 2026-01-18 — Weekly Theme Override (Admin)
- `/api/meta/weekly`는 ISO week seed 기반 deterministic rotation을 기본으로 한다.
- 운영 override는 storage backend key `ops/weekly_theme_override.json`에 저장하며 admin-gated ops API로 제어한다:
  - `GET /api/ops/weekly`
  - `POST /api/ops/weekly/override`

## 2026-01-18 — Packs Promotion (Admin Workflow)
- Pack 선택은 ruleset_version 기반 파일 구조를 우선한다:
  - `packs/<ruleset_version>/pack.json` 또는 `packs/<ruleset_version>/v1/pack.json` → 없으면 `packs/default/v1/pack.json` fallback.
- 운영 워크플로는 “즉시 적용” 대신 “승인/가이드”를 기본으로:
  - candidate: `ops/pack_candidate.json`
  - promotion plan: `ops/pack_promotion_latest.json`
  - patch notes append: `ops/patch_notes.json` → `/api/meta/season.patch_notes`에 합쳐 노출
- 실제 적용은 배포 설정(`NEUROLEAGUE_ACTIVE_RULESET_VERSION` 또는 `ACTIVE_RULESET_VERSION`) + 이미지/볼륨에 pack 파일 포함 + 재시작으로 수행한다(결정론/리플레이 재현성 보호 목적).

## 2026-01-18 — Deploy Smoke (Curl-Based)
- 배포 직후 “60초 내 sanity”를 자동화하기 위해 `scripts/deploy_smoke.sh`를 표준으로 둔다(`make deploy-smoke`).
- Smoke는 web origin 기준으로 `/api/*` + `/s/*` + `/start`를 함께 검사한다(Caddy/Vite proxy 환경에 동일하게 적용 가능).
- Seed replay 선택은 안정성을 위해:
  - 우선 `/api/assets/ops/demo_ids.json`의 `clip_replay_id`,
  - 없으면 `/api/clips/feed?limit=1`의 `replay_id` fallback.

## 2026-01-18 — Seed On Boot + Demo IDs
- Public alpha에서 “빈 서버처럼 보이지 않게” 하기 위해 deploy compose는 `NEUROLEAGUE_SEED_ON_BOOT=1`을 기본으로 둔다.
- Seed는 파괴적 reset이 아닌 idempotent `scripts/seed_data.py` 실행을 기본으로 한다(재시작 시 데이터 유실 방지).
- Seed 스크립트는 안정적인 deep link/스모크 테스트를 위해 `ops/demo_ids.json`을 항상 갱신한다(공개 allowlist: `/api/assets/ops/...`).

## 2026-01-18 — Backups (Postgres → MinIO/S3)
- 백업은 “로컬 파일”이 아니라 storage backend(S3/MinIO)에 올리는 것을 표준으로 둔다:
  - `scripts/backup_pg_to_s3.sh`: `pg_dump` 업로드 + 최근 N개 유지 + `ops/last_backup.json` 기록.
  - `scripts/restore_pg_from_s3.sh`: 최신(또는 지정 key) 다운로드 후 `pg_restore --clean`.
- Deploy에는 `backup` 서비스(일일 루프)를 추가하고, `/api/ops/status`에서 `last_backup_at/key`를 노출한다.

## 2026-01-18 — Artifact Retention (Safe by Default)
- retention은 기본 OFF(`NEUROLEAGUE_ARTIFACTS_RETENTION_ENABLED=false`)로 두고, scheduler에서 주기 실행한다.
- “공유된 링크가 깨지는” 사고를 줄이기 위해 최근 `share_open` 이벤트 기반의 keep-shared guard(`KEEP_SHARED_DAYS`)를 둔다.
- 삭제는 storage backend `delete()`를 통해 LocalFS/S3 모두 지원한다.

## 2026-01-18 — Ops Moderation Inbox (Resolve/Hide/Soft Ban)
- 운영자 UX는 `/ops/moderation`을 표준으로 둔다(목록/상세/액션 최소 셋).
- 글로벌 hide는 `moderation_hides`로 저장하고 feed/gallery에서 필터링한다(“개인 숨김”과 분리).
- soft ban은 “차단”이 아니라 비용 폭탄을 막는 최소 가드로:
  - clip/sharecard render job 생성만 403으로 막는다(게임 플레이/관전은 유지).

## 2026-01-18 — Ops Experiments Reporting (Variant KPI)
- 실험은 “fork만” 보지 않고, 퍼널 KPI(clip_completion, clip_open_ranked, replay_open, ranked_done 등)를 variant별로 함께 표기한다.
- 통계 유의성 계산은 v1 scope 밖으로 두고, 표본수/차이를 명확히 보이게 하는 것을 우선한다.

## 2026-01-18 — Share Landing Conversion CTA
- `/s/*`는 crawler-friendly(SSR HTML) + never-404 OG image를 유지하면서,
  - “Play in ~30 seconds” above-the-fold 문구,
  - “Copy for Discord” 버튼(짧은 템플릿)으로 전환 마찰을 줄인다.
- CTA 클릭은 별도 public 이벤트 엔드포인트를 만들지 않고, `/start → /api/auth/guest` 요청 payload에 `source/next/utm`을 포함해 서버에서 기록한다(`share_cta_click`, `guest_start_success`).

## 2026-01-19 — Featured Curation (Launch Week)
- Launch week 콘텐츠 품질 고정을 위해 운영자가 clip/build/user/challenge를 “Featured”로 고정할 수 있게 한다.
- 모델: `featured_items(kind, target_id, title_override, priority, starts_at, ends_at, status)`
  - 정렬: `priority desc`, 동률은 `created_at desc`
  - 스케줄: `starts_at/ends_at`(UTC) 범위 내에서 `status=active`가 노출 대상
- Feed 통합:
  - `/api/clips/feed` 첫 페이지 상단에 featured clip을 pin (cap: `min(3, limit-1)`)
  - 호환성을 위해 feed item에 `featured?: true`만 optional로 추가

## 2026-01-19 — Quests (Daily/Weekly, KST Deterministic Sets)
- Period key:
  - daily: Asia/Seoul 기준 `YYYY-MM-DD`
  - weekly: Asia/Seoul 기준 ISO week `YYYYW##`
- Quest set(3개)은 결정론적으로 선택한다:
  - seed: `cadence|period_key|ruleset_version`
  - 정렬: `sha256(seed|quest.key)` 오름차순
  - 운영 override: storage backend key `ops/quests_override.json`
- Progress는 서버 이벤트 기반으로 누적하며(event ingest 시 업데이트), 중복 적용은 `quest_events_applied(event_id, assignment_id)`로 idempotency 보장.
- Reward 정책:
  - 기본 보상은 cosmetic badge 1개
  - 이미 보유한 cosmetic은 stack 대신 `wallet.cosmetic_points`로 전환(Non‑P2W 유지)

## 2026-01-19 — Discord Launch Loop (Webhook/App/Mock)
- 모드:
  - default: webhook-only (`DISCORD_MODE=webhook` 또는 `NEUROLEAGUE_DISCORD_MODE=webhook`)
  - app mode: interactions endpoint + 서명검증(Ed25519)
  - mock: 로컬/e2e에서 외부 Discord 호출 없이 payload 검증/미리보기
- Outbox/Rate limit:
  - Discord 발송은 `discord_outbox`(DB) 큐로만 수행하고, retry/backoff + 429 Retry-After를 존중한다.
  - Scheduler가 outbox drain + daily challenge ensure + daily post enqueue를 수행한다.
- Daily challenge:
  - KST 날짜 + ruleset_version 기반으로 `ch_daily_<hash>` challenge id를 결정론적으로 생성/재사용한다.
  - 노출/연결은 `featured_items(kind="challenge")`로 관리한다.
- App mode interactions:
  - `POST /api/discord/interactions`에서 Discord signature를 검증(cryptography)하고 `/nl top|challenge|weekly|build`를 제공한다.

## 2026-01-19 — Build Code v1 (UGC Share/Import)
- Prefix:
  - 기존 호환을 위해 `NL1_`를 유지한다(`NL1:`로 변경하지 않음).
- Encode:
  - canonical blueprint payload(JSON) → zlib(level=9) → base64url → checksum(sha256(json)[:8])
  - payload 필드: `v=1`, `ruleset_version`, `mode`, `spec`, (optional) `pack_hash`
- Decode:
  - 길이 제한(32KB) + decompressed payload 제한(128KB) + checksum 검증으로 악성/초대형 입력을 방지한다.
  - `POST /api/build_code/decode`는 mismatch를 **에러가 아닌 warnings**로 반환한다(ruleset/pack_hash 등).
- Import:
  - `POST /api/build_code/import`는 draft blueprint를 생성한다.
  - ruleset mismatch는 안전을 위해 서버 ruleset_version으로 import하며(warning 기록), lineage는 동일 `spec_hash`의 submitted blueprint가 있으면 `forked_from_id`로 연결한다.
  - 외부 import는 `blueprints.origin_code_hash`(sha256(build_code))로 추적한다.

## 2026-01-19 — Build of the Day (KST Deterministic + Ops Override)
- 기준:
  - date key는 Asia/Seoul(KST) 기준 `YYYY-MM-DD`.
  - seed는 `"{ruleset_version}:{mode}:{date_key}"`로 고정하여 같은 날/같은 DB 상태에서 결과가 안정적이다.
- Auto pick:
  - 제출된(submitted) 최신 빌드(유저당 1개) 중 표본이 충분한 후보(>=5 matches)에서 top pool을 구성하고 seed로 1개를 선택한다.
- Ops override:
  - override는 storage backend key `ops/build_of_day_override.json`에 저장하고(`/api/ops/build_of_day/override`), public 응답은 override를 우선한다.
- Discord:
  - daily post의 “Build of the Day”는 BOTD를 우선 사용하고(없으면 featured build → demo fallback), 외부 링크는 `/s/build/{id}`를 사용한다.

## 2026-01-20 — Request IDs + Ops Recent Errors
- 모든 API 응답에 `X-Request-Id`를 포함한다(요청 헤더가 있으면 재사용, 없으면 생성).
- 최근 60분 에러(엔드포인트/상태 코드)를 프로세스 메모리에 보관하고, admin-gated ops endpoint + `/ops` 카드로 노출한다.
- 주의: in-memory 집계이므로 다중 프로세스/다중 인스턴스 환경에서는 “노드별”로만 관측된다(v2에서 외부 스토어/로그 집계로 확장).

## 2026-01-20 — Dual Rate Limits (User + IP) + Retry-After Consistency
- 비용이 큰 엔드포인트는 `user_id` 기반 + `ip_hash` 기반 2중 rate limit을 적용한다(ENV로 조절).
- `429`는 payload에 `retry_after_sec`를 포함하고, HTTP 헤더 `Retry-After`도 일관되게 제공한다.

## 2026-01-20 — Creator Pack “Kit” Zip (Deterministic)
- 공유 랜딩에서 “다운로드 한 방”을 위해 `/s/clip/{replay_id}/kit.zip`을 추가한다(4개 파일: mp4/thumb/caption/qr).
- 결정론:
  - `CREATOR_KIT_VERSION=kitv1`를 cache key에 포함한다.
  - kit key는 `mp4 cache_key`(caption version/template 포함), `thumbnail cache_key`, `SHARE_CAPTION_VERSION`, caption hash, QR etag seed로 구성한다.
  - zip은 고정 timestamp + `ZIP_STORED` + 안정 파일 순서로 바이트가 안정되도록 한다.

## 2026-01-20 — Best Clip Captions capv4
- 템플릿 추가로 `match_id % N` 선택 결과가 변하므로 `CAPTIONS_VERSION`을 `capv3 → capv4`로 bump한다(캐시 키에 포함됨).
- Clutch 판정은 winner HP `<=5`로 확장하고, Portal/Augment 강조 템플릿을 추가한다.
- Upset(Elo 차) 템플릿은 보류: replay payload에 Elo 정보가 없어서 DB lookup 또는 schema 확장이 필요하다.

## 2026-01-21 — Steam Demo Mode + Guided Run
- 데모는 “첫 60초에 결과(리플레이/클립/키트)”가 나오게 한다.
- 토글:
  - `NEUROLEAGUE_DEMO_MODE=true|false`
  - enabled 시 Home 최상단 CTA를 `/demo`로 유도하고, Training은 “Later”로 뒤로 미룬다(기존 플로우는 유지).
- 서버 API:
  - `GET /api/demo/presets` — 고정 3개 프리셋(버전: `DEMO_PRESETS_VERSION`)
  - `POST /api/demo/run` — **결정론적** demo match/replay/challenge 생성(버전: `DEMO_RUN_VERSION`)
  - demo match_id/replay_id/challenge_id는 `(DEMO_RUN_VERSION, preset_id, user_id)` 기반 sha256로 파생(랜덤 금지).

## 2026-01-21 — Best Clip Share Cache Alignment (0.1s)
- 공유 URL은 짧고 안정적으로 유지하기 위해 `start/end`는 0.1s 해상도를 사용한다.
- `/api/matches/{match_id}/best_clip_jobs`가 생성하는 clip/thumbnail render job도 동일한 0.1s range로 정규화해:
  - `/s/clip/*/video.mp4` 및 `/s/clip/*/kit.zip`와 **동일 cache_key**를 사용하게 한다(share assets cache hit 증가).

## 2026-01-21 — Multi‑Instance Safety (Scheduler/Discord/Ops Errors)
- 분산 락: Postgres advisory lock을 사용해 scheduler의 핵심 job이 1회만 실행되게 한다(락 키는 stable hash).
- Discord outbox drain은 `FOR UPDATE SKIP LOCKED`로 multi-instance 중복 전송을 방지한다.
- Ops recent errors는 in-memory 대신 DB 테이블(`http_error_events`)에 저장해:
  - multi-instance에서도 `/ops` “최근 60분 에러” 카드가 일관되게 집계된다.

## 2026-01-21 — KPI Drop Alerts (Discord, Cooldown)
- 목적: funnel 급락/5xx spike/render backlog를 운영자가 즉시 인지하되 스팸을 방지한다.
- 정책(초기값):
  - funnel drop: today < (prev 7d avg * 0.6) AND 표본 >= 30
  - 5xx spike: last 15m >= 5
  - render backlog: queued+running >= 200
  - cooldown: 동일 `alert_key`는 2시간 쿨다운(`alerts_sent` audit 테이블)
- 전송 경로:
  - Discord outbox에 `kind="alert"`로 enqueue
  - webhook은 `NEUROLEAGUE_ALERTS_DISCORD_WEBHOOK_URL`가 있으면 우선 사용(없으면 기본 webhook fallback)

## 2026-01-21 — Steam Wishlist/Discord CTA (Demo Completion)
- 데모 완주 화면을 “위시리스트 전환”의 핵심 surface로 고정한다.
- 설정:
  - `NEUROLEAGUE_STEAM_APP_ID` (없으면 CTA를 숨기지 않고 기본값/폴백을 사용; 배포 시 반드시 설정)
  - `NEUROLEAGUE_DISCORD_INVITE_URL`
- 이벤트:
  - `wishlist_click`, `discord_click` (ops rollup에서 users 카운트로 관측)

## 2026-01-21 — Steam Desktop Demo Packaging (Electron + Embedded Python)
- 목적: “Windows에서 더블클릭 → 30초 내 데모 완주”를 위해 web+api를 로컬로 묶는다.
- 선택: Electron wrapper (`apps/desktop`) + python.org embeddable Python + `requirements-desktop.txt`
- CI에서 Windows artifact를 생성한다(`.github/workflows/build-desktop-windows.yml`).
- Desktop UX:
  - API(uvicorn) + web(dist)를 로컬에서 띄우고 `http://127.0.0.1:<port>`를 로드
  - 외부 링크(steam/https)는 Electron main process에서 `shell.openExternal()`로 처리한다

## 2026-01-21 — E2E FAST: Disable Ray for Match Jobs
- 문제: Ray local instance의 GCS가 불안정하게 종료되면 driver 프로세스가 terminate될 수 있어, e2e가 flake가 된다.
- 정책: `NEUROLEAGUE_E2E_FAST=1`에서는 ranked/challenge match 실행을 Ray 대신 in-process sync runner로 수행한다.
- 영향:
  - e2e/로컬 테스트 안정성 ↑
  - prod/compose 환경(기본)에서는 기존대로 Ray worker 경유를 유지한다.
