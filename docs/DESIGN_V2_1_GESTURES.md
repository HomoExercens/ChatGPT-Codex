# NeuroLeague Design v2.1 — /play Gesture UX

This document defines the **implementation-ready interaction spec** for `/play` in Design v2.1.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Requested model: `gemini-3-pro-preview`
- Actually used model (per tool output): `gemini-3-pro-preview`
- Concept label: “Cinematic Precision” (immersive video + minimal chrome)

## Goals
- Make `/play` behave like a **native vertical feed** (TikTok-style): swipe navigation, double-tap delight, UI chrome disappears when idle.
- Keep the current guardrails: only 1–2 videos preloaded, deterministic HUD extraction unchanged.

## Non‑negotiables
- No determinism changes, no `/s/*` OG regressions, no open-redirect changes, no `/api/assets` allowlist changes.

---

## 1) Swipe pager (vertical)
### Behavior
- **Swipe Up** → next clip
- **Swipe Down** → previous clip
- “Page” transition: translate + subtle fade (no spring).

### Gesture thresholds (recommended defaults)
- Minimum vertical travel: **≥ 56px**
- Direction lock: `abs(dy) > abs(dx) * 1.2`
- Max gesture duration for a “flick”: **≤ 650ms** (longer drags can still count if travel is large)

### Performance / preload
- Only **active** and **next** clip may preload video data (max 2).
- Others must use poster/thumbnail only.

### Reduce Motion
- No spring, no parallax.
- Transition = **short translate + fade** (duration ≤ 220ms).

---

## 2) Double‑tap reaction
### Behavior
- Double-tap anywhere on the video area triggers a reaction:
  - Default = **👍** (`reaction_type="up"`)
  - If user has reacted before (anywhere in the app), use their **last selected** reaction (`up|lol|wow`).
- Visual feedback: **center-screen burst** (short, < 700ms).
- Haptics: single short vibrate (if enabled).

### Network & optimistic UX
- Burst is **optimistic** (always shows immediately).
- API call is best-effort:
  - On failure: show a toast (`toast.error(...)`) but do not “rollback” the burst.

### Reduce Motion
- Burst becomes a simple **scale + fade** (no particles/glow pop).
- Provide a testable flag (`data-reduced="1"`).

---

## 3) UI chrome auto-hide
### Behavior
- After **idle** (no input) for `IDLE_MS`, fade out:
  - Top HUD
  - Right-side actions / CTA chrome
  - Bottom tab bar
- Any tap shows chrome again immediately and resets the timer.

### Suggested defaults
- `IDLE_MS = 6000` (long enough not to interfere with FTUE / first actions)
- Fade duration: 220–320ms

### Accessibility suppression
- Auto-hide must be **suppressed** when:
  - Keyboard mode active (recent keydown / focus navigation)
  - Focus is inside an interactive control (focusin)
  - A modal/bottom sheet is open
  - FTUE overlay is open (optional but recommended)

---

## Implementation notes
- Prefer pointer events to support desktop + mobile consistently.
- Add `data-gesture-ignore` on UI controls so double-tap/swipe doesn’t fire when the user taps a button.

