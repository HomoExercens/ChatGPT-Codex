from __future__ import annotations

import os

try:
    import ray  # type: ignore
except Exception:  # noqa: BLE001
    ray = None  # type: ignore[assignment]

from neuroleague_api.core.config import Settings


def ensure_ray() -> None:
    if ray is None:
        raise RuntimeError("ray_not_installed")
    if ray.is_initialized():
        return
    settings = Settings()
    if settings.ray_address:
        # Connect to an existing Ray cluster (e.g., docker-compose.prod.yml).
        ray.init(
            address=str(settings.ray_address),
            ignore_reinit_error=True,
            log_to_driver=False,
            runtime_env={"env_vars": dict(os.environ)},
        )
        return

    # Local dev: no dashboard, keep logs quieter.
    ray.init(
        include_dashboard=False,
        ignore_reinit_error=True,
        log_to_driver=False,
        runtime_env={"env_vars": dict(os.environ)},
    )
