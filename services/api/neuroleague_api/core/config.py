from __future__ import annotations

import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEUROLEAGUE_", extra="ignore")

    ruleset_version: str = "2026S1-v1"
    public_base_url: str | None = None
    trust_proxy_headers: bool = False
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_json: bool = False

    db_url: str = "sqlite:///./artifacts/neuroleague.db"
    artifacts_dir: str = "./artifacts"
    ray_address: str | None = None

    # Storage backend for artifacts (local filesystem by default).
    # - local: store under artifacts_dir and serve via /api/assets
    # - s3: optional; requires boto3 + NEUROLEAGUE_STORAGE_S3_BUCKET
    storage_backend: str = "local"
    storage_public_base_path: str = "/api/assets"
    storage_cdn_base_url: str | None = None
    storage_s3_bucket: str | None = None
    storage_s3_prefix: str = ""
    storage_s3_region: str | None = None
    storage_s3_endpoint_url: str | None = None

    auth_jwt_secret: str = "dev-secret-change-me"
    auth_jwt_issuer: str = "neuroleague-local"
    auth_jwt_exp_minutes: int = 60 * 24 * 7

    blueprint_submit_cooldown_sec: int = 120

    matchmaking_repeat_window: int = 10
    matchmaking_repeat_recent_window: int = 3
    matchmaking_repeat_penalty: int = 200
    matchmaking_repeat_recent_penalty: int = 500
    matchmaking_pick_margin: int = 100

    # Public alpha guardrails (in-memory rate limit; per-process).
    rate_limit_enabled: bool = True
    rate_limit_training_runs_per_minute: int = 4
    rate_limit_training_runs_per_hour: int = 20
    rate_limit_training_runs_per_minute_ip: int = 10
    rate_limit_training_runs_per_hour_ip: int = 40
    rate_limit_render_jobs_per_minute: int = 20
    rate_limit_render_jobs_per_hour: int = 200
    rate_limit_render_jobs_per_minute_ip: int = 80
    rate_limit_render_jobs_per_hour_ip: int = 800
    rate_limit_clip_events_per_minute: int = 120
    rate_limit_clip_events_per_hour: int = 2000
    rate_limit_clip_events_per_minute_ip: int = 600
    rate_limit_clip_events_per_hour_ip: int = 10000
    rate_limit_follow_per_minute: int = 30
    rate_limit_follow_per_hour: int = 500
    rate_limit_follow_per_minute_ip: int = 120
    rate_limit_follow_per_hour_ip: int = 2000

    rate_limit_reports_create_per_minute: int = 6
    rate_limit_reports_create_per_hour: int = 60
    rate_limit_reports_create_per_minute_ip: int = 30
    rate_limit_reports_create_per_hour_ip: int = 300

    rate_limit_blueprint_fork_per_minute: int = 12
    rate_limit_blueprint_fork_per_hour: int = 200
    rate_limit_blueprint_fork_per_minute_ip: int = 60
    rate_limit_blueprint_fork_per_hour_ip: int = 1200

    rate_limit_blueprint_auto_tune_per_minute: int = 6
    rate_limit_blueprint_auto_tune_per_hour: int = 120
    rate_limit_blueprint_auto_tune_per_minute_ip: int = 20
    rate_limit_blueprint_auto_tune_per_hour_ip: int = 400

    rate_limit_ranked_queue_per_minute: int = 6
    rate_limit_ranked_queue_per_hour: int = 80
    rate_limit_ranked_queue_per_minute_ip: int = 30
    rate_limit_ranked_queue_per_hour_ip: int = 300

    rate_limit_events_track_per_minute: int = 300
    rate_limit_events_track_per_hour: int = 5000
    rate_limit_events_track_per_minute_ip: int = 1200
    rate_limit_events_track_per_hour_ip: int = 20000

    rate_limit_challenge_accept_per_minute: int = 10
    rate_limit_challenge_accept_per_hour: int = 200
    rate_limit_challenge_accept_per_minute_ip: int = 40
    rate_limit_challenge_accept_per_hour_ip: int = 800

    # Guests can be created freely via /start deep links, so keep Beat/Challenge tighter.
    rate_limit_guest_challenge_accept_per_minute: int = 4
    rate_limit_guest_challenge_accept_per_hour: int = 40
    rate_limit_guest_challenge_accept_per_minute_ip: int = 10
    rate_limit_guest_challenge_accept_per_hour_ip: int = 120
    rate_limit_guest_challenge_accept_per_minute_device: int = 4
    rate_limit_guest_challenge_accept_per_hour_device: int = 40

    challenge_accept_dedupe_window_sec: int = 8

    admin_token: str | None = None

    referral_ip_credit_limit_per_day: int = 3

    # Lightweight ops scheduler (runs metrics/balance rollups periodically).
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 60 * 24

    # Optional artifact retention (runs in scheduler; default off).
    artifacts_retention_enabled: bool = False
    artifacts_retention_days: int = 14
    artifacts_retention_keep_shared_days: int = 7

    # Optional: seed demo content on boot (safe, idempotent).
    seed_on_boot: bool = False

    # Preview hardening (public preview / staging): disable expensive public work by default.
    preview_mode: bool = False

    # Demo mode (Steam Next Fest / onboarding).
    demo_mode: bool = False
    desktop_mode: bool = False
    steam_app_id: str | None = None
    discord_invite_url: str | None = None

    # Alerts (Discord) — optional (ops).
    alerts_enabled: bool = False
    alerts_discord_webhook_url: str | None = None

    # OAuth (Discord) — optional (public alpha).
    discord_client_id: str | None = None
    discord_client_secret: str | None = None
    discord_oauth_mock: bool = False

    # Discord launch loop (webhook/app/mock).
    discord_mode: str = "webhook"
    discord_webhook_url: str | None = None
    discord_application_id: str | None = None
    discord_public_key: str | None = None
    discord_bot_token: str | None = None
    discord_guild_id: str | None = None
    discord_channel_id: str | None = None
    discord_daily_post_hour_kst: int = 9

    # Viral engine: best-clip prewarm (enqueue render jobs after match completion).
    best_clip_prewarm_enabled: bool = True
    best_clip_prewarm_queue_types: str = "ranked,challenge"

    # Android deep links (TWA/App Links) — optional.
    android_assetlinks_package_name: str | None = None
    android_assetlinks_sha256_cert_fingerprints: str | None = None
    android_install_url: str | None = None

    @field_validator("android_assetlinks_sha256_cert_fingerprints")
    @classmethod
    def _validate_android_assetlinks_fingerprints(
        cls, v: str | None
    ) -> str | None:
        raw = str(v or "").strip()
        if not raw:
            return None

        fp_re = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){31}$", flags=re.IGNORECASE)

        out: list[str] = []
        seen: set[str] = set()
        invalid: list[str] = []
        for item in raw.replace("\n", ",").split(","):
            fp = str(item or "").strip()
            if not fp:
                continue
            norm = fp.upper()
            if not fp_re.match(norm):
                invalid.append(fp)
                continue
            if norm in seen:
                continue
            seen.add(norm)
            out.append(norm)

        if invalid:
            raise ValueError(
                "NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS contains an invalid "
                f"fingerprint: {invalid[0]!r} (expected 'AA:BB:..' 32 bytes SHA-256)"
            )
        if not out:
            return None
        if len(out) > 16:
            raise ValueError(
                "NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS has too many entries "
                f"({len(out)} > 16)"
            )
        return ",".join(out)
