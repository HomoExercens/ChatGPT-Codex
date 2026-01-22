# Steam Next Fest Timeline (Ops Pack)

Steam Next Fest (Feb 2026): **2026-02-23 10:00 PT ~ 2026-03-02 10:00 PT**  
Note: Steamworks guidance emphasizes funneling users to the **Demo** during festivals, and Next Fest participation is typically **once per title**.

## D-14 (Two Weeks Before) — Prelaunch Rehearsal
- [ ] **Store page ready**: demo is the primary CTA; wishlist link is correct (`NEUROLEAGUE_STEAM_APP_ID`)
- [ ] **Desktop demo build artifact** exists (Windows) and boots in <30s to Home/Demo CTA
- [ ] **Demo golden path** passes offline/slow network:
  - [ ] Guest start → `/demo` → run → replay → best clip → kit.zip
  - [ ] Wishlist CTA + Discord CTA visible on demo completion screen
- [ ] **Ops ready**:
  - [ ] `/ops` shows “Next Fest Live” card (demo completion + kit + wishlist + 5xx/backlog + alerts)
  - [ ] Alerts enabled + cooldown verified in mock (`NEUROLEAGUE_ALERTS_ENABLED=1`)
- [ ] **Runbook dry-run**: follow `docs/RUNBOOK_DEPLOY.md` end-to-end once on a real VPS

## D-7 (One Week Before) — Freeze + Only Bugfixes
- [ ] Content/pack changes freeze (balance only if critical)
- [ ] Demo scripts/assets updated:
  - [ ] `scripts/export_steam_assets.py` outputs capsules under `artifacts/steam_assets/`
  - [ ] Screenshot candidates selected for the Steam store page
- [ ] Deploy smoke stays green (CI + VPS rehearsal)
- [ ] Discord announcements drafted (short, link to demo share landing)

## D-1 (Day Before) — Final Checklist
- [ ] VPS rehearsal check script passes: `scripts/vps_rehearsal_check.sh <base_url>`
- [ ] Ops rollups refreshed: `make ops-metrics-rollup`
- [ ] Smoke sanity:
  - [ ] `/api/ready` ok
  - [ ] `/s/*` OG meta present, og:image never-404
  - [ ] `/s/clip/*/video.mp4` Range 206 works
  - [ ] `/s/clip/*/kit.zip` downloads + contains 4 files
- [ ] Alerts channel configured (Discord outbox/webhook), message length <2000 chars
- [ ] Rollback plan confirmed (revert to last handoff tag)

## D-day (Festival Live) — Operating Loop
- [ ] Monitor `/ops` “Next Fest Live”:
  - demo completion rate (start→done)
  - kit downloads + wishlist clicks
  - 5xx spike + render backlog
  - recent alerts + last check time
- [ ] Respond to alerts (avoid hotfix spam; prioritize availability + onboarding)
- [ ] Daily Discord post: clip/share + “Beat This / Remix” CTA + wishlist link
- [ ] Record changes in `docs/HANDOFF_REPORT.md` + ship via handoff bundle

