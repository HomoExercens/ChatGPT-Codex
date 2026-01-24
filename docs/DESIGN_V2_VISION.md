# NeuroLeague Design v2 — Vision (Premium Mobile)

This document is the source-of-truth for the UI/UX “v2” direction for `apps/web` (React+TS+Vite+Tailwind).

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Requested model: `gemini-3-pro-preview`
- Actually used model (per tool output): `gemini-3-pro-preview`
- Runs:
  - Run 1: 3 directions + initial tokens/components/screens
  - Run 2: domain-corrected (Forge = Blueprint editor) spec + expanded tokens/components/screens

## Design Goal
Deliver a **high-end, Android-first mobile game app** feel:
- “Content-first”: video + match outcome is the hero; UI chrome must disappear until needed.
- “Electric clarity”: only the most important CTAs glow; everything else is calm.
- “Zero broken interactions”: if a control can fail in preview/local, it must be gated or made safe.

## The 3 Design Directions (Gemini)
### A) Cyber‑Sport Industrial
- Aggressive, angular, high-contrast “league HUD”.
- Risk: visually loud; easy to feel cluttered in a vertical feed.

### B) Soft Glass Ethereal
- Frosted glass everywhere, pastel gradients, soft shapes.
- Risk: performance cost (blur-heavy) + video readability.

### C) Cinematic Minimal + Electric Accent (Selected)
- Deep void background + sharp electric accents for actions.
- Best fit for `/play` TikTok-style feed: **video stays dominant**.
- Accents communicate interactability without adding “UI noise”.

## Selected Direction: “Cinematic Minimal + Electric Accent”
### Core Principles
1) **Void surfaces**: near-black backgrounds; panels are “glass” with thin borders (not heavy shadows).
2) **Electric CTAs**: primary actions use cyan→violet energy gradient + subtle glow.
3) **Premium readability**: text always sits on a scrim or gets a shadow on video.
4) **Motion = physical, short**: snap-in, micro-scale on press; no long bouncy loops.
5) **Accessibility**: touch targets ≥ 44px; strong focus-visible ring; `reduceMotion` disables strong effects.

### What “Premium” means here (practical rules)
- Avoid large white cards and slate-grey dashboards in the core game path.
- Use **consistent spacing + radii** (no random rounded values per page).
- Use 2 CTAs max on `/play` overlay: **Beat This** + **Quick Remix**.
- “Hero” + “Quest” UI must feel like **widgets**, not cheap rectangular cards.

## Key Screens to Refresh (v2 priority)
- `/play` (highest): cinematic feed + minimal HUD + premium widgets.
- Beat result (Reply result in `ReplayPage`): WIN/LOSE should both feel rewarding and drive next action.
- `/forge`: “Creator Studio” (Blueprint edit + Auto Tune sheet + lineage).
- `/me`: “Badge Cabinet” (collection/display), XP/level/streak hierarchy.
- `/ops/hero`: dense admin table but using the same v2 tokens/components.

## Non‑negotiable Constraints (must not regress)
- Determinism invariants: `derive_seed`, replay digest, `pack_hash`, cache keys.
- `/s/*` OG meta + `og:image` never‑404.
- `/start?next=` open‑redirect guard.
- `/api/assets` allowlist policy.

