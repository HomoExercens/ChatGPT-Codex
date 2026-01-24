# NeuroLeague Design v2 — Components

This document defines the v2 UI kit used across `apps/web`.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Actually used model (per tool output): `gemini-3-pro-preview`

## Global interaction rules
- Touch target: **≥ 44px** for all tappables.
- Press feedback: subtle **micro-scale** + haptics/sfx only when enabled.
- Focus: always visible via `focus-visible` ring (token `--nl-ring`).
- Reduced motion: when `html[data-reduce-motion='true']`, disable strong animations and keep transitions to fade/opacity.

## Component inventory (maps to `apps/web/src/components/ui.tsx`)

### Button
- Sizes:
  - `sm`: 36px height (still ≥44px when used with padding containers; prefer `md` on mobile FTUE path)
  - `md`: 48px height (default)
  - `lg`: 56px height (rare; hero CTA)
  - `icon`: 44×44px
- Variants:
  - `primary`: electric gradient (brand→accent), `text-black`, glow
  - `secondary`: glass surface, border, `text-fg`
  - `outline`: transparent, border, `text-fg`
  - `ghost`: transparent, hover/press surface highlight
  - `destructive`: danger accent
- States: `disabled` lowers opacity and removes glow; `isLoading` shows spinner and disables.

### IconButton
- Wrapper around `Button size="icon"`; must include `aria-label`.

### Chip / Badge
- Chip: tiny HUD label on video; mono/uppercase; glass background.
- Badge: status label, can be `success|warning|error|neutral|brand`.

### Card
- Surface container (glass or solid surface), thin border, optional “active” highlight.
- Used for quests widget, hero widgets, admin panels, and profile cabinet panels.

### BottomSheet / Modal
- BottomSheet: mobile-first, slide-up panel with handle; backdrop dim + optional blur.
- Modal: center on desktop (future), but current implementation can share BottomSheet.

### Toast
- Non-blocking status; sits above the tab bar and respects safe-area.
- Variants: info/success/error.

### Progress
- Thin bar with optional glow on progress change (short duration).

### Skeleton
- Dark shimmer/pulse placeholder for video loading and async panels.

### BottomNav
- Glass tab bar with active underglow; icons (lucide) + tiny label.
- Height controlled by `--nl-tabbar-h` + safe-area inset.

