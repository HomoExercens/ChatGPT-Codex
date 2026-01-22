# STEAM DEMO CHECKLIST — “First 60 Seconds”

Steam Next Fest (Feb 2026): **2026-02-23 10:00 PT ~ 2026-03-02 10:00 PT**

> Steamworks guidance (summary): funnel users to the **Demo** during festivals. Treat the demo as the primary conversion surface.

## 0) Demo Mode Toggle
- [ ] Set `NEUROLEAGUE_DEMO_MODE=true`
- [ ] Home shows **“Play Demo Run (5 min)”** as the top CTA
- [ ] Training CTA is deprioritized (“Later”), but `/training` still works

## 1) First 60 Seconds (No Dead Ends)
Goal: user gets a *result* (replay + best clip) fast, without needing an account or a long setup flow.

- [ ] Guest start works (`Continue as Guest`)
- [ ] `/demo` loads and shows 3 presets
- [ ] Click **Play Demo Run** → within 60s:
  - [ ] replay is created
  - [ ] best clip render completes (vertical MP4 visible)
  - [ ] **Download Kit.zip** appears

## 2) Demo Run Golden Path (First 5 Minutes)
- [ ] Preset pick → `POST /api/demo/run`
- [ ] Replay opens (`/replay/{match_id}`)
- [ ] Best clip plays (9:16)
- [ ] Creator Pack download works (`/s/clip/{replay_id}/kit.zip`)
  - [ ] zip contains 4 files: `neuroleague_best_clip_*.mp4`, `neuroleague_thumb_*.png`, `neuroleague_caption_*.txt`, `neuroleague_qr_*.png`
- [ ] Demo completion screen CTAs:
  - [ ] **Wishlist Now** opens `steam://store/<APPID>` (fallback: `https://store.steampowered.com/app/<APPID>`)
  - [ ] **Join Discord** opens the invite URL
- [ ] **Beat This** CTA opens the challenge (`/challenge/{id}`)

## 3) Metrics / Funnels
- [ ] Events recorded: `demo_run_start`, `demo_run_done`, `demo_kit_download`, `demo_beat_this_click`
- [ ] Ops daily funnel shows **demo_v1**

## 4) “Do Not Ship” UX Failures
- [ ] Demo CTA missing when `NEUROLEAGUE_DEMO_MODE=true`
- [ ] Demo run requires Discord login / non-guest account
- [ ] Demo run can end without a replay + clip
- [ ] Demo share assets 404 (clip MP4 / kit.zip) without a retry path
- [ ] Demo path breaks the existing flow (Training → Forge → Ranked → Replay → Share)
