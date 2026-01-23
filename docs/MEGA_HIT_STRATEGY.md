# MEGA HIT STRATEGY — NeuroLeague as “UGC Build Sport”

## 1) One‑sentence thesis
NeuroLeague는 “빌드를 만들고(Forge) → 겨루고(Ranked) → 공유하고(/s/*) → 남의 빌드를 개조해 내 빌드로 만드는(Remix)” 과정을 스포츠처럼 반복하게 만들어, **UGC(빌드) 자체가 네트워크 효과를 만드는 게임**이다.

## 2) Why “UGC Build Sport” wins
### (A) 콘텐츠 단위가 짧고, 측정 가능하다
- 단위: `Blueprint`(빌드)와 `Replay/Clip`(결과/하이라이트)
- 결과가 즉시 수치화됨: Elo, 승률, 매치업, 리플레이 digest(결정론)
- 공유 가능 단위가 명확함: `/s/clip/{replay_id}`와 `/s/build/{blueprint_id}`

### (B) “창작 → 경쟁 → 확산”의 순환이 자연스럽다
1. 창작(Forge/Training): “내 빌드”를 만든다.
2. 경쟁(Ranked/Tournament): “내 빌드가 통하는지” 검증한다.
3. 확산(Share/Clip Feed): “재현 가능한 증거(clip)”로 공유한다.
4. 파생(Remix): 남이 만든 걸 가져와 “내 버전”을 만든다.
5. 다시 경쟁 → 다시 공유 → 다시 Remix…

### (C) 리믹스는 네트워크 효과의 핵심 메커니즘이다
- **포크(부모 1명 + 자식 다수)** 구조는 “밈/메타의 계보”를 만든다.
- “원본 → 파생”이 기록되면, 인기 빌드가 “더 많이 개조될수록 더 눈에 띄는” 자기강화 루프가 생긴다.

## 3) Remix Flywheel v1 (이번 릴리즈)
### 제품 루프
1) 유저가 공유 랜딩(`/s/clip/{replay_id}`) 또는 클립/리플레이 뷰에서 **Remix**를 누른다.  
2) 원본 `Blueprint`의 `spec_json`을 복제해 **내 Blueprint(포크)** 를 만든다.  
3) 포크된 Blueprint는 Forge에서 즉시 편집 가능하며, **Lineage(계보)** 가 보인다.  
4) 포크/리믹스 활동은 이벤트로 기록되어 **롤업/트렌딩**에 반영된다.

### v1에서 확보한 “제품 레버”
- **마찰 제거**: 공유 랜딩에서 바로 Remix → (로그인/게스트 생성) → 자동으로 Forge 진입
- **계보 가시화**: “내 빌드가 어디서 왔는지”와 “내 빌드가 얼마나 리믹스됐는지”를 한 화면에서 확인
- **측정/최적화 가능**: fork_click/fork_created 이벤트 + remix_v1 퍼널로 병목을 찾고 개선
- **트렌딩 신호 추가**: “리믹스가 많이 일어나는 클립”을 더 강하게 띄워 전환을 강화

## 4) NSM/KPI (무엇을 성공으로 볼 것인가)
### North Star Metric (추천)
- **WAU Remixes**: 주간 `fork_created`(또는 unique creators)  
  - 해석: “이번 주에 실제로 몇 번 리믹스가 ‘생성’되었는가”

### 핵심 KPI
- **Remix CTR**: `fork_click_events / share_open_users` (또는 share_open_events 기반)  
- **Remix Conversion**: `fork_created_events / fork_click_events`  
- **Remix → Play**: `first_match_done_users` 중 remix_v1 퍼널에 포함된 비율  
- **Retained Creators**: 7일 내 “리믹스 생성자” 재방문/재리믹스

### 어디서 보나 (현재 파이프라인)
- Rollup: `scripts/metrics_rollup.py` → `metrics_daily`/`funnel_daily`
- Ops API:
  - `/api/ops/metrics/summary` (daily metrics)
  - `/api/ops/metrics/funnel` (funnel steps; includes `remix_v1`)
- v1 추가 지표(키):
  - `fork_click_events`
  - `fork_created_events`
  - Funnel: `remix_v1` = `share_open → fork_click → fork_created → first_match_done`

## 5) 다음 단계 로드맵 (v2+)
### v2: Guest Try Remix (더 큰 상단 퍼널)
- 목표: 로그인/게스트 생성 이전에도 “한 번은” 빌드를 만져볼 수 있게
- 방향:
  - `/remix`에서 즉시 “간단 편집(프리셋/슬롯 1개 변경)”을 허용하고, 저장/랭크 진입 시점에 계정 생성
  - 또는 “임시(guest) Blueprint”를 서버에서 생성 후, 저장/공유 시 정식 계정으로 승격

### v2: Creator Profile & Lineage Surfacing
- 목표: 리믹스 체인을 콘텐츠 그래프로 만들기
- 방향:
  - 프로필에서 “대표 빌드 + 리믹스된 횟수 + 파생 트리” 노출
  - `/s/build/{id}`에 “Remixes / Fork from / Forks of” 섹션 추가

### v2: Weekly Novelty / Meta Games
- 목표: “이번 주에만 재밌는” 빌드 스포츠 규칙을 주간 단위로 공급
- 방향:
  - weekly portals/augments, 제한 룰(예: 특정 태그만), weekly trophy 등
  - “이번 주 가장 많이 리믹스된 빌드/클립”을 시즌/주간 보상과 연결

## 6) 운영 원칙 (깨지면 안 되는 것)
- 결정론 불변: RNG seed 파생/Replay digest/Pack hash 규칙 유지
- Share OG 안정성: `/s/*`의 OG meta + og:image never‑404 유지
- 보안: open redirect 방지(next 상대경로 제한) 유지, `/api/assets` allowlist 약화 금지

