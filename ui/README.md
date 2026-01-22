# Creature Lab Auto‑Battle League (NeuroLeague) — Local Prototype

Monorepo prototype that turns the provided UI export into a runnable game loop:
blueprints → ranked queue → deterministic sim → replay viewer, plus training (Ray + RLlib).

## Quick Start

Prereqs: `python3`, `make`, `node` + `npm`, `curl`

- `make dev`
  - Bootstraps Python venv (falls back to `virtualenv.pyz` if `python -m venv` is unavailable)
  - Runs DB migrations
  - Seeds demo data (demo user, blueprints, one replay)
  - Starts API + Web

Open:
- Web: `http://localhost:3000`
- API health: `http://localhost:8000/api/health`
- API docs: `http://localhost:8000/docs`

## Commands

- `make dev` — API + Web + DB init + seed
- `make api` — API only
- `make web` — Web only
- `make db-init` — Alembic migrations (SQLite)
- `make seed-data` — Seed demo user/blueprints/replay
- `make seed-data-reset` — Delete + regenerate seeded demo content (bots + sample replays)
- `make test` — Determinism/replay/Elo/API schema tests
- `make fmt` — Ruff format + autofix

## UI Spec Snapshot (Important)

The original UI export lives at:
- `/home/clutch/cursor-workspace/cursor/뉴로리그`

A copy is kept in:
- `ui/`

If you receive an updated UI export, refresh `ui/` from the source path. Since the destination is inside the repo, exclude `ui/` to avoid recursion:
- Preferred: `./scripts/sync_ui.sh`
- Manual (same rules as the script):
  - `rsync -a --delete --exclude 'ui' --include '.env.local' --include '.gitignore' --include 'App.tsx' --include 'README.md' --include 'components/***' --include 'lib/***' --include 'views/***' --include 'constants.ts' --include 'index.html' --include 'index.tsx' --include 'metadata.json' --include 'package.json' --include 'tsconfig.json' --include 'types.ts' --include 'vite.config.ts' --exclude '*' \"/home/clutch/cursor-workspace/cursor/뉴로리그/\" \"./ui/\"`

## Repo Layout

- `apps/web` — React + TS + Vite + Tailwind (Router, TanStack Query, Zustand)
- `services/api` — FastAPI + SQLAlchemy + Alembic (SQLite)
- `packages/sim` — Deterministic simulator + replay + highlights
- `packages/rl` — PettingZoo ParallelEnv + RLlib PPO
- `artifacts` — DB, replays, models/checkpoints

## Notes

- Determinism: match RNG is derived from `match_id` + `seed_index` and replay digests are stable.
- Training uses CPU‑only PyTorch (`torch==2.9.1+cpu`) to avoid CUDA init crashes in WSL/sandbox.
