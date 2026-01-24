# NeuroLeague Design v2.1 — Motion + Accessibility Policy

This document defines what motion is allowed in v2.1 and how the UI behaves under `reduceMotion`.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Requested model: `gemini-3-pro-preview`
- Actually used model (per tool output): `gemini-3-pro-preview`

## Inputs
- App setting: `reduceMotion` (stored in `neuroleague.settings`)
- System: `prefers-reduced-motion: reduce`

Policy: either one being “reduced” must disable strong motion.

---

## 1) Allowed motion (default)
### 1.1 Micro-interactions (allowed everywhere)
- Button press micro-scale (already in v2 Button)
- Short fades (≤ 220–320ms)
- Small translate (≤ 8–12px) for page transitions

### 1.2 “Juice” (allowed but bounded)
- Reaction burst: max ~650ms, center-only, non-blocking
- Page swipe: translate + fade (no spring)

Hard caps:
- No infinite loops
- No heavy blur animations

---

## 2) Reduced Motion mode (mandatory behavior)
When `reduceMotion=true` OR `prefers-reduced-motion: reduce`:
- Disable:
  - bursts with particles / explosive scale
  - spring-like easing / overshoot
  - shake / hit-stop / slowmo (already used elsewhere)
- Replace with:
  - simple opacity fades
  - minimal scale (≤ 1.05) or none

Implementation requirement:
- Components that have “strong” variants must expose a testable marker:
  - e.g. `data-reduced="1"`

---

## 3) Auto-hide + accessibility
- Auto-hide must not fight accessibility:
  - If the user is navigating with keyboard (recent keydown/focus), suppress auto-hide.
  - If an interactive element is focused, suppress auto-hide.
  - If a sheet/modal is open, suppress auto-hide.

---

## 4) QA checklist
- With `reduceMotion=true`:
  - `/play` swipe works with simple transitions.
  - Double-tap reaction uses reduced burst (no strong animation classes).
  - No console errors.

