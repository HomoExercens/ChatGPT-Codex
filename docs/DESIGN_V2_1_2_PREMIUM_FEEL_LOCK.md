# Design v2.1.2 — Premium Feel Lock (/play)

목표: Design v2.1.1의 제스처/입력 품질을 “체감(즉시성) + 튜닝 가능성 + 관측 가능성”까지 잠가서, 모바일(특히 Android)에서 진짜 앱처럼 느껴지게 만든다.

## 0) Scope / Non-goals

- Scope
  - /play 입력 체감(탭 지연 체감 보완), 제스처 관측 이벤트(시도/취소 포함), threshold 실험 주입, HUD/CTA 타겟 안전.
- Non-goals
  - 결정론(derive_seed/replay digest/pack_hash/cache keys) 관련 로직 변경 금지.
  - /s/* OG meta / og:image 정책 변경 금지.
  - /start?next 오픈 리다이렉트 가드 변경 금지.
  - /api/assets allowlist 약화 금지.

## 1) Single-tap delay “feel” 보완: 즉시 피드백(pressed)

문제: double-tap arbitration 때문에 single tap action이 ~260ms 지연되며 “늦게 반응”으로 체감될 수 있음.

해결: **기능 실행은 지연하되, “탭이 인식되었다”는 즉시 피드백을 pointerdown에 제공**.

### 1-A) Pressed overlay 규칙

- 트리거: /play “video area”에서 `pointerdown`
- 표시: **아주 약한 pressed overlay** (scrim 강화/미세 하이라이트). 텍스트/CTA를 가리지 않음.
- 지속: `80–120ms` 기본 + 즉시 release 시 더 빨리 종료 가능.
- double-tap 확정 시:
  - pressed overlay는 보여도 됨
  - single-tap action은 실행되지 않음(기존 v2.1.1 규칙 유지)
- 제스처로 전환(swipe/drag)되면: pressed overlay 즉시 해제
- Reduce Motion:
  - 애니메이션 없이 on/off만(또는 0ms transition)

### 1-B) “영역 우선순위”

- HUD/CTA/BottomNav에서 시작된 터치는:
  - global pager swipe보다 클릭/탭이 우선
  - pressed overlay도 **video area에서만** 적용(CTA 위에서 보이면 산만)
- 구현 정책: 클릭 타겟에 `data-gesture-ignore="true"`를 부여하여 global 제스처 처리기가 early return.

## 2) Gesture Observability: 성공뿐 아니라 시도/취소 측정

튜닝을 위해 “성공 이벤트”뿐 아니라 **시도/취소**를 측정한다. 단, 스팸/중복을 피하기 위해 **1 gesture당 1회**만 기록한다.

### 2-A) 이벤트 타입

- 신규:
  - `swipe_attempt`
  - `tap_attempt`
- 기존 유지:
  - `swipe_next`, `swipe_prev`
  - `double_tap_reaction`
  - `chrome_autohide_shown`, `chrome_autohide_hidden`
  - `unmute_click`

### 2-B) swipe_attempt schema

```json
{
  "event_type": "swipe_attempt",
  "meta": {
    "replay_id": "r_123",
    "direction_candidate": "next|prev",
    "dy": -180,
    "dx": 18,
    "velocity": 0.72,
    "committed": 1,
    "cancel_reason": null
  }
}
```

권장 cancel_reason taxonomy (string):

- `gesture_ignore_target` (HUD/CTA 위에서 시작)
- `horizontal_dominance` (가로 드래그 우세)
- `threshold_not_met` (dy/velocity 미달)
- `multi_touch` (2+ pointers)
- `pointer_cancelled` (pointercancel/leave)

### 2-C) tap_attempt schema

```json
{
  "event_type": "tap_attempt",
  "meta": {
    "replay_id": "r_123",
    "kind": "single_candidate|double_candidate",
    "canceled": 0,
    "cancel_reason": null
  }
}
```

권장 cancel_reason taxonomy:

- `gesture_ignore_target`
- `tap_slop_exceeded`
- `became_swipe`
- `multi_touch`

### 2-D) dedupe 정책

- “attempt 이벤트”는 gesture 단위로 1회만 기록:
  - swipe: pointerdown → pointerup/cancel 시점에 1회
  - tap: arbitration이 끝나는 시점(single 확정 / double 확정 / cancel) 1회
- replay_id/세션 기준으로 동일 액션이 연속 발생해도 **각 제스처당 1회**만 기록(move마다 기록 금지)

## 3) Threshold tunability: experiments 주입

기기별 체감 차이를 대응하기 위해 threshold는 코드 상수가 아니라 **실험(원격 설정)로 주입**한다.

### 3-A) experiment key

- key: `gesture_thresholds_v1`
- variants:
  - `control`: 현행 v2.1.1 값 유지
  - `variant_a`: “조금 더 민감” (double-tap window 단축, tap slop 상향 등)
  - `variant_b`: “조금 더 의도적” (swipe commit 강화, tap slop 하향 등)

### 3-B) 주입 대상 파라미터(권장)

- tap
  - `DOUBLE_TAP_MS`
  - `DOUBLE_TAP_SLOP_PX`
  - `TAP_SLOP_PX`
- swipe
  - `DRAG_START_PX`
  - `SWIPE_COMMIT_PX` (px 또는 height 비율)
  - `VELOCITY_PX_PER_MS`
  - `VERTICAL_DOMINANCE`

### 3-C) 기본값

- 기본값은 “현재 코드에 있는 값”을 명시적으로 유지한다.
- 실험이 실패하거나 값이 비정상이면 기본값으로 fallback한다.

## 4) A11y / Reduce Motion 정책

- `prefers-reduced-motion` 또는 앱 설정 `reduceMotion=true`:
  - pressed overlay: transition 없이 on/off만
  - reaction burst: 강한 모션 off(기존 정책 유지)
  - auto-hide: 비활성(또는 대폭 단순화) (기존 정책 유지)
- Screen reader / keyboard focus:
  - focus가 잡힌 상태에서는 auto-hide 억제
  - swipe는 터치 기반이므로 키보드로도 접근 가능한 최소 대체(기존 구현 유지/필요 시 추가)

## 5) Tests

### 5-A) Playwright (fast e2e)

- /play 진입 → 첫 카드 로드
- pointerdown 즉시 pressed overlay가 보임(`data-testid`로 검증)
- double-tap → reaction burst는 뜨되, single-tap action(크롬 토글)이 발생하지 않음
- swipe up/down 최소 1회 성공
- (가능하면) /api/events/track 요청 중 `tap_attempt` / `swipe_attempt` 가 1회 이상 포함됨을 확인
- reduceMotion=true일 때 burst/auto-hide가 비활성(또는 단순화)임을 확인

### 5-B) Manual QA checklist

- Android Chrome:
  - 탭 시 즉시 반응(pressed) 체감이 있고 “딜레이” 느낌이 줄었는지
  - HUD/CTA 위에서 스와이프가 버튼 입력을 빼앗지 않는지
  - 빠른 더블탭이 single-tap 토글을 만들지 않는지
  - 스크린 edge/back gesture와 충돌하지 않는지(특히 가로 드래그)

---

## Gemini UI Spec provenance (AGENTS.md requirement)

- requested_start_alias: `ui-design-pro-max`
- selected_latest_pro_model: `gemini-3-pro-preview`
- attempted_chain:
  - `{ alias: "ui-design-pro-max", raw_model: "gemini-3-pro-preview", success: true }`
- actual_models_used: `["gemini-3-pro-preview"]`
- thinking_config_applied: `{ raw_model: "gemini-3-pro-preview", thinkingLevel: "high", includeThoughts: false }`
- gemini_cli_version: `0.25.2`
- note: `모델 목록 조회 실패로 인해 보수적 기본값 사용 | No supported non-interactive model listing method found (GEMINI_API_KEY not set; Gemini CLI does not expose \`models list\` in headless mode).`

