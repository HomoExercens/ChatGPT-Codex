# NeuroLeague Design v2.1 — Typography + Icon System

This document standardizes typography and icons for v2.1 so the app feels intentional and premium.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Requested model: `gemini-3-pro-preview`
- Actually used model (per tool output): `gemini-3-pro-preview`

## Constraints
- No external font downloads. Use existing system/Inter-like stack already in the project.
- Keep Tailwind + CSS variable tokens architecture.

---

## 1) Typography roles
### 1.1 Roles
- **Display** (results / hero numbers): bold, tight tracking, short strings only
- **Text** (body): calm, readable, no heavy effects
- **Numeric** (counters): tabular numerals to prevent jitter

### 1.2 Rules
- Any changing number MUST use tabular numerals:
  - likes / shares / HP% / XP / streak / counts / timers
- Text legibility over video must be solved primarily with scrims (see `ScrimOverlay`), then minimal shadow.

### 1.3 Recommended utilities
- `nl-display`:
  - weight 900
  - tracking tight (negative)
  - optional uppercase for short badges
- `nl-tabular`:
  - `font-variant-numeric: tabular-nums`
- `nl-text-shadow`:
  - small shadow for video overlay legibility (avoid glow spam)

---

## 2) Icon system
### 2.1 Source
- Use `lucide-react` everywhere for consistency.

### 2.2 Sizes
Choose only from:
- **20**: default inline actions
- **24**: primary icon buttons (most common)
- **28**: hero/center emphasis (rare)

### 2.3 Stroke / filled policy
- Default: outline + consistent stroke width.
- Filled: only for “selected/active” states (e.g. liked).

### 2.4 Implementation
Add an `Icon` wrapper component that:
- Normalizes size and stroke width.
- Supports a `filled` boolean for active states.
- Prevents per-page ad-hoc icon sizing.

---

## Migration guidance
- `/play`: migrate all inline `<LucideIcon size=...>` to `Icon`.
- Bottom nav: unify to icon size 20 with consistent stroke.
- Any icon-only tap target must be 44×44 via `IconButton`/`Button size="icon"`.

