# QA CHECKLIST — Manual

## Auth
- [ ] `/` 로드: 로그인 카드 + 접근성 설정 패널이 표시됨
- [ ] `게스트로 시작` → `/home` 이동 + 토큰 저장됨(새로고침 후에도 세션 유지 확인)
- [ ] `demo` 로그인(유저명 입력 후 `로그인`) → `/home`
- [ ] `Discord로 계속`(또는 `Continue with Discord`) → (mock/local이면) 즉시 `/home` 진입 + 계정이 guest가 아닌 상태로 전환됨
- [ ] 에러 케이스: 잘못된 유저명으로 로그인 시 에러 메시지 노출

## Home (/home)
- [ ] 상단: Division/Elo 표시
- [ ] Recent Matches가 0개일 때 Empty state 메시지 표시
- [ ] Recent Matches 클릭 → `/replay/{match_id}` 이동
- [ ] CTA: `Quick Battle` 클릭 → (훈련 없이) 랭크 큐 시작 → 완료 시 replay로 자동 이동
- [ ] CTA: `Watch Clips` 클릭 → `/clips` 이동
- [ ] 오프라인(백엔드 종료) 시: 데이터 로드 실패 메시지/에러 표시(브라우저 콘솔 확인 포함)

## Demo Mode (/demo)
- [ ] `NEUROLEAGUE_DEMO_MODE=true`에서 Home 최상단 CTA가 `Play Demo Run (5 min)`로 표시된다
- [ ] `Play Demo Run (5 min)` 클릭 → `/demo` 이동
- [ ] `/demo`에서 3개 preset이 표시된다
- [ ] `Play Demo Run` 클릭 → 1분 내에:
  - [ ] best clip vertical MP4가 표시된다
  - [ ] `Download Kit.zip` 버튼이 표시된다
- [ ] Demo 완료 화면에 CTA가 표시된다:
  - [ ] `Wishlist Now` (Steam store 딥링크/https 폴백)
  - [ ] `Join Discord` (초대 링크)
- [ ] `Download Kit.zip` 다운로드 후 zip 내부에 4개 파일(mp4/thumb/caption/qr)이 있다
- [ ] `Open Replay` → `/replay/{match_id}` 이동
- [ ] `Beat This` → `/challenge/{id}` 이동

## Clips (/clips)
- [ ] 피드 로드: Trending/New + mode(1v1/team) 토글이 동작
- [ ] 세로 비디오(ready) 또는 썸네일(fallback)이 화면 중앙에 표시됨
- [ ] 스크롤/키보드(↑/↓)로 다음/이전 클립 이동
- [ ] Like 버튼: 토글되고 숫자 업데이트(재로딩 후에도 카운트 일관)
- [ ] Share 버튼: `/s/clip/{replay_id}?start=&end=&v=1` 링크가 복사됨
- [ ] Remix 버튼: 포크 생성 후 `/forge?bp=...` 이동
- [ ] Ranked 버튼: 포크→제출→랭크 큐까지 자동 진행되고 `/ranked?auto=1` 경유(또는 동일 UX)로 replay까지 이동
- [ ] Hide 버튼: 해당 클립이 피드에서 숨김 처리됨(새로고침 후에도 유지)
- [ ] Report 버튼: reason 입력 후 성공 토스트/응답(200) 확인

## Training (/training)
- [ ] 초기: `실험 시작` CTA가 보임
- [ ] Mode 토글: `1v1` / `Team (3v3)` 선택이 가능하고, 새 Run 생성 시 선택한 mode로 생성됨
- [ ] Start: `실험 시작` 클릭 → 상태/진행률(%)가 즉시 업데이트(스피너만 있는 상태 금지)
- [ ] Running: 체크포인트가 1개 이상 생성됨(수 초~1분 내)
- [ ] Pause/Resume: `일시정지` → 상태가 Paused로 변경, `재개`로 복귀
- [ ] Stop: `중단` → status가 Stopped로 반영, 이후 새 Run 시작 가능
- [ ] 실패 UX: status Failed일 때 에러 요약 + `Retries: 0` + CTA(Lower budget/Switch plan/View logs) 표시
- [ ] Checkpoints 탭:
  - [ ] `Benchmark` 실행 → W-L-D 결과 + 봇별 W/L/D가 표시됨
  - [ ] `To Blueprint` 실행 → `/forge?bp=...` 이동
  - [ ] Compare A/B 두 개 선택 → matchup diff 패널 표시

## Blueprint Forge (/forge)
- [ ] 딥링크: `/forge?bp=<id>` 진입 시 해당 blueprint 자동 선택됨
- [ ] New: 새 Blueprint 생성 시 mode 선택(1v1/team) 후 생성됨
- [ ] Validate: `Validate` 클릭 → 성공/실패 UX(에러 메시지, 잘못된 팀 구성) 확인
- [ ] Submit: `제출` 클릭 → Ranked에서 선택 가능한 submitted 목록에 반영
- [ ] Submit cooldown: 제출 직후 다시 `제출` 시 429(cooldown) 에러가 발생하고, UI에 `N초 후 제출 가능` 안내가 표시됨
- [ ] Draft Summary:
  - [ ] Training 체크포인트에서 생성된 blueprint를 열면 `Draft Summary` 패널이 보임(있으면 펼쳐보기)
  - [ ] 라운드별 offers/actions(level_up/reroll/buy/pass)와 gold/level 변화가 표시됨
  - [ ] Blueprint meta에 `POLICY`(policy_inference) 또는 `FALLBACK`(fallback_deterministic) 출처가 명시됨
- [ ] 아이템 선택: Weapon/Armor/Utility 슬롯별 옵션 표시 + 변경 즉시 spec 반영
- [ ] 팀 모드: mode=team blueprint에서 3 슬롯 편집 가능(비활성 슬롯은 고정)

## Ranked (/ranked)
- [ ] Mode 탭: `1v1` / `Team (3v3)` 탭이 있고, submitted 목록/매치 히스토리가 mode별로 분리됨
- [ ] submitted blueprint 선택 가능(없으면 Empty 텍스트 표시)
- [ ] `랭크전 입장` 클릭 → 로딩 상태 표시(버튼 disabled)
- [ ] Queue 상태 카드가 표시되고 status가 `queued → running → done/failed`로 변함
- [ ] Progress bar(%)가 0→100으로 증가(동기 완료 금지)
- [ ] PvP 기본:
  - [ ] 매치 카드에 상대 `HUMAN/BOT` 배지가 표시됨
  - [ ] `HUMAN`인 경우 상대 이름 + (가능하면) 상대 Elo가 표시됨
  - [ ] 시드 환경에서 기본적으로 `HUMAN` 매치가 성립(풀 부족 시 BOT fallback은 허용)
- [ ] 실패 시: error_message 표시 + `Retry`/`Clear Active Match` CTA 동작
- [ ] 결과 카드:
  - [ ] result(A/B/draw) 표시
  - [ ] Elo Δ 표시
  - [ ] `Open Replay` 클릭 → `/replay/{match_id}` 이동
- [ ] Matchmaking reason:
  - [ ] 결과/큐 카드에 `Matchmaking: similar Elo, different user` 또는 `pool low, bot fallback`이 표시됨
- [ ] Recent matches 목록 업데이트됨

## Replay Hub (/replay)
- [ ] seeded matches가 목록으로 보임(최소 20개)
- [ ] 항목 클릭 → `/replay/{match_id}` 이동

## Replay Viewer (/replay/:id)
- [ ] 타임라인 스크럽(슬라이더) 동작 + 이벤트 리스트가 tick에 따라 변경
- [ ] Canvas 전투 뷰포트가 표시되고, 스크럽 시 HP/타겟 라인/데미지 오버레이가 즉시 변함
- [ ] 하이라이트 카드 3개가 항상 노출됨
- [ ] `점프` 버튼: 각 하이라이트 start tick으로 이동
- [ ] 타임라인 마커/구간바가 하이라이트와 일치
- [ ] `오버레이` 토글 On/Off 동작
- [ ] 우측 `인사이트` 3줄 표시(승패/피해량/전환점)
- [ ] Team 시너지 tier:
  - [ ] 팀전 리플레이에서 `SYNERGY_TRIGGER` 이벤트 payload에 `threshold(2/4/6)`가 존재
  - [ ] T4/T6 시너지 장면에서 하이라이트 캡션에 `T4`/`T6`가 보이고, `+Sigil`(또는 유사) 표시가 노출됨
- [ ] Clip link:
  - [ ] `Set Start` / `Set End` 클릭 → URL query에 `t=`/`end=`가 반영됨
  - [ ] `Copy Share Link` 클릭 → `/s/clip/{replay_id}?start=&end=` 형태 링크가 복사됨
  - [ ] `Copy App Link` 클릭 → `/replay/{match_id}?t=&end=` 형태 링크가 복사됨
  - [ ] 각각의 링크로 재진입 시 자동 점프(및 end가 있으면 자동 정지) 동작
- [ ] Share landing(OG):
  - [ ] `/s/clip/{replay_id}?start=&end=` 페이지가 HTML로 렌더되고(빈 화면 X) 썸네일/CTA가 보임
  - [ ] 페이지 소스에 `og:title`, `og:description`, `og:image`, `og:url`, `twitter:card` meta 태그가 포함됨
  - [ ] `/s/build/{blueprint_id}` 페이지가 HTML로 렌더되고 OG meta가 포함됨(제출된 빌드만)
  - [ ] `/s/profile/{user_id}?mode=...` 페이지가 HTML로 렌더되고 OG meta가 포함됨
  - [ ] Share landing에서 `Open in App` 클릭 → `/start?next=...`를 경유해 앱 화면으로 이동(토큰 없으면 guest 자동 발급)
- [ ] Clip export:
  - [ ] `Generate Thumbnail` 클릭 → 썸네일 이미지가 프리뷰로 표시됨
  - [ ] `Export GIF` 클릭 → 다운로드 링크가 생기고 파일이 정상 다운로드됨
  - [ ] `Export WebM` 클릭 → 다운로드 링크가 생기고 파일이 정상 다운로드됨
  - [ ] 동일 파라미터로 재요청 시 빠르게 캐시 응답(서버 로그/체감) 확인
- [ ] Share card:
  - [ ] `Share` 클릭 → 생성 상태 후 PNG 다운로드가 시작됨(캐시 hit 시 즉시)
  - [ ] Bookmark: `Bookmark` 클릭 → label prompt → 저장 응답(200) 확인

## Analytics (/analytics)
- [ ] Mode 탭: `1v1` / `Team (3v3)` 전환 시 KPI/차트/테이블이 해당 mode 데이터로 변경됨
- [ ] Coach 카드 3개가 상단에 표시되고(근거/태그/CTA 포함), CTA가 동작함
- [ ] KPI(승/패/무, 승률, Elo/Division) 표시
- [ ] Elo line chart가 실데이터로 렌더링(데이터 0이면 Empty state + CTA)
- [ ] Matchups 리스트가 opponent별 집계로 표시됨
- [ ] Build Insights가 아이템/시너지 사용 빈도/승률 기반으로 표시됨(차트+테이블)
- [ ] Version Compare가 blueprint A/B 선택 시 diff 요약/표로 표시됨

## Meta (/meta)
- [ ] 시즌/룰 버전 배지가 표시됨
- [ ] Patch notes list 표시(더미 가능)
- [ ] Balance Watch(랭크 1v1)가 표시됨:
  - [ ] 데이터가 충분하면 Overperforming/Underperforming 리스트가 5개까지 노출됨
  - [ ] 데이터가 적으면 “Not enough data(need ≥ N)” 안내가 표시됨

## Settings (/settings)
- [ ] 접근성: font scale/contrast/reduce motion/colorblind 토글이 실제 CSS 변수에 반영됨
- [ ] Account: `Connect Discord` 클릭 → Discord OAuth 연결 완료(로컬은 mock 가능)
- [ ] 로그아웃 → `/`로 이동 + 보호 라우트 접근 차단됨

## E2E
- [ ] `make e2e` 실행 → Playwright 테스트 PASS
- [ ] 1v1 + Team 플로우가 모두 자동 완주됨
- [ ] 스크린샷이 `docs/screenshots/01_home.png` … 형태로 생성됨

## Leaderboard (/leaderboard)
- [ ] 모드별(1v1/team) Top 목록이 보임
- [ ] row 클릭(또는 링크) → `/profile/:userId` 이동

## Profile (/profile/:userId)
- [ ] 유저명/guest 뱃지(있다면) 표시
- [ ] Elo/경기수 표시
- [ ] 대표 submitted blueprint 요약(있다면) 표시
- [ ] 최근 경기 10개 리스트가 보이고, 클릭 시 `/replay/{match_id}`로 이동
- [ ] Referrals(자기 프로필):
  - [ ] `Referral rewards`(또는 유사) 섹션에 최근 5개가 표시됨(있을 때)
- [ ] Report profile:
  - [ ] `Report` 버튼 → reason 입력 → 성공 응답 확인

## Social (/social)
- [ ] Following Feed가 로드됨(팔로우가 없으면 Empty state + `Open Leaderboard` CTA)
- [ ] 리더보드/프로필에서 `Follow` 후 `/social`에 이벤트가 표시됨(예: `ranked_done`)
- [ ] feed item 클릭 → href가 있으면 `/replay/{match_id}`로, 없으면 `/profile/{user}`로 이동

## Observability (Request ID + Errors)
- [ ] API 응답에 `X-Request-Id` 헤더가 포함된다(정상/에러 모두)
- [ ] `/ops` → `Recent Errors (last 60m)` 카드가 로드되고 항목이 비어도 UI가 깨지지 않는다
- [ ] `/api/ops/metrics/errors_recent`는 admin token 없으면 차단된다(401/403)
- [ ] `/ops`에 `Next Fest Live` 카드가 보이고 demo completion/5xx/render backlog/alerts 요약이 표시된다(admin token 필요)

## Ops / Storage
- [ ] `make balance-report` 실행 → `artifacts/ops/balance_report_latest.json` + `.md` 생성됨
- [ ] `make ops-clean` 실행 → 오래된 render_jobs가 정리되고 요약(카운트) 출력됨
- [ ] API: `/api/ops/balance/latest?mode=1v1` (또는 `team`) 호출 시 JSON 응답이 온다(빈 데이터도 shape 유지)
- [ ] Public assets allowlist:
  - [ ] `/api/assets/clips/...` / `/api/assets/sharecards/...` 는 파일이 있으면 서빙된다
  - [ ] `/api/assets/neuroleague.db` 는 404(또는 Not found)로 차단된다

## Public Alpha Guardrails
- [ ] Rate limit: clip event(`POST /api/clips/{replay_id}/event`) 폭주 시 `429` + 친절한 에러 payload 반환
- [ ] Rate limit: render jobs(clip/sharecard) 폭주 시 `429` 반환
- [ ] Rate limit: training run 생성 폭주 시 `429` 반환

## Ops Reports (Admin)
- [ ] `NEUROLEAGUE_ADMIN_TOKEN` 설정 후 `GET /api/ops/reports` 호출 시 신고 목록 JSON이 응답됨(헤더 `X-Admin-Token`)
- [ ] 토큰 없거나 틀리면 401/403으로 차단됨

## Ops Moderation Inbox (Admin)
- [ ] Web: `/ops/moderation` 진입 후 admin token 입력 시 목록이 로드됨
- [ ] Resolve: `Resolve` 클릭 → status가 resolved로 변경되고 목록에서 제외(open only)
- [ ] Hide globally: 클릭 → 이후 `/clips` 및 `/gallery`에서 해당 target이 제외됨(새로고침 포함)
- [ ] Soft ban (24h): 클릭 → 해당 유저가 clip/sharecard render job 생성 시 403(soft_banned) 응답
- [ ] `/api/ops/status.reports_pending`가 open reports count와 일치(대략)함

## Docker
- [ ] `docker compose up --build`로 api(8000)/web(3000)가 기동됨
- [ ] Web에서 `/api/*` 및 `/s/*`가 정상 동작(프록시 target 설정 포함)
- [ ] (선택) `make prod-up`로 `docker-compose.prod.yml` 기동 후 web(8080)/api(8000) 동작 확인
- [ ] (배포 레퍼런스) `make deploy-up` 또는 `docker compose -f docker-compose.deploy.yml --env-file .env.deploy up -d --build`
  - [ ] `/api/ready` healthcheck 통과
  - [ ] `/s/*` OG meta의 `og:url/og:image`가 HTTPS base URL로 생성됨
  - [ ] `make deploy-smoke`가 PASS(배포 후 60초 sanity)
  - [ ] `/api/assets/ops/demo_ids.json`이 200/307로 응답하고 JSON에 `clip_replay_id`가 있다

## Share Kit (QR + Caption)
- [ ] `/s/clip/{replay_id}`에서 QR + `Copy App Link`/`Copy Caption`/`Copy for Discord`가 보인다
  - [ ] `Copy Caption` 클릭 시 토스트(예: “Copied caption.”)가 표시된다
- [ ] `/s/build/{blueprint_id}`, `/s/profile/{user_id}`, `/s/challenge/{id}`도 동일하게 QR + copy 버튼이 있다
- [ ] `/s/build/{blueprint_id}`에는 `Copy Build Code`가 있고 `NL1_...` 코드가 노출된다
- [ ] `/s/qr.png?next=...`가 200을 반환하고 ETag가 있으며, `If-None-Match`로 304(캐시) 응답이 된다
- [ ] `/s/clip/{replay_id}/video.mp4`:
  - [ ] `HEAD`가 200을 반환하고 `ETag` + `Cache-Control: public, max-age=31536000, immutable`가 있다
  - [ ] `If-None-Match`로 304(캐시) 응답이 된다
  - [ ] `Range: bytes=0-3` 요청이 206(Partial Content)로 동작한다(모바일 재생 최적화)

## Creator Pack (Download Kit)
- [ ] `/s/clip/{replay_id}`에 `Download Kit` 버튼이 보인다(MP4가 cached 상태일 때)
- [ ] `Download Kit` 클릭 → zip 다운로드가 되고, 압축을 풀면 4개 파일이 있다(mp4/thumb/caption/qr)
- [ ] `/s/clip/{replay_id}/kit.zip`:
  - [ ] `ETag` + `Cache-Control: public, max-age=31536000, immutable`가 있다
  - [ ] `If-None-Match`로 304(캐시) 응답이 된다
- [ ] `/replay/{match_id}` Best Clip 섹션에서 `Download Kit` 링크가 있다(MP4 생성 후)

## Backup / Restore (Deploy)
- [ ] (deploy) `backup` 서비스가 실행 중이고 MinIO에 `backups/pg/...` 오브젝트가 생성된다
- [ ] `/api/ops/status.last_backup_at/last_backup_key`가 채워진다(설정된 경우)
- [ ] `scripts/restore_pg_from_s3.sh`로 최신 백업을 내려받아 복구할 수 있다(스테이징/로컬에서 1회 검증 권장)

## Retention (Optional)
- [ ] `NEUROLEAGUE_ARTIFACTS_RETENTION_ENABLED=true`에서 scheduler가 retention을 실행한다(`ops/retention_latest.json`)
- [ ] `make ops-clean`에서 `--dry-run` / `--keep-shared-days`가 의도대로 동작한다(최근 공유된 assets는 유지)

## Deploy Smoke
- [ ] `NEUROLEAGUE_PUBLIC_BASE_URL=https://<domain> NEUROLEAGUE_ADMIN_TOKEN=<token> make deploy-smoke` → `PASS`

## CI Deploy Smoke (Compose)
- [ ] GitHub Actions에서 workflow `ci.yml`의 job `deploy-smoke-compose`가 green인지 확인한다(WSL 로컬 docker 불필요)
- [ ] 실패한 run의 artifacts에 `deploy-smoke-diagnostics`가 업로드되고, `deploy-smoke.log`/`curl-diagnostics.txt`/docker logs로 원인 파악이 가능하다

## Experiments (A/B)
- [ ] API: `GET /api/experiments/assign?keys=clips_feed_algo,share_cta_copy,quick_battle_default` 응답이 온다(variant/config 포함)
- [ ] Home: `quick_battle_default`에 따라 CTA 강조/순서가 바뀐다(Quick Battle vs Watch Clips)
- [ ] Clips: `clips_feed_algo`에 따라 feed 요청이 `algo=v2|v3`로 바뀐다(네트워크 탭 확인)
- [ ] Clips: `share_cta_copy`에 따라 Remix vs Beat This CTA 강조(버튼 색/우선순위)가 바뀐다

## Challenges (“Beat This”)
- [ ] API: `POST /api/challenges`로 challenge 생성 → `share_url` 반환
- [ ] Share landing: `/s/challenge/{id}`에 OG meta가 포함된다
  - [ ] `og:title`, `og:description`, `og:image`, `og:image:width`, `og:image:height`, `og:url`, `twitter:card`
- [ ] `/s/challenge/{id}`에서 CTA(`Beat This`) 클릭 → `/start?next=/challenge/{id}`로 이동
- [ ] App: `/challenge/{id}`에서 `Beat This` 클릭 → match 큐 시작 → 완료 시 `/replay/{match_id}`로 이동
- [ ] Challenge match는 Elo 업데이트가 없다(랭크 변화 없음) + `queue_type=challenge`

## Ops Metrics + Preflight (Admin)
- [ ] `NEUROLEAGUE_ADMIN_TOKEN` 설정 후 Web `/ops` 진입:
  - [ ] Deploy Sanity 패널이 로드된다(`/api/ops/status`)
  - [ ] Admin token 입력 시 KPI/퍼널/실험 카드가 로드된다(`/api/ops/metrics/*`)
  - [ ] Funnels (daily) 카드가 보이고 오늘/7일 평균/전일 대비가 표시된다(`share_v1`, `clips_v1`)
  - [ ] Alerts 카드가 보이고 최근 알림/상태가 표시된다(`/api/ops/metrics/alerts_recent`)
  - [ ] Preflight 카드가 보이고 `make ops-preflight` 안내 또는 최신 JSON/MD 링크가 보인다(`/api/ops/preflight/latest`)
- [ ] `make ops-metrics-rollup` 실행 후 `/ops`에서 숫자가 업데이트된다(0 → non-zero)
- [ ] API: `GET /api/ops/metrics/funnel_daily?funnel=share_v1&range=7d`가 series를 반환한다(admin-gated)
- [ ] `/ops/packs`:
  - [ ] candidate pack 선택/저장(`/api/ops/packs/candidate`)
  - [ ] promote 실행 시 promotion plan + patch notes가 기록됨(`/api/ops/packs/promote` → `/api/meta/season`)
- [ ] `/ops/weekly`:
  - [ ] 현재 주 테마가 표시됨(`/api/ops/weekly`)
  - [ ] override 저장/clear가 동작하고 `/api/meta/weekly?week_id=` 결과가 바뀜

## Featured Curation (Launch Week)
- [ ] API: `GET /api/featured?active=true`가 정렬(priority desc, created_at desc)된 리스트를 반환한다
- [ ] Ops: `/ops/featured` 로드(토큰 입력/저장) 후 리스트가 보인다
- [ ] Ops: Add Featured로 clip/build/user/challenge 추가가 된다
- [ ] Ops: priority 수정(`Save`)이 반영되고 정렬이 바뀐다
- [ ] Ops: Remove로 삭제된다
- [ ] Feed: `/api/clips/feed` 첫 페이지 상단에 featured clip이 pin 되고 중복이 없다(cap 적용)
- [ ] Home: Featured 섹션(Top Clip/Build/Challenge)이 노출되고 링크가 동작한다

## Quests (Daily / Weekly)
- [ ] API: `GET /api/quests/today`가 daily+weekly를 반환하고 `daily_period_key/weekly_period_key`가 KST 기준으로 맞다
- [ ] Progress: 이벤트 발생 시(clip completion / match done / remix or beat / share) progress_count가 증가한다(중복 event_id는 1회만 반영)
- [ ] Claim: `POST /api/quests/claim`이 완료된 assignment만 성공하고 claimed_at이 저장된다
- [ ] Duplicate reward: 이미 보유한 cosmetic을 다시 claim하면 `wallet.cosmetic_points`가 증가한다(Non‑P2W)
- [ ] Web Home: “Today’s Quests” 카드에서 progress/Claim 버튼이 동작한다
- [ ] Web Profile: 최근 7일 quest history가 표시된다
- [ ] Ops: `/ops/quests`에서 오늘/이번주 set을 확인하고 override가 동작한다

## Discord Launch Loop
- [ ] Ops: `/ops/discord` 로드 후 mode/status(last_post_at/last_error)가 표시된다
- [ ] Ops: “Send test post” 클릭 시(mock 모드에서) payload preview가 렌더된다(외부 Discord 호출 없음)
- [ ] Scheduler/Ensure: daily challenge가 1개 고정으로 생성/재사용되며 `/s/challenge/{id}`가 never-404로 열린다
- [ ] App mode(선택): `POST /api/discord/interactions`가 Ed25519 signature를 검증하고 `/nl top|challenge|weekly|build`가 응답한다
- [ ] Rate limit: Discord 발송은 outbox 큐를 통해 retry/backoff + 429 Retry-After를 존중한다

## Content Packs
- [ ] `packs/default/v1/pack.json`이 존재하고 `pack_hash`가 포함된다
- [ ] replay JSON `header.pack_hash`가 존재한다(새로 생성된 리플레이)
- [ ] `make generate-pack` 실행 시 pack.json이 갱신되고 hash가 안정적으로 재계산된다

## Variation Engine (Portals + Augments)
- [ ] Pack: `pack.json`에 `portals[]`/`augments[]`가 포함되고 `pack_hash`에 반영된다
- [ ] API: `GET /api/meta/portals`, `GET /api/meta/augments`가 현재 pack 기준 리스트를 반환한다
- [ ] Match: ranked 완료 후 replay에서 `portal_id` + augment chosen이 표시된다(구 리플레이는 null/[]로 호환)
- [ ] Replay timeline에 `PORTAL_SELECTED`/`AUGMENT_OFFERED`/`AUGMENT_CHOSEN` 이벤트가 보인다
- [ ] Analytics: `GET /api/analytics/portals`, `GET /api/analytics/augments`가 pick/winrate/sample/low_confidence를 포함한다

## Viral Engine v3 (Auto Best Clip)
- [ ] Match 완료 시 `best_clip`이 생성/캐시된다(thumb + 9:16 MP4, 멱등 enqueue)
- [ ] `GET /api/matches/{id}/best_clip`에서 status/urls가 정상 응답한다
- [ ] `/s/clip/{replay_id}`는 best segment(하이라이트 1순위, 없으면 중간 10초) 기준으로 vertical MP4 블록을 우선 노출한다
- [ ] OG: `/s/clip/{replay_id}`의 `og:image`는 best thumb 우선이며 never-404다

## UGC Engine (Build Code + Lineage + Build of the Day)
- [ ] Build code decode: `POST /api/build_code/decode`가 `{ok,warnings[],mode,ruleset_version,pack_hash,blueprint_spec}`를 반환한다
- [ ] Forge: “Import Build Code”에서 preview(모드/룰셋/팩/경고) 확인 후 Import가 된다
- [ ] Import: `POST /api/build_code/import`가 draft blueprint를 생성하고 lineage에 parent(있으면) 또는 origin_code_hash가 표시된다
- [ ] Lineage: `GET /api/blueprints/{id}/lineage`에 `children_count`(fork 수)와 `origin_code_hash`(external import)가 포함된다
- [ ] Build of the Day: `GET /api/gallery/build_of_day`가 KST 기준 date로 결정론적 결과를 반환한다
- [ ] Ops: `/ops/build-of-day`에서 override 설정/해제가 동작하고 선택 source가 `override`로 표시된다
- [ ] Home: “Build of the Day” 카드가 노출되며 View/Remix/Challenge CTA가 동작한다
