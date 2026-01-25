# NeuroLeague Design v2.1.1 — Gesture Quality Spec (/play)

This document is the **implementation-ready input quality spec** for `/play` in Design v2.1.1.

## Gemini UI Spec (required provenance)
Tool used: `gemini_ui_design`

### Tool metadata (per `gemini_ui_design` structured output)
- requested_start_alias: `ui-design-pro-max`
- selected_latest_pro_model: `gemini-3-pro-preview`
- attempted_chain:
  - `ui-design-pro-max` → `gemini-3-pro-preview` (success)
- actual_models_used: `["gemini-3-pro-preview"]`
- thinking_config_applied: `{ raw_model: "gemini-3-pro-preview", thinkingLevel: "high", includeThoughts: false }`
- gemini_cli_version: `0.25.2`
- note: `모델 목록 조회 실패로 인해 보수적 기본값 사용 | No supported non-interactive model listing method found (GEMINI_API_KEY not set; Gemini CLI does not expose \`models list\` in headless mode).`

## Goals
- Make `/play` feel like a **premium mobile app**: confident gesture detection, no accidental actions.
- Resolve conflicts: **single tap** (chrome show/hide + optional unmute) vs **double-tap** (reaction).
- Keep the existing performance constraints (1–2 video preload) and all platform invariants.

## Non‑negotiables (must not regress)
- Determinism invariants: `derive_seed`, replay digest, `pack_hash`, cache keys
- `/s/*` OG meta + `og:image` never‑404
- `/start?next=` open‑redirect guard
- `/api/assets` allowlist policy
- UI source of truth: `apps/web/`

---

## 1) Gesture recognition rules (thresholds + priorities)

### 1.1 Tap vs Double‑tap vs Swipe (priority order)
1) **Interactive targets win**: if the gesture starts on a control, do not start pager gesture handling.
2) **Swipe** (vertical dominance + travel/velocity) has priority over taps once the movement crosses the drag slop.
3) **Double‑tap** beats **single‑tap**; single tap is delayed until the double‑tap window closes.

### 1.2 Threshold table (recommended defaults)
| Name | Value | Notes |
|---|---:|---|
| `TAP_SLOP_PX` | 10px | Max movement to still be considered a tap. |
| `DOUBLE_TAP_MS` | 260ms | Time window between taps. |
| `DOUBLE_TAP_SLOP_PX` | 14px | Max distance between the two taps to count as double‑tap. |
| `DRAG_START_PX` | 12px | Movement to consider starting a drag. |
| `VERTICAL_DOMINANCE` | 1.2× | Require `abs(dy) >= abs(dx) * 1.2` to treat as vertical swipe. |
| `SWIPE_COMMIT_PX` | `max(64px, 0.18 * height)` | Commit travel threshold (height = pager viewport). |
| `SWIPE_VELOCITY_PX_PER_MS` | 0.65 | Commit if velocity exceeds threshold (≈ 650px/s). |

### 1.3 Single-tap delay (conflict-free)
- On first tap, **schedule** single-tap action for `DOUBLE_TAP_MS`.
- If a second tap arrives within `DOUBLE_TAP_MS` and within `DOUBLE_TAP_SLOP_PX`, **cancel** the scheduled single-tap and fire double-tap action immediately.
- Single tap should not “flash” UI and then be canceled. Prefer “do nothing until confirmed”.

### 1.4 Swipe detection
- Start drag only after `DRAG_START_PX`.
- Require vertical dominance before starting the swipe interaction.
- Commit:
  - if `abs(dy) >= SWIPE_COMMIT_PX`, or
  - if `abs(velocity) >= SWIPE_VELOCITY_PX_PER_MS` (flick).
- If started on an interactive element, do not capture pointer; let the element handle click/press.

---

## 2) Region priority rules

### 2.1 Areas
- **Video area** (non-interactive): swipe pager + single/double tap behaviors apply.
- **HUD / CTA buttons** (Beat This, Quick Remix, like/share, quest chip):
  - Buttons must be tappable without swipes stealing input.
  - These targets must be detectable via `button/a/input/...` or `[data-gesture-ignore]`.
- **Bottom nav**: always wins; gesture handling must not start from bottom nav touches.

### 2.2 Implementation hooks
- Add `[data-gesture-ignore="true"]` to any non-semantic interactive wrappers (divs behaving like buttons).
- Pager checks `closest('button, a, input, ... , [data-gesture-ignore="true"]')` before capturing.

---

## 3) touch-action / pointer-events policy (browser interference minimization)

### 3.1 Pager container
- Use **pointer events** (not touch events).
- Set `touch-action: none` on pager container to prevent:
  - browser scroll / pull-to-refresh
  - double-tap zoom
- Set `overscroll-behavior: none` to prevent scroll chaining bounce.

### 3.2 Global notes
- Ensure video uses `playsInline muted loop` by default; unmute must only happen from a user gesture.
- Avoid passive touch handlers that prevent `preventDefault` when needed (pointer events should be sufficient here).

---

## 4) A11y / Reduce Motion / screen reader / keyboard focus behaviors

### 4.1 Reduce Motion (`reduceMotion=true` or `prefers-reduced-motion: reduce`)
- Disable or simplify:
  - ReactionBurst animation → simple opacity/scale (no “burst” motion)
  - Swipe transition → short translate + fade (no spring)
  - Idle chrome auto-hide → **disabled**

### 4.2 Screen reader / keyboard focus
- Auto-hide must be suppressed when:
  - keyboard navigation is detected (Tab/Arrow keys), or
  - focus is inside an interactive control (`focusin`/`focusout` based detection)
- Any gesture-only action must have a visible control alternative:
  - Reaction buttons still exist on UI (double-tap is a shortcut, not the only way).

---

## 5) Telemetry (events + dedupe)

Events are sent via the existing `/api/events/track` pipeline (best-effort; never block UX).

### 5.1 Event map
- `swipe_next` / `swipe_prev`
  - Fired when the pager index changes due to swipe.
  - Meta: `{ from_replay_id, to_replay_id, mode, sort, feed_algo, hero_variant }`
- `double_tap_reaction`
  - Fired when double-tap reaction shortcut triggers.
  - Meta: `{ replay_id, reaction_type, ... }`
- `chrome_autohide_shown` / `chrome_autohide_hidden`
  - Fired when chrome becomes visible/hidden.
  - Meta: `{ replay_id, reason }` where `reason ∈ { idle, tap_toggle, tap_unmute, swipe, keyboard, focus, ... }`
- `unmute_click`
  - Fired when audio is enabled from mute → unmute.
  - Meta: `{ replay_id, via: "tap"|"button" }`

### 5.2 Dedupe / spam guardrails
- `double_tap_reaction`: client cooldown (≈ 650ms) to prevent accidental spam.
- `chrome_autohide_*`: only on state transitions (hide/show), not continuously.
- `video_load_fail` remains the primary guardrail event for feed reliability and should be analyzed alongside the above (per replay/session).

---

## 6) Testing

### 6.1 Playwright (must pass in `NEUROLEAGUE_E2E_FAST=1 make e2e`)
- `/play` loads; Beat This CTA visible; console errors = 0
- Swipe up → next clip (active replay id changes)
- Swipe down → previous clip (active replay id returns)
- Double-tap on video area → `reaction-burst` appears
- `reduceMotion=true`:
  - `reaction-burst` renders with reduced indicator (`data-reduced="1"`)
  - chrome does not auto-hide (Beat This remains visible after idle window)

### 6.2 Manual QA checklist (mobile Chrome + Android TWA)
- Swipe works from video area; does not misfire when starting on CTAs.
- Button presses never feel “stolen” by swipes.
- Double-tap reliably triggers reaction; does not toggle chrome/unmute.
- Single tap toggles chrome reliably; delay is not perceived as broken.
- Overscroll / pull-to-refresh does not happen on `/play`.
- Reduce Motion: no burst motion; no auto-hide; transitions are simple.
