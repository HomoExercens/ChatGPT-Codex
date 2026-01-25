# Gesture Ops v2.1.5 — UA Reduction / UA-CH(UAData) + Segment Trust & Coverage

This document is generated for **Gesture Ops v2.1.5** and records the UI/telemetry spec + provenance per `AGENTS.md`.

## Status / Provenance

### gemini_ui_design (attempted; empty output)

The `gemini_ui_design` MCP tool was called **before implementation** (per AGENTS.md), but returned **empty output** across the required alias fallback chain. Because no usable spec text was produced, the sections below are a **fallback spec** written to unblock implementation, while still preserving the tool provenance for debugging.

#### Attempt #1 (requested_start_alias=`ui-design-pro-max`)

```json
{
  "requested_start_alias": "ui-design-pro-max",
  "selected_latest_pro_model": "gemini-3-pro-preview",
  "attempted_chain": [
    { "alias": "ui-design-pro-max", "raw_model": "gemini-3-pro-preview", "success": false, "error_summary": "empty output" },
    { "alias": "ui-design-3-flash-max", "raw_model": "gemini-3-flash-preview", "success": false, "error_summary": "empty output" },
    { "alias": "ui-design-2.5-pro-max", "raw_model": "gemini-2.5-pro", "success": false, "error_summary": "empty output" },
    { "alias": "ui-design-2.5-flash-max", "raw_model": "gemini-2.5-flash", "success": false, "error_summary": "empty output" }
  ],
  "actual_models_used": [],
  "thinking_config_applied": null,
  "gemini_cli_version": "0.25.2"
}
```

#### Attempt #2 (requested_start_alias=`ui-design-3-pro-max`)

```json
{
  "requested_start_alias": "ui-design-3-pro-max",
  "selected_latest_pro_model": "gemini-3-pro-preview",
  "attempted_chain": [
    { "alias": "ui-design-3-pro-max", "raw_model": "gemini-3-pro-preview", "success": false, "error_summary": "empty output" },
    { "alias": "ui-design-3-flash-max", "raw_model": "gemini-3-flash-preview", "success": false, "error_summary": "empty output" },
    { "alias": "ui-design-2.5-pro-max", "raw_model": "gemini-2.5-pro", "success": false, "error_summary": "empty output" },
    { "alias": "ui-design-2.5-flash-max", "raw_model": "gemini-2.5-flash", "success": false, "error_summary": "empty output" }
  ],
  "actual_models_used": [],
  "thinking_config_applied": null,
  "gemini_cli_version": "0.25.2"
}
```

---

## 1) UA reduction / UA-CH / UAData overview (ops-friendly)

**What changed (industry trend):**
- Modern browsers are reducing the entropy of the classic `User-Agent` string (“UA reduction”), making UA-only heuristics less reliable for platform/container classification over time.
- Chromium-based browsers expose **User-Agent Client Hints (UA-CH)** and the JS API **`navigator.userAgentData`** to provide *lower-entropy* signals (platform/mobile/brands).

**Why this matters for NeuroLeague Gesture Ops:**
- `/ops/gestures` relies on **segment filters** (android_twa / android_chrome / desktop_chrome / ios_safari / ios_chrome / unknown).
- If UA-based segmentation drifts, the experiment readouts become hard to interpret (e.g., “unknown” grows, android_twa misclassified, etc.).
- Therefore we need **coverage/trust metrics** so an operator can tell whether segment KPIs and misfire are interpretable.

**HTTPS note (important):**
- UA-CH headers and `navigator.userAgentData` are **best-effort** and often depend on **secure contexts (HTTPS)**.
- In local HTTP/dev, `userAgentData` may be missing or reduced; ops should expect lower coverage locally.

---

## 2) Data collection spec (low-entropy only; analytics-only)

### 2.1 Client-side UAData (best-effort)

Collect only the **low-entropy** fields from `navigator.userAgentData` when available:
- `uaData_platform`: string (example: `"Android"`, `"Windows"`, `"macOS"`, `"iOS"` …)
- `uaData_mobile`: boolean
- `uaData_brands_major`: array of `{ brand, major }` (major version only; do **not** collect full version)

Add a presence bit:
- `uach_available`: boolean (true if `navigator.userAgentData` exists)

**Where to attach:**
- `play_open` event meta (once per session)
- `gesture_session_summary` event meta (once per session; keepalive)

**Non-goals / privacy guardrails:**
- Do **not** call `getHighEntropyValues`.
- Do **not** store model/device identifiers.
- Do **not** add any stable per-device fingerprint beyond existing `device_id`/`session_id`.

### 2.2 Server-side UA-CH headers (optional, analytics-only)

If present in requests (typically HTTPS Chromium), capture low-entropy UA-CH headers for ops debugging:
- `sec-ch-ua-platform` → `uach_platform_hdr`
- `sec-ch-ua-mobile` → `uach_mobile_hdr`
- `sec-ch-ua` (brands list) → `uach_brands_hdr_major` (major only)

These should be **stored only on session-level events** (`play_open`, `gesture_session_summary`) to avoid payload bloat.

### 2.3 Container hint coverage

Container hint is considered present when the API request includes:
- `X-App-Container: twa|chrome|safari`

Store:
- `ua_container_hint`: `"twa"|"chrome"|"safari"` (only when provided; else absent)

---

## 3) Ops UI: Trust/Coverage visibility (Design v2)

### 3.1 Placement & hierarchy

On `/ops/gestures`:
1) Filters (admin token, range, segment)
2) Guardrails (5xx/429/video_load_fail/render backlog)
3) **Trust & Coverage strip** (always visible when enabled)
4) Variant cards (KPIs / Sampling / Misfire)

### 3.2 Trust & Coverage strip metrics

Show the following for the current `range` + `segment` selection:
- `n_sessions` (already shown as “sessions” per variant; show total too)
- `uach_available_rate` (fraction of sessions where UAData is available)
- `container_hint_coverage` (fraction of sessions with explicit `X-App-Container` hint)
- `unknown_segment_rate` (fraction of sessions where server `ua_segment == "unknown"`; only meaningful when segment=all)

### 3.3 Warnings / interpretability rules (UX copy)

Add a small, explicit warning when:
- `n_sessions < 50` → “Low sample; interpret with caution”
- `unknown_segment_rate > 0.25` (segment=all) → “High unknown; segment KPIs may be biased”
- `uach_available_rate < 0.30` → “UAData coverage low (expected on HTTP/dev); segment trust reduced”
- `container_hint_coverage` is unexpectedly low for a known TWA rollout → “TWA hint missing; check wrapper URL params”

### 3.4 Visual style

Use existing Design v2 tokens/components:
- `Card`, `Badge`, `Skeleton`, `Button`
- Compact “ops density” but keep legibility (monospace + tabular numerals for metrics).

---

## 4) Components / interactions (implementation notes)

### 4.1 New UI primitives (minimal)

- **`CoverageStrip`** (inline on `/ops/gestures`)
  - Inputs: totals + rates
  - Shows 4–6 badges + optional warning chip
  - `data-testid="ops-gestures-coverage-strip"`

- **`CoverageRow`** (inside each variant card, under Sampling/Bias)
  - Inputs: variant-level coverage rates (if exposed)
  - `data-testid="ops-gestures-coverage-variant-${variantId}"`

### 4.2 Tooltip copy (optional; no new deps)

Prefer a small caption text under the segment buttons, rather than a tooltip dependency. If tooltips exist, add:
- “UAData is only available on some browsers (often HTTPS Chromium).”
- “Container hint is provided by app wrapper (`?twa=1`/`?container=twa`) and sent via `X-App-Container`.”

---

## 5) QA / Tests

### 5.1 Manual QA checklist

- Open `/play` and confirm no gesture behavior changed.
- Confirm `play_open` and `gesture_session_summary` include UAData meta when available (Chrome HTTPS).
- Open `/ops/gestures`:
  - Coverage strip shows `uach_available_rate`, `container_hint_coverage`, `unknown_segment_rate`.
  - Switching segment updates values.
  - When segment=all, unknown rate is non-zero if unknown sessions exist.

### 5.2 Playwright (suggested selectors)

- `/ops/gestures` renders with admin token:
  - Assert `data-testid="ops-gestures-page"` exists.
  - Assert `data-testid="ops-gestures-coverage-strip"` exists and contains labels:
    - `uach` / `container_hint` / `unknown`
- Segment toggle:
  - Click “Android · Chrome” and assert request includes `segment=android_chrome` (existing test).

