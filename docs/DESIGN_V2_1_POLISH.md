# NeuroLeague Design v2.1 — Premium Polish

This document upgrades Design v2 with a **premium polish pass** focused on typography clarity, icon consistency, scrim legibility, and touch ergonomics.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Requested model: `gemini-3-pro-preview`
- Actually used model (per tool output): `gemini-3-pro-preview`
- Spec theme: “Cinematic Precision” (content-first + ultra-clear data)

## Goals (v2.1)
- Make `/play` feel like a **native, high-end mobile game app**: immersive video, minimal chrome, zero readability failures.
- Remove “random” styling: unify **type**, **icons**, **scrims**, **touch targets**.

## Non‑negotiables (must not regress)
- Determinism invariants: `derive_seed`, replay digest, `pack_hash`, cache keys
- `/s/*` OG meta + `og:image` never‑404
- `/start?next=` open‑redirect guard
- `/api/assets` allowlist policy
- Service UI source of truth is `apps/web/`

---

## 1) Typography polish
### 1.1 Display vs Text
We separate type roles so the UI looks intentional:
- **Display**: results, WIN/LOSE, big numbers, hero headings
- **Text**: body copy, tooltips, labels, helper text

Implementation rules:
- Display uses heavier weight + tighter tracking, limited to short strings.
- Text stays calm; avoid excessive glow/shadow.

### 1.2 Tabular numerals (anti “HUD jitter”)
All changing numbers must use **tabular numerals**:
- Likes, shares, HP%, XP, timers, streak, counts

Implementation rule:
- Use a single utility/class so it’s consistent (`font-variant-numeric: tabular-nums`).

### 1.3 Text shadow & glow rules (tokenized)
Legibility over video must not be ad-hoc.
- Prefer **scrim first**, then a minimal, consistent shadow utility.
- Strong glow is allowed only for primary CTAs and only when `reduceMotion=false`.

---

## 2) Icon system unify
### 2.1 Sizes (single spec)
- Sizes: **20 / 24 / 28**
- Stroke width: consistent (default ~2, configurable)
- Filled vs outline policy:
  - Outline by default
  - Filled only to indicate “active/selected” state (e.g., liked)

### 2.2 Implementation
- Use a wrapper Icon component around `lucide-react`:
  - Centralizes size + strokeWidth + optional filled mode
  - Eliminates per-page inconsistencies

---

## 3) ScrimOverlay (video legibility)
We standardize top/bottom scrims:
- **Top scrim**: supports title/controls (height ~120px)
- **Bottom scrim**: supports HUD/CTA/meta (height ~240px)

Rule:
- Any HUD/CTA text must live on scrim OR use the standard shadow utility.

---

## 4) Touch target enforcement
All tappables must satisfy **min 44×44 px**:
- Buttons, icon buttons, bottom nav items, interactive chips

Implementation rule:
- Enforce in component APIs (not ad hoc per screen).

---

## References
- Gesture interactions: `docs/DESIGN_V2_1_GESTURES.md`
- Type & icon spec details: `docs/DESIGN_V2_1_TYPO_ICON.md`
- Motion/a11y policy: `docs/DESIGN_V2_1_MOTION_A11Y.md`

