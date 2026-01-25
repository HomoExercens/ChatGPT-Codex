# Gesture Ops v2.1.6 — Variant Config Echo (read-only) + gemini_ui_design empty-output gate

This document records the **v2.1.6 ops UX spec** for `/ops/gestures` and the required `gemini_ui_design` provenance per `AGENTS.md`.

## Status / Provenance

### gemini_ui_design (called; spec text missing)

Per `AGENTS.md`, `gemini_ui_design` was called **before implementation**. The tool returned provenance successfully, but did **not** include the actual UI spec text in the response (effectively **empty spec output**).

Per the v2.1.6 gate policy (below), we retried once with a more specific prompt and still got no spec text. The remainder of this document is a **fallback spec** written to unblock implementation while preserving provenance for debugging.

#### Attempt #1 (requested_start_alias=`ui-design-pro-max`)

```json
{
  "requested_start_alias": "ui-design-pro-max",
  "selected_latest_pro_model": "gemini-3-pro-preview",
  "attempted_chain": [{ "alias": "ui-design-pro-max", "raw_model": "gemini-3-pro-preview", "success": true }],
  "actual_models_used": ["gemini-3-pro-preview"],
  "thinking_config_applied": { "raw_model": "gemini-3-pro-preview", "thinkingLevel": "high", "includeThoughts": false },
  "gemini_cli_version": "0.25.2",
  "creds_path_used": "/home/clutch/.gemini/oauth_creds.json",
  "gemini_cwd_used": "/home/clutch/.gemini",
  "ci_env_stripped": 0,
  "auth_flow_used": "none",
  "refresh_attempted": false,
  "refresh_result": "skipped",
  "auth_url": null,
  "note": "모델 목록 조회 실패로 인해 보수적 기본값 사용 | Model listing via API key is disabled (OAuth-only); Gemini CLI does not expose `models list` in headless mode. | cwd pinned to ~/.gemini to maximize OAuth cache reuse"
}
```

#### Attempt #2 (retry; requested_start_alias=`ui-design-pro-max`)

```json
{
  "requested_start_alias": "ui-design-pro-max",
  "selected_latest_pro_model": "gemini-3-pro-preview",
  "attempted_chain": [{ "alias": "ui-design-pro-max", "raw_model": "gemini-3-pro-preview", "success": true }],
  "actual_models_used": ["gemini-3-pro-preview"],
  "thinking_config_applied": { "raw_model": "gemini-3-pro-preview", "thinkingLevel": "high", "includeThoughts": false },
  "gemini_cli_version": "0.25.2",
  "creds_path_used": "/home/clutch/.gemini/oauth_creds.json",
  "gemini_cwd_used": "/home/clutch/.gemini",
  "ci_env_stripped": 0,
  "auth_flow_used": "none",
  "refresh_attempted": false,
  "refresh_result": "skipped",
  "auth_url": null,
  "note": "모델 목록 조회 실패로 인해 보수적 기본값 사용 | Model listing via API key is disabled (OAuth-only); Gemini CLI does not expose `models list` in headless mode. | cwd pinned to ~/.gemini to maximize OAuth cache reuse"
}
```

---

## 1) Goal: Variant Config Echo (analysis speed)

**Problem:** `/ops/gestures` shows KPI + misfire deltas by `gesture_thresholds_v1` variants, but operators must cross-reference code to remember each variant’s threshold config, slowing iteration and increasing misinterpretation risk.

**Goal:** Show each variant’s **current threshold config** (read-only) directly inside the variant card, **adjacent to sampling + coverage** so deltas are always interpreted with context.

**Non-goal:** Editing experiment weights/config in UI (read-only only).

## 2) Information architecture (page)

1) Filters (admin token, range, segment) — existing.
2) Guardrails strip — existing.
3) Coverage strip (sessions + UAData/container_hint/unknown) — existing.
4) Variant cards grid — existing; add new section:
   - KPIs
   - Sampling/Bias
   - Coverage/Trust
   - **Current config (new)**
   - Misfire + cancel reasons

## 3) “Current config” block (per-variant)

### 3.1 Data to display (gesture_thresholds_v1 config keys)

Show these keys when available:
- `double_tap_ms` (ms)
- `double_tap_slop_px` (px)
- `tap_slop_px` (px)
- `drag_start_px` (px)
- `vertical_dominance` (ratio)
- `swipe_commit_frac` (ratio)
- `swipe_commit_min_px` (px)
- `swipe_velocity_px_ms` (px/ms)

### 3.2 Presentation rules

- Render as a compact key/value list, **2 columns** on desktop widths (single column on narrow).
- Numbers use **tabular numerals** (`nl-tabular-nums`) and can be monospace.
- Labels are short + consistent (e.g., “double tap”, “tap slop”, “commit frac”).
- Units are always visible (ms/px/ratio/px·ms⁻¹).

### 3.3 Missing config / degraded state

If `thresholds_config` is missing or empty:
- Show “—” values and a muted note: “Config not available for this variant (check experiment row).”
- Do not block the rest of the card.

## 4) Layout rules with Sampling/Bias + Coverage/Trust (interpretability)

- “Current config” must appear **in the same vertical stack** as:
  - Sampling/Bias (sample sizes, cap_hit, dropped, sample_rate)
  - Coverage/Trust (UAData + container_hint coverage)
- Operators should be able to see **Sampling → Coverage → Config** without scrolling inside the card.
- If vertical space is tight, “Cancel reasons” is allowed to extend below the fold; “Config” is not.

## 5) Data-testids (Playwright)

Add:
- `data-testid="ops-gestures-config-echo-${variantId}"`

Optional (if helpful for tests later):
- `data-testid="ops-gestures-config-${variantId}-double_tap_ms"` etc.

## 6) gemini_ui_design empty-output gate policy (v2.1.6)

**Definition of “empty output”:**
- The tool response is missing the actual spec body (no usable Markdown), even if provenance metadata exists.

**Gate steps (mandatory):**
1) If `gemini_ui_design` output is empty, retry **once** with a more specific prompt (explicit output format + required sections).
2) If the retry is still empty, treat as a **blocking failure**:
   - Stop UI work, or
   - Proceed only with a clearly labeled fallback spec (like this document) and record the raw tool provenance + any relevant CLI logs in the PR description.

**What to record in docs/PR (debugging):**
- `requested_start_alias`
- `selected_latest_pro_model`
- `attempted_chain`
- `actual_models_used`
- `thinking_config_applied`
- CLI versions if available

## 7) QA checklist

- `/ops/gestures` shows “Current config” for each variant card (when admin token is present).
- Config is never displayed without adjacent sample sizes + coverage context.
- Segment toggle still refetches.
- Missing config does not break rendering.

