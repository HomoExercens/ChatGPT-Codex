# Design v2.1.3 — Gesture Ops + Sampling + Misfire Score

목표: `/play` 제스처 튜닝(gesture_thresholds_v1)을 **운영 가능(operational)** 하게 만든다.
- 비용 폭탄 없이(샘플링/상한) 시도·취소 데이터를 수집
- variant별로 KPI ↔ misfire(오작동/취소) 상관을 한 화면에서 비교
- cancel_reason 분포로 “무엇이 망가졌는지” 바로 보이게

---

## 1) Ops UI spec (/ops/gestures)

Gemini UI 컨셉: **“The Tuning Cockpit”**  
고밀도 비교(Variant A/B vs Control) + premium ops 톤(다크/모노숫자/명확한 위계).

### 1-A) 정보 위계(IA)

- Breadcrumb: `/Ops / Gestures`
- Title: `Gesture Tuning`
- Action bar:
  - Range toggle: `24h(1d)` / `7d`
  - `Refresh` 버튼(재조회)
  - “ADMIN MODE” 배지(권한 신호)
- Main: **variant 비교 그리드**
  - desktop: 3-column (control / variant_a / variant_b)
  - mobile: stacked cards

### 1-B) Variant card 구조(각 variant 동일 레이아웃)

1. **Header**
   - Variant 이름 + (가능하면) traffic %/assigned
2. **Engagement KPIs (2x2)**
   - `clip_view_3s`, `beat_this_click`, `match_done`, `reply_clip_shared`
   - 숫자: tabular/mono(정렬) + 작은 delta(추후) 확장 가능
3. **Gesture Quality**
   - `misfire_score` (0~1 또는 0~100 스케일 중 1개로 통일)
   - `cancel_reason top3` 리스트(순위 + 카운트 + 비율)
4. **Guardrails**
   - `video_load_fail`
   - `429`
   - `5xx`

### 1-C) 컴포넌트 스펙(Design v2 컴포넌트로 구현)

- `RangeToggle`
  - 2-state segmented control
  - `aria-pressed` 사용
- `MetricCard` / `MetricItem`
  - label(uppercase 작은 글자) + value(굵은 mono/tabular)
- `MisfireGauge`
  - bar/gauge(간단)
  - 색상은 토큰의 success/warn/danger 계열을 “임계치 기반”으로 적용
- `CancelReasonList`
  - top3만 노출(“more”는 v2.1.4 후보)
- `ErrorState`
  - 401(admin_disabled/unauthorized)면 전체 페이지 안내
  - 네트워크 오류면 card 단위 retry 제공
- `Skeleton`
  - 레이아웃 고정(shift 최소화), 숫자 영역만 skeleton

### 1-D) 스타일/토큰 적용 규칙

- **Design v2 토큰 우선**: `bg-bg`, `bg-surface-*`, `border-border/*`, `text-fg`, `text-muted`, `shadow-glass`, `nl-tabular-nums` 활용.
- 숫자 가독성: `font-mono` 또는 기존 `nl-tabular-nums` 유틸로 “숫자 흔들림” 방지.
- ops는 dense하되 터치 타겟 최소 44px 유지.

### 1-E) 상태 정의

- Loading: skeleton(카드 구조는 유지)
- Empty: “No telemetry for this period” + range 변경 힌트
- Error:
  - 401: admin token 안내
  - 기타: `Retry` 버튼

---

## 2) Event volume control: attempt sampling 정책

대상 이벤트: `tap_attempt`, `swipe_attempt` (시도/취소 계열)

권장 정책(v1):
- **세션 샘플링**: 기본 30% 세션만 attempt 이벤트 기록
- **세션당 상한**: attempt 이벤트 합산 최대 20개/세션
- 메타 포함(필수):
  - `gesture_attempt_sample_rate`
  - (가능하면) `gesture_attempt_session_cap`
  - (가능하면) `gesture_attempt_session_remaining`

주의:
- success 이벤트(`swipe_next`, `swipe_prev`, `double_tap_reaction` 등)는 샘플링하지 않음(튜닝 KPI 유지).

---

## 3) Misfire Score 정의(rollup + ops)

목표: variant별로 “입력 품질”을 하나의 수치로 비교.

예시(v1):
- `swipe_cancel_rate = swipe_cancel_count / max(1, swipe_attempt_count)`
- `tap_cancel_rate = tap_cancel_count / max(1, tap_attempt_count)`
- `misfire_score = 0.6 * swipe_cancel_rate + 0.4 * tap_cancel_rate`

추가로, `cancel_reason top3`를 함께 노출해 “왜 나쁜지” 바로 보이게 한다.

샘플링 보정(가능하면):
- attempt 이벤트가 샘플링될 경우, `1 / sample_rate` 가중으로 “추정치” 집계(메타에 sample_rate가 들어있어야 함).

---

## 4) Ops 화면에서 보는 지표(요약)

- Variant KPIs: `clip_view_3s`, `beat_this_click`, `match_done`, `reply_clip_shared`
- Misfire: `misfire_score`, `cancel_reason top3`
- Guardrails: `video_load_fail`, `429`, `5xx`

---

## Gemini UI spec provenance (AGENTS.md requirement)

> Gemini MCP tool 사용이 일시적으로 OAuth 요구로 실패할 수 있어, 동일 `gemini_ui_design` MCP 서버를 로컬 테스트 클라이언트로 호출하여 spec을 생성했다.

- requested_start_alias: `ui-design-pro-max`
- selected_latest_pro_model: `gemini-3-pro-preview`
- attempted_chain:
  - `{ alias: "ui-design-pro-max", raw_model: "gemini-3-pro-preview", success: true }`
- actual_models_used: `["gemini-3-pro-preview"]`
- thinking_config_applied: `{ raw_model: "gemini-3-pro-preview", thinkingLevel: "high", includeThoughts: false }`
- gemini_cli_version: `0.25.2`
- note: `모델 목록 조회 실패로 인해 보수적 기본값 사용 | No supported non-interactive model listing method found (GEMINI_API_KEY not set; Gemini CLI does not expose \`models list\` in headless mode).`

