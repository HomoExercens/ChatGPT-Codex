from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from neuroleague_api.core.config import Settings
from neuroleague_api.storage_backend import get_storage_backend, guess_content_type

router = APIRouter(prefix="/api/assets", tags=["assets"])

# Intentionally restrict public asset serving to shareable artifacts only.
_ALLOWED_PREFIXES = ("clips/", "sharecards/", "ops/")


@router.get("/{key:path}")
def get_asset(key: str):
    raw = str(key or "").lstrip("/")
    if not any(raw.startswith(p) for p in _ALLOWED_PREFIXES):
        raise HTTPException(status_code=404, detail="Asset not found")

    backend = get_storage_backend()
    try:
        local = backend.local_path(key=raw)
    except Exception:  # noqa: BLE001
        local = None

    if local is not None and local.exists():
        return FileResponse(
            path=str(local),
            media_type=guess_content_type(raw),
            filename=local.name,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    try:
        if backend.exists(key=raw):
            url = backend.public_url(key=raw)
            # Avoid infinite redirects when a CDN base URL points back to this endpoint.
            settings = Settings()
            self_prefix = "/api/assets/"
            self_abs_prefix = (
                f"{str(settings.public_base_url).rstrip('/')}{self_prefix}"
                if settings.public_base_url
                else None
            )
            if str(url).startswith(self_prefix) or (
                self_abs_prefix and str(url).startswith(self_abs_prefix)
            ):
                data = backend.get_bytes(key=raw)
                return Response(
                    content=data,
                    media_type=guess_content_type(raw),
                    headers={"Cache-Control": "public, max-age=31536000, immutable"},
                )

            return RedirectResponse(
                url=url,
                status_code=307,
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
    except Exception:  # noqa: BLE001
        pass

    raise HTTPException(status_code=404, detail="Asset not found")
