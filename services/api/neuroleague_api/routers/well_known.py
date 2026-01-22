from __future__ import annotations

import re

import orjson
from fastapi import APIRouter
from fastapi.responses import Response

from neuroleague_api.core.config import Settings


router = APIRouter(tags=["well-known"])


_FINGERPRINT_RE = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){31}$")


def _sha256_fingerprints(raw: str | None) -> list[str]:
    values = []
    for item in str(raw or "").replace("\n", ",").split(","):
        v = item.strip().upper()
        if not v:
            continue
        if _FINGERPRINT_RE.match(v):
            values.append(v)
    # Avoid accidental bloat / abuse via env.
    return values[:16]


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks_json() -> Response:
    """
    Android Digital Asset Links for App Links verification.

    Configure via:
      - NEUROLEAGUE_ANDROID_ASSETLINKS_PACKAGE_NAME
      - NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS (comma-separated)
    """
    settings = Settings()
    package_name = str(settings.android_assetlinks_package_name or "").strip()
    fingerprints = _sha256_fingerprints(settings.android_assetlinks_sha256_cert_fingerprints)

    if not package_name or not fingerprints:
        return Response(
            content="[]",
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    statements = [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package_name,
                "sha256_cert_fingerprints": fingerprints,
            },
        }
    ]
    return Response(
        content=orjson.dumps(statements),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )

