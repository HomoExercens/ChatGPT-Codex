# NeuroLeague Design v2 — Tokens

Tokens are the single lever: **change tokens ⇒ app tone changes**.

## Gemini UI Spec (required provenance)
- Tool used: `gemini_ui_design`
- Actually used model (per tool output): `gemini-3-pro-preview`

## Naming + Philosophy
- Prefix: `--nl-*`
- Colors are stored as **RGB triplets** (`r g b`) to support Tailwind alpha syntax: `rgb(var(--nl-*) / <alpha>)`.
- Dark is the default. Light mode is minimal via `prefers-color-scheme: light`.

## File Location
- Implemented in: `apps/web/src/styles/tokens.css`
- Imported by: `apps/web/src/main.tsx`

## Token Set (v2)
### 1) Semantic colors
- `--nl-bg`: app background (“void”)
- `--nl-surface-1/2/3`: layered surfaces (cards/sheets/nav)
- `--nl-fg`: primary text
- `--nl-fg-muted/subtle`: secondary labels
- `--nl-border`: base border color (use alpha in Tailwind)
- `--nl-ring`: focus ring color

### 2) Brand / accents / status colors
- `--nl-brand-*`: electric cyan scale (primary CTA energy)
- `--nl-accent-*`: electric violet scale (secondary energy; also used for a11y colorblind swap)
- `--nl-success-*`, `--nl-warning-*`, `--nl-danger-*`: status colors

### 3) Layout + radii + motion
- Radii: `--nl-radius-*`
- Elevation: `--nl-shadow-*`
- Motion: `--nl-dur-*`, `--nl-ease-*`
- Safe-area: `--nl-tabbar-h` and helper utility classes (`.pt-safe` etc)

## Tailwind Mapping Guidance
Update `apps/web/tailwind.config.ts` to expose token-backed utilities:
- Colors: `bg`, `surface-*`, `fg`, `muted`, `border`, `ring`, `brand`, `accent`, `success`, `danger`, `warning`
- Radius: map to `--nl-radius-*`
- Shadows: define a couple of token-driven shadows (glass + glow)

This ensures styles are primarily expressed as Tailwind classes like:
- `bg-bg text-fg`
- `bg-surface-1/70 border border-border/12`
- `shadow-glass`
- `focus-visible:ring-2 focus-visible:ring-ring/40`

## Colorblind / a11y notes
The app already supports `data-colorblind` via `useApplyA11ySettings()` which swaps `--nl-accent-*`.
Design v2 keeps that contract: **accent is swappable**, brand remains stable.

