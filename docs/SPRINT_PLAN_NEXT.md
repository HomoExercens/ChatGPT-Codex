# This Sprint Plan — “Production Hardening × Launch Ops × Creator Pack”

Timestamp: `2026-01-20`  
Baseline (before sprint): `make test` PASS, `NEUROLEAGUE_E2E_FAST=1 make e2e` PASS  
Baseline commit: `bddf3ee`

## Plan
- EPIC D) Production Hardening: request_id/logs/metrics 확장, 최근 1시간 에러 Top N(ops), DB 인덱스/마이그레이션, per-user+per-ip rate limit 보강, CI deploy smoke 진단 강화.
- EPIC E) Launch Ops: funnel(share_v1/clips_v1) 기준 variant별 전환율 ops 노출, featured rotation “내일 미리보기” 추가, Discord daily 루프 템플릿/테스트 보강.
- EPIC F) Creator Pack: `/s/clip` + Replay에서 “Download Kit(zip)” 제공(9:16 MP4 + thumb + caption + QR), 캡션 템플릿 2~3개 추가(결정론+버전), QA/스크린샷/테스트 보강.

## Definition of Done (DoD)
- Determinism 유지: 동일 입력이면 동일 결과/키, 출력이 바뀌면 반드시 versioned key로 분리(예: `CAPTIONS_VERSION`, `CREATOR_KIT_VERSION`).
- Heavy 작업은 `render_jobs`/worker로 처리하고, 동기 경로 폭주 없음(캐시 miss는 202+polling).
- `make test` PASS, `NEUROLEAGUE_E2E_FAST=1 make e2e` PASS.
- Ops에서:
  - 최근 1시간 에러 Top N(엔드포인트/코드) 확인 가능 + request_id로 트레이스 가능
  - funnel + variant별 표본수/전환율이 보임(유의성은 v2)
- Creator Pack zip 다운로드가 되고, zip 구성(4 files) 테스트로 검증됨.

## Risks / Mitigations
- 캡션 템플릿 추가가 기존 캐시를 깨뜨릴 수 있음 → `CAPTIONS_VERSION` bump + cache key 포함(기록은 decisions.md).
- zip 생성이 비결정적으로 변할 수 있음(타임스탬프/파일 순서) → 고정 timestamp + 정렬 + stable zip 옵션 사용.
- 인덱스/마이그레이션이 CI/seed에 영향 → migration + 테스트로 고정, 쿼리 hot path 위주로 최소 추가.

## Rollback
- 새로운 캡션/키트는 versioned asset key로 분리하고, UI는 feature flag/조건부 노출로 즉시 비활성화 가능.
- rate limit은 ENV로 완화/비활성화 가능(보안상 default는 on 유지).
- 인덱스는 안전하게 유지(rollback 시에도 기능 영향 없음).

---

# This Sprint Plan — “Variety × Virality × UGC”

Timestamp: `2026-01-19`  
Baseline (before sprint): `make test` PASS, `make e2e` PASS (`NEUROLEAGUE_E2E_FAST=1`)

## EPIC A) Variation Engine — Portals + Augments
**DoD**
- Pack 기반 `portals[]`/`augments[]` 정의가 `pack_hash`에 포함되고 로드된다.
- match_id 기반으로 portal 1개 + phase(2/4/6)별 augment offers/chosen이 결정론적으로 선택된다(중복 없음).
- DB + replay header + timeline events에 기록되며(구 리플레이는 default/null로 호환), 동일 입력이면 replay digest/highlights/cache key가 동일하다.
- UI: Ranked 카드 + Replay에 portal/augments가 표시된다.
- Analytics/Balance report에 portal/augment pick/winrate가 나오고 low-confidence 처리가 있다.
- Ops weekly theme override에서 portal/augment subset(추천/제한)을 설정할 수 있다.

**Risks / Mitigations**
- 룰 파워 과다: economy 위주로 시작 + combat modifier는 소폭/상한 적용.
- 리플레이 호환: 새 필드는 optional + default.

**Test Plan**
- unit: portal/augment 선택 determinism, replay header 기록, modifier 적용(경제 변수) 확인
- api schema: `/api/meta/portals|augments`, `/api/analytics/portals|augments`
- e2e: ranked match → replay portal/augments 표시 + ops weekly subset 스크린샷

**Rollback**
- Settings 플래그로 modifiers 선택/적용을 즉시 비활성화(기록은 유지 가능).

## EPIC B) Viral Engine v3 — Auto Best Clip(9:16 MP4 + Captions) Prewarm
**DoD**
- match 완료 시(best effort, ranked/challenge 기본) best clip(thumb + 9:16 MP4)이 render_jobs로 자동 enqueue 되고 멱등이다.
- best segment는 highlights[0] 우선, 없으면 중간 10초 fallback이며 결정론적이다.
- captions 텍스트/오버레이가 결정론적으로 생성되며 cache key에 captions_version이 포함된다.
- `/s/clip` 랜딩은 best clip 블록을 최상단에 노출하고 OG는 best thumb 우선(never-404)이다.
- Discord daily post는 가능하면 best clip thumb/share URL을 사용한다(ready 아닐 때 fallback).

**Test Plan**
- unit: best segment selection stable, enqueue idempotent, captions text stable
- api schema: best clip status/urls endpoint
- e2e: match 완료 → best clip ready 확인 + `/s/clip` best 블록 스크린샷

## EPIC C) UGC Engine — Build Code v1 + Import + Lineage + Build of the Day
**DoD**
- Build code 포맷 `NL1_`(canonical JSON → zlib → base64url + checksum)로 encode/decode/import가 된다(길이 제한/에러 메시지 포함).
- Forge에서 “Import Build Code”로 decode preview(warnings) 후 import하여 draft blueprint를 만든다.
- build page에서 “Copy Build Code” + lineage(원본/포크) 표시가 된다.
- Build of the Day가 KST+ruleset_version seed로 결정론적 선정되며 ops override + 최근 7일 history가 있다.
- Home/Discord에서 Build of the Day가 노출/연동된다.

**Test Plan**
- unit: encode/decode roundtrip stable, mismatch warnings stable, daily selection deterministic
- api schema: build code endpoints + build-of-day endpoints
- e2e: Forge import → blueprint 생성 → ranked 큐 → replay + ops build-of-day override 스크린샷

## Required Screenshots (docs/screenshots)
- Replay portal/augments 표시
- Ops weekly theme portal/augment subset UI
- `/s/clip` best clip 블록
- Forge build code import 모달/결과 (`46_forge_build_code_import_modal.png`, `47_forge_build_code_imported.png`)
- Ops build-of-day override (`48_ops_build_of_day_override.png`)

---

# SPRINT PLAN — “Go Viral + Stay Fresh + Operate at Scale”

Timestamp: `2026-01-18`  
Baseline (before sprint): `make test` PASS, `make e2e` PASS (`NEUROLEAGUE_E2E_FAST=1`)

## Goals (User-Perceived)
- Every match feels different (Portals + Augments) and this is visible in replay/UI/analytics.
- Sharing is frictionless: “best clip” is auto-generated, vertical-ready, captioned, and 1‑click shareable.
- UGC loop exists: browse builds → fork/import by build code → submit → play.
- Live ops loop exists: weekly theme + tournament ladder + cosmetic‑only rewards.
- Ops safety improves: background rendering by default, storage abstraction, and balance reporting.

## Epics / Tasks / DoD

### EPIC 1 — Variation Engine (Portals + Augments)
**Tasks**
- Add deterministic definitions (`packages/sim/neuroleague_sim/modifiers.py`) with stable IDs.
- Deterministic selection per match_id, recorded in replay header + timeline events.
- Apply a small set of safe combat‑level rules (start shield, revive‑once, dmg amp, etc).
- Expose portal/augment summary in Ranked cards + Replay + Analytics.

**Definition of Done**
- Same `(match_id, seed_index, blueprints)` ⇒ identical replay digest.
- Replay shows portal + each side’s augments; events include `PORTAL_SELECTED`/`AUGMENT_CHOSEN`.
- `/api/analytics/*` includes portal/augment aggregates (winrate + sample size).

**Risks / Mitigations**
- Risk: replay schema change breaks old replays → make new fields optional with defaults.
- Risk: unbalanced modifiers → start with small tiers and keep “power budget” conservative.

### EPIC 2 — Viral Engine v2 (Auto Best Clip + 9:16 + Captions)
**Tasks**
- Extend clip renderer to support `aspect=9:16` and caption overlays (deterministic).
- Add “best clip” endpoints and auto generation hook at match completion (via `render_jobs` + cache).
- Upgrade share landing to show best clip preview and stable OG meta.
- Add Replay UI section for 1‑click share/download.

**Definition of Done**
- Best clip defaults to `highlights[0]` segment (stable).
- Cache keys include replay.digest + params + aspect + captions_version.
- Cache miss defaults to async jobs (202 + polling); sync only via `async=0` or E2E fast path.

### EPIC 3 — UGC Engine (Gallery + Fork + Build Code + Lineage)
**Tasks**
- Build code encoder/decoder (versioned) based on canonical blueprint JSON.
- API: gallery list + import build code + fork + lineage.
- UI: `/gallery` cards + filters + fork/import flows; integrate into Forge.
- Build of the Day (deterministic daily pick) exposed via API + cached JSON under `artifacts/ops/`.

**Definition of Done**
- A guest can fork/import a build and queue a match in <2 minutes.
- Build codes decode safely (size/format checks).

### EPIC 4 — Live Ops (Weekly Theme + Tournament Ladder + Cosmetics)
**Tasks**
- Weekly theme endpoint (`/api/meta/weekly`) with deterministic rotation (ISO week seed) + override support.
- Tournament queue type + leaderboard endpoints (mode‑separated).
- Cosmetics tables + minimal badges; award participation badge at first tournament match per week.
- UI: `/tournament` page, Home banner, Profile badge section.

**Definition of Done**
- Tournament matches don’t break Ranked/Elo; scoreboard is computed deterministically.
- Cosmetics never affect sim outcome.

### EPIC 5 — Scale/Ops (Storage Abstraction + Balance Report Bot)
**Tasks**
- Storage backend interface (LocalFS default, S3 optional) and wire replay/clip/sharecard to it.
- Balance report script + API (`/api/ops/balance/latest`) + Meta UI summary.
- Add “low confidence” thresholds and clear UI.

**Definition of Done**
- Local works without extra config; S3 backend is optional and gated by env vars.
- Balance report output is deterministic (stable sorting/keys) and safe on empty data.

## Test Plan
- `make test` must PASS after each epic slice; add focused unit tests per epic:
  - modifiers selection determinism + replay schema stability
  - best-clip cache-key determinism + caption rendering sanity
  - build code encode/decode stability + gallery endpoints schema
  - tournament scoring rules + cosmetics awarding idempotency
  - storage backend LocalFS + balance report deterministic output
- `make e2e` must PASS (fast mode preserved); extend E2E minimally:
  - Gallery fork/import flow (fast fixture if needed)
  - Best clip generation UI (job create + poll + preview)
  - Tournament queue once + leaderboard screenshot

## Rollback Plan
- Portals/Augments: gate behind `Settings().enable_modifiers` (default on for dev; can disable quickly).
- Best clip: keep existing clip export endpoints as fallback; disable auto prewarm if needed.
- Gallery/Tournament/Cosmetics: keep routes additive; no breaking changes to existing flows.
- Storage backend: keep LocalFS backend default; S3 backend optional and off by default.
