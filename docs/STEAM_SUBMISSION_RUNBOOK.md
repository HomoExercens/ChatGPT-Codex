# STEAM SUBMISSION RUNBOOK — Demo Build (NeuroLeague)

> Steamworks UI/labels change over time; treat this as an internal checklist and follow Steamworks docs for the final source of truth.

## 0) References (Steamworks)
- Steam Next Fest: https://partner.steamgames.com/doc/marketing/steam_next_fest
- SteamPipe (build upload): https://partner.steamgames.com/doc/sdk/uploading
- Store assets: https://partner.steamgames.com/doc/store/assets

## 1) Required IDs (Fill These In)
- Main AppID: `<APPID_MAIN>`
- Demo AppID: `<APPID_DEMO>`
- Windows DepotID: `<DEPOTID_WINDOWS>`

Repo env knobs (demo conversion CTA):
- `NEUROLEAGUE_STEAM_APP_ID=<APPID_MAIN>`
- `NEUROLEAGUE_DISCORD_INVITE_URL=https://discord.com/invite/<code>`

## 2) Build Artifact Source (Windows Demo)
This repo provides a GitHub Actions workflow that produces a Windows desktop demo artifact:
- Workflow: `build-desktop-windows` (artifact downloadable from Actions UI)

Checklist:
- [ ] Artifact downloaded from Actions
- [ ] Windows machine smoke: “double-click → Home loads → Demo completes → clip + kit.zip works”

## 3) SteamPipe Upload (High-Level)
1) Install SteamCMD on a Windows build machine.
2) Create an `app_build.vdf` + `depot_build.vdf` for the Demo AppID and Windows depot.
3) Upload via SteamCMD.

Minimum validation after upload:
- [ ] Download demo from Steam client (staging branch ok)
- [ ] Launch → Home shows Demo CTA (if `NEUROLEAGUE_DEMO_MODE=true` in the packaged env)
- [ ] Demo Run completes offline (seeded), and assets (clip/kit.zip) are generated locally

## 4) Store Page (Assets + Screenshots)
Use:
- `docs/STEAM_STORE_PAGE.md`
- Scripts:
  - `python scripts/export_steam_assets.py --write-manifest --title "NeuroLeague"`
  - `python scripts/export_steam_screenshots.py --limit 8`

## 5) Next Fest Operational Notes
- During the festival, prioritize the Demo funnel (wishlists are the primary conversion).
- Keep a “no-risk update” plan: demo hotfixes only; avoid large balance/content changes during the event window.

