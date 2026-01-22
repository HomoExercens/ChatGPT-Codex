# NeuroLeague Desktop Demo (Electron)

This is a lightweight desktop wrapper for the existing Web UI + local FastAPI server.

## Dev (WSL/Linux)
Prereqs:
- Node.js + npm
- Python 3.12 (CPU-only)

Commands:
- `make desktop-dev`
  - builds `apps/web` → starts Electron app
  - the Electron app spawns a local API server via `python3 -m uvicorn ...`

If your Python executable is not `python3`, set:
- `NEUROLEAGUE_DESKTOP_PYTHON=/path/to/python`

## Runtime behavior
- Picks local ports (defaults: API `8000`, Web `3100`, auto-increments if busy)
- Spawns API with:
  - `NEUROLEAGUE_DESKTOP_MODE=1` (starts local render job runner)
  - `NEUROLEAGUE_DEMO_MODE=1` (surfaces demo CTA)
  - `NEUROLEAGUE_PUBLIC_BASE_URL=http://127.0.0.1:<web_port>`
- Serves `apps/web/dist` on the web port and proxies `/api/*` + `/s/*` to the local API

## Windows build (CI)
GitHub Actions workflow:
- `.github/workflows/build-desktop-windows.yml`

It prepares:
- `apps/web/dist` build
- `apps/desktop/python/` embedded Python + `requirements-desktop.txt` deps
- Electron `zip` artifact via `electron-builder`

