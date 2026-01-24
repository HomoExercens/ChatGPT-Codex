# NeuroLeague Design v2 — Screens (High-level Mock Specs)

These are implementation-facing “mockups in text” for the v2 refresh.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Actually used model (per tool output): `gemini-3-pro-preview`

## 1) `/play` — Cinematic Feed
**Layout**
- Full-screen video (9:16), `bg-bg`.
- Top overlay: lightweight controls (mode/sort, sound toggle) on a subtle top scrim.
- Bottom overlay: content + CTAs on a bottom scrim for readability.

**HUD**
- Top-left: outcome badge (WIN/LOSE) + tiny HP bar (already exists → restyle).
- Mid overlay: highlight badges only when events occur (already exists → restyle).
- Bottom-left: creator + build name (short).

**CTAs**
- Primary: **Beat This** (electric gradient pill) — always visible on active card.
- Secondary: **Quick Remix** (glass button) — opens bottom sheet with 3 presets.
- Hero + Quest: premium widgets (glass, thin border, subtle glow), never “cheap white card”.

**Error/loading**
- If video load fails: skeleton poster + toast explaining “tap to retry / check network”.
- Keep current performance guardrails (only 1–2 video preload; IntersectionObserver playback).

## 2) Beat Result (Reply Result in `ReplayPage`)
**WIN**
- Big WIN typography; subtle “energy burst” behind (disabled under reduceMotion).
- Show 1 badge: PERFECT / ONE-SHOT / CLUTCH.
- Primary CTA: **Share Reply Clip**.
- Secondary CTA: **View Original**.

**LOSE**
- Big LOSE typography.
- Show “closeness” (“Almost!”) line (already exists) in premium capsule.
- Primary CTA: **Auto Tune (Counter)** (one tap) → pushes to Forge tuned build (existing flow).
- Secondary CTA: **Share Reply Clip** still available when applicable.

## 3) `/forge` — Creator Studio
**Structure**
- Header: blueprint selector + “fork lineage” summary.
- Sections: Lineup / Items / Lineage (or existing structure, but visually grouped).

**Auto Tune**
- BottomSheet with 3 preset cards (DPS/Tank/Speed) + short description.
- After success: show a “Before vs After” change list in a premium card.
- 1-tap CTA: **Queue match**.

## 4) `/me` — Badge Cabinet
- Profile header: display name + level + XP progress bar.
- Streak: show streak days + Shield tokens in a premium stat row.
- Badge Cabinet: grid of “badges as collectibles” (glass tiles, locked state subdued).
- Keep “Logout” safe and obvious but not visually dominant.

## 5) `/ops/hero`
- Dense but consistent: dark glass panels, readable mono numbers, clear expanders.
- Candidate rows: show wow_score + breakdown expand, plus Pin/Exclude controls.
- Keep labels and buttons stable for existing e2e (`Hero Auto-curator v2`, `Recompute now`).

