from __future__ import annotations

import json
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal
from neuroleague_api.metrics import (
    observe_http_request,
    record_http_error_event,
    render_prometheus_metrics,
)
from neuroleague_api.storage_backend import get_storage_backend


def _parse_csv(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def create_app(*, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    app = FastAPI(
        title="NeuroLeague API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url="/docs",
    )

    if settings.trust_proxy_headers:
        # Trust X-Forwarded-* headers when behind a reverse proxy.
        # For safety, pair this with TrustedHostMiddleware + PUBLIC_BASE_URL.
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    allowed_hosts = _parse_csv(settings.allowed_hosts) or ["*"]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    cors_origins = _parse_csv(settings.cors_allowed_origins)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def _request_context(request: Request, call_next):
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000.0
            _observe_http(
                request=request,
                status_code=500,
                duration_ms=duration_ms,
                request_id=request_id,
            )
            if settings.log_json:
                _log_json(
                    {
                        "level": "error",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "duration_ms": round(duration_ms, 2),
                    }
                )
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        _observe_http(
            request=request,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        response.headers["X-Request-Id"] = request_id

        if settings.log_json:
            _log_json(
                {
                    "level": "info",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )

        return response

    @app.exception_handler(HTTPException)
    async def _with_request_id_http_exception(request: Request, exc: HTTPException):
        resp = await http_exception_handler(request, exc)
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            resp.headers["X-Request-Id"] = str(request_id)
        return resp

    @app.exception_handler(RequestValidationError)
    async def _with_request_id_validation_error(
        request: Request, exc: RequestValidationError
    ):
        resp = await request_validation_exception_handler(request, exc)
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            resp.headers["X-Request-Id"] = str(request_id)
        return resp

    @app.exception_handler(Exception)
    async def _with_request_id_unhandled(request: Request, exc: Exception):
        _ = exc
        request_id = getattr(request.state, "request_id", None)
        resp = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
        if request_id:
            resp.headers["X-Request-Id"] = str(request_id)
        return resp

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "ruleset_version": settings.ruleset_version}

    @app.get("/api/ready")
    def ready() -> dict[str, object]:
        db_ok = False
        storage_ok = False
        db_err: str | None = None
        storage_err: str | None = None

        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_err = str(exc)[:400]

        try:
            backend = get_storage_backend()
            # Local backend: root dir exists (created on init).
            # S3 backend: rely on backend public_url/exists being callable; deeper checks are optional.
            _ = backend.public_url(key="ops/ready.txt")
            storage_ok = True
        except Exception as exc:  # noqa: BLE001
            storage_err = str(exc)[:400]

        return {
            "status": "ok" if (db_ok and storage_ok) else "fail",
            "db": {"ok": db_ok, "error": db_err},
            "storage": {"ok": storage_ok, "error": storage_err},
        }

    @app.get("/api/metrics", response_class=PlainTextResponse)
    def metrics() -> Response:
        with SessionLocal() as session:
            text_out = render_prometheus_metrics(db=session)
        return PlainTextResponse(
            content=text_out, media_type="text/plain; version=0.0.4"
        )

    if settings.desktop_mode:
        from neuroleague_api.local_render_runner import (
            start_local_render_runner,
            stop_local_render_runner,
        )

        @app.on_event("startup")
        def _desktop_startup() -> None:
            # Desktop demo is self-contained; ensure SQLite schema exists without
            # requiring Alembic on the end-user machine.
            try:
                from neuroleague_api.db import Base, engine

                Base.metadata.create_all(engine)
            except Exception:  # noqa: BLE001
                pass
            start_local_render_runner()

        @app.on_event("shutdown")
        def _desktop_shutdown() -> None:
            stop_local_render_runner()

    from neuroleague_api.routers import (
        analytics,
        assets,
        auth,
        build_code,
        blueprints,
        challenges,
        hero_clips,
        clips,
        discord,
        demo,
        events,
        experiments,
        feed,
        featured,
        gallery,
        home,
        leaderboard,
        matches,
        meta,
        notifications,
        ops,
        quests,
        replays,
        render_jobs,
        reports,
        share,
        users,
        well_known,
    )

    app.include_router(well_known.router)
    app.include_router(auth.router)
    app.include_router(events.router)
    app.include_router(experiments.router)
    app.include_router(feed.router)
    app.include_router(home.router)
    app.include_router(build_code.router)
    app.include_router(blueprints.router)
    app.include_router(challenges.router)
    app.include_router(gallery.router)
    app.include_router(matches.router)
    app.include_router(replays.router)
    app.include_router(analytics.router)
    app.include_router(meta.router)
    app.include_router(demo.router)
    app.include_router(share.router)
    app.include_router(notifications.router)
    app.include_router(render_jobs.router)
    app.include_router(leaderboard.router)
    app.include_router(users.router)
    app.include_router(assets.router)
    app.include_router(ops.router)
    app.include_router(hero_clips.router)
    app.include_router(featured.router)
    app.include_router(featured.ops_router)
    app.include_router(quests.router)
    app.include_router(quests.ops_router)
    app.include_router(discord.router)
    app.include_router(discord.ops_router)
    app.include_router(clips.router)
    app.include_router(reports.router)

    if not settings.desktop_mode:
        from neuroleague_api.routers import ranked, training, tournament

        app.include_router(ranked.router)
        app.include_router(training.router)
        app.include_router(tournament.router)

    return app


def _observe_http(
    *,
    request: Request,
    status_code: int,
    duration_ms: float | None = None,
    request_id: str | None = None,
) -> None:
    route = request.scope.get("route")
    template = getattr(route, "path", None) if route is not None else None
    path_label = str(template or request.url.path)
    observe_http_request(
        path=path_label,
        method=request.method,
        status=str(status_code),
        duration_ms=duration_ms,
        request_id=request_id,
    )
    if int(status_code) >= 400:
        record_http_error_event(
            path=path_label, method=request.method, status=int(status_code), request_id=request_id
        )


def _log_json(payload: dict[str, object]) -> None:
    try:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    except Exception:  # noqa: BLE001
        pass


app = create_app()
