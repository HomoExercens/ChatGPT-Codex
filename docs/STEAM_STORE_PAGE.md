# STEAM STORE PAGE — Assets & Checklist (NeuroLeague)

Steam Next Fest (Feb 2026): **2026-02-23 10:00 PT ~ 2026-03-02 10:00 PT**

> Steamworks docs (partner login required):
> - Steam Next Fest: https://partner.steamgames.com/doc/marketing/steam_next_fest
> - Store graphical assets: https://partner.steamgames.com/doc/store/assets
> - Store page rules (graphical asset guidelines): https://partner.steamgames.com/doc/store/page

## 1) Core Guidance (Summary)
- Next Fest 참여는 **Demo 빌드가 사실상 필수**이며, 행사 기간에는 유저를 **Demo로 유도**하는 것을 권장(상세는 Steamworks 문서 기준).
- Next Fest는 타이틀당 **1회만** 참가 가능(일정/정책은 Steamworks 기준).

## 2) Store Capsules (Required Sizes)
Generate these PNGs under `artifacts/steam_assets/`:
- Header Capsule: `920x430` → `capsule_header_920x430.png`
- Small Capsule: `462x174` → `capsule_small_462x174.png`
- Main Capsule: `1232x706` → `capsule_main_1232x706.png`
- Vertical Capsule: `748x896` → `capsule_vertical_748x896.png`

Script:
- `python scripts/export_steam_assets.py --write-manifest --title "NeuroLeague" --bg "#0b1220"`
- (Optional) `--input <path/to/sharecard_or_thumb.png>`
- (Optional) `NEUROLEAGUE_STEAM_FONT_PATH=/path/to/font.ttf` (if you want consistent font rendering across machines)

## 3) Store Screenshots (1920x1080)
Export screenshot candidates (letterboxed to 1920x1080) from `docs/screenshots/`:
- `python scripts/export_steam_screenshots.py --limit 8`

Outputs:
- `artifacts/steam_assets/screenshots/01.png` … `08.png`
- `artifacts/steam_assets/screenshots/screenshots_manifest.json`

Tip:
- `NEUROLEAGUE_E2E_FAST=1 make e2e` regenerates `docs/screenshots/*.png`.

## 4) Trailer (Optional Helper)
If `ffmpeg` is available:
- `bash scripts/make_trailer_teaser.sh`

Output:
- `artifacts/steam_assets/trailer_teaser.mp4`

## 5) Upload Checklist (Preflight)
- [ ] Demo build is ready (Windows) and launches to Home → Demo CTA within 30s
- [ ] Store capsules uploaded (4 sizes)
- [ ] 1920x1080 screenshots uploaded (Steam rules compliant)
- [ ] Trailer uploaded (optional)
- [ ] Store text: features/description match what the Demo actually contains

