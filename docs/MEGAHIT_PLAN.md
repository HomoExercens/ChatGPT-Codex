# MEGAHIT Plan (Android‑first) — NeuroLeague

## North Star FTUE (v1)
Goal: **0 logins, 0 confusion, 0 dead clicks**.

- **≤10s:** user lands on `/play` and sees a full‑screen 9:16 clip with a single obvious CTA.
- **≤30s:** user taps **Beat This** → match starts → result screen appears (WIN/LOSE).
- **≤60s:** user taps **Share Reply Clip** → returns to original clip and sees their reply in **Replies**.

## P0 (must ship first): “No broken interactions” + mobile game shell
1) **IA + routing**
   - Make `/` redirect to `/play` (no login wall).
   - Add bottom tabs: Play(`/play`), Forge(`/forge`), Inbox(`/inbox`), Profile(`/me`).
2) **App shell reliability**
   - Safe‑area + portrait‑first layout.
   - Global **ErrorBoundary** + **Toast** so failures are visible (never “nothing happened”).
3) **Broken feature containment**
   - Gate unstable “훈련/강화(Training/Upgrade)” behind **Labs** (`?labs=1` or `VITE_ENABLE_LABS=1`).
   - Remove Training entry points from the FTUE path.
4) **Always‑success power button (Forge)**
   - Add deterministic **Auto Tune** (DPS/Tank/Speed): creates a forked blueprint and returns quickly.

## P1 (next): visual juice + “reward” loop
1) **Clips Feed juice**
   - Autoplay‑on‑visible video, tap‑to‑unmute (remember preference).
   - HUD overlays: win/loss badge, synergy chips, primary Beat This CTA, secondary Quick Remix CTA.
2) **Micro‑interactions**
   - Haptics (`navigator.vibrate`) + tiny WebAudio SFX (no assets).
   - Settings toggles (sound/haptics) and remember them.
3) **Reward UX**
   - Post‑match result screen: BIG WIN/LOSE + progress bar + Share Reply primary CTA.
   - Replies cards: clearer ranking (“Top Replies”), reactions shown prominently.

## P2 (open loops): progression + creator graph
- Lightweight progression (streak/XP), weekly novelty, profile polish.
- Social graph: “people who beat you / you beat” and reply chains as followable threads.

## Acceptance criteria (release gate)
- `/play` works on mobile viewport with no auth steps and shows a playable clip within 10s.
- Beat This → match done → reply share CTA is reachable without errors.
- Replies section shows at least one reply card with clear “Top/Recent” and reaction counts.
- **No dead clicks** on the default path (Play → Beat This → Result → Share/Back).
- Training/Upgrade is not reachable from the default path unless Labs is enabled.
- Determinism invariants and share OG/og:image policies remain unchanged.

## Instrumentation (confirm impact)
Events (minimum):
- `play_open`
- `clip_view` (include `watched_ms`)
- `beat_this_click`
- `quick_remix_click`
- `auto_tune_click`, `auto_tune_success`
- `match_done`
- `reply_clip_shared`
- `ftue_completed` (first time only)

Funnel rollup:
- `ftue_v1 = play_open → clip_view(watched_ms>=3000) → beat_this_click → match_done → reply_clip_shared`

